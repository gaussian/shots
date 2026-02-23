from __future__ import annotations

import json
import logging
import pathlib
import sys
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import Page, sync_playwright

from .config import RunConfig, ShotGroup, ShotSpec
from .image_ops import Crop, add_label_banner, clamp_crop, crop_png, downscale_png, get_png_size, pngs_to_pdf
from .labels import desensitize_url, render_label
from .stability import wait_until_stable
from .utils import StepOutcome, normalize_url, now_ts, safe_filename, same_origin
from .viewport import Viewport, viewport_from_preset, viewport_from_values

log = logging.getLogger("shots")


def _configure_logging(out_dir: pathlib.Path) -> None:
    root = logging.getLogger("shots")
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)-5s %(name)s  %(message)s", datefmt="%H:%M:%S")

    fh = logging.FileHandler(out_dir / "shots.log", mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    root.addHandler(sh)


def _ensure_dir(p: pathlib.Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _resolve_viewport_for_shot(defaults: dict[str, Any], shot: ShotSpec, fallback: Viewport) -> Viewport:
    full_page = shot.full_page if shot.full_page is not None else bool(defaults.get("full_page", fallback.full_page))

    if shot.viewport:
        w = int(shot.viewport.get("width", fallback.width))
        h = int(shot.viewport.get("height", fallback.height))
        scale = int(shot.viewport.get("scale", defaults.get("scale", fallback.scale)))
        return viewport_from_values(w, h, scale, full_page)

    preset = shot.viewport_preset or defaults.get("viewport_preset")
    if preset:
        return viewport_from_preset(str(preset), full_page_override=full_page)

    # Defaults fall back to CLI fallback
    return viewport_from_values(fallback.width, fallback.height, fallback.scale, full_page)


def _auth_state_path(out_dir: pathlib.Path) -> pathlib.Path:
    return out_dir / "storage_state.json"


def login_manual(base_url: str, out_dir: pathlib.Path, viewport: Viewport) -> pathlib.Path:
    _ensure_dir(out_dir)
    state_path = _auth_state_path(out_dir)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": viewport.width, "height": viewport.height},
            device_scale_factor=viewport.scale,
        )
        page = context.new_page()
        page.goto(base_url, wait_until="domcontentloaded")

        print("\nManual login:")
        print("1) A browser window opened.")
        print("2) Log into your app manually.")
        print("3) Navigate to any page that proves you're logged in.")

        if sys.stdin.isatty():
            print("4) Return here and press ENTER.\n")
            input("Press ENTER when you are fully logged in... ")
        else:
            print('4) Click the ▶ (Resume) button in the Playwright inspector when done.\n')
            page.pause()

        context.storage_state(path=str(state_path))
        print(f"Saved auth state: {state_path}")

        context.close()
        browser.close()

    return state_path


def _execute_action(page: Page, action: Any, timeout_ms: int, nav_timeout_ms: int | None = None) -> StepOutcome:
    """
    Executes one action with optional repeat. Returns StepOutcome (ok/error).
    timeout_ms: used for element interactions (clicks, typing). Should be short (fail fast).
    nav_timeout_ms: used for page.goto navigation. Falls back to timeout_ms if not given.
    """
    from .llm import NavAction  # local import to keep deps clean

    _nav_timeout = nav_timeout_ms or timeout_ms

    if not isinstance(action, NavAction):
        return StepOutcome(ok=False, error="Invalid action type.")

    def do_once() -> None:
        if action.type == "goto" and action.url:
            page.goto(action.url, wait_until="domcontentloaded", timeout=_nav_timeout)
            return

        if action.type == "click_role" and action.role and action.name:
            loc = page.get_by_role(action.role, name=action.name)
            if action.nth is not None:
                loc = loc.nth(int(action.nth))
            loc.first.click(timeout=timeout_ms)
            return

        if action.type == "click_text" and action.text:
            loc = page.get_by_text(action.text, exact=False)
            if action.nth is not None:
                loc = loc.nth(int(action.nth))
            loc.first.click(timeout=timeout_ms)
            return

        if action.type == "type_text":
            if action.selector:
                page.locator(action.selector).click(timeout=timeout_ms)
                page.locator(action.selector).fill(action.input_text or "", timeout=timeout_ms)
                return
            page.keyboard.type(action.input_text or "")
            return

        if action.type == "press_key" and action.key:
            page.keyboard.press(action.key)
            return

        if action.type == "scroll":
            dy = int(action.scroll_y or 800)
            page.mouse.wheel(0, dy)
            return

        if action.type == "wait":
            page.wait_for_timeout(int(action.ms or 800))
            return

    if action.type in ("done", "fail"):
        return StepOutcome(ok=True, extra={"terminal": action.type})

    try:
        reps = max(1, int(action.repeat or 1))
        for _ in range(reps):
            do_once()
            page.wait_for_timeout(200)
        return StepOutcome(ok=True)
    except Exception as e:
        return StepOutcome(ok=False, error=repr(e))


def _pick_carry_note(history: list[dict[str, Any]]) -> str:
    for h in reversed(history):
        act = h.get("action") or {}
        np = act.get("next_prompt")
        if isinstance(np, str) and np.strip():
            return np.strip()
    return ""


def _get_page_context(page: Page, max_items: int = 80) -> str:
    """Extract interactive elements from the page accessibility tree."""
    try:
        snapshot = page.accessibility.snapshot()
    except Exception:
        return ""
    if not snapshot:
        return ""

    lines: list[str] = []

    def _walk(node: dict, depth: int = 0) -> None:
        if len(lines) >= max_items:
            return
        role = node.get("role", "")
        name = node.get("name", "")
        # Only include interactive/navigable elements
        if role in ("link", "button", "menuitem", "tab", "checkbox", "radio",
                     "textbox", "combobox", "searchbox", "option"):
            prefix = "  " * depth
            desc = f'{prefix}{role} "{name}"' if name else f"{prefix}{role}"
            # For links, try to get the URL via the node's value or description
            if role == "link" and node.get("description"):
                desc += f' ({node["description"]})'
            lines.append(desc)
        for child in node.get("children", []):
            _walk(child, depth + 1)

    _walk(snapshot)

    # Also grab all <a> hrefs from the page for URL context
    try:
        links = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .slice(0, 60)
                .map(a => ({ text: (a.textContent || '').trim().slice(0, 80), href: a.getAttribute('href') }))
                .filter(l => l.href && l.href !== '#')
        """)
        if links:
            lines.append("\nLINK HREFS:")
            for link in links:
                text = link.get("text", "").replace("\n", " ").strip()
                href = link.get("href", "")
                label = f'  "{text}"' if text else "  (no text)"
                lines.append(f'{label} href={href}')
    except Exception:
        pass

    return "\n".join(lines)


def _absolutize(base_url: str, maybe_url: str) -> str:
    if maybe_url.startswith("http://") or maybe_url.startswith("https://"):
        return maybe_url
    if maybe_url.startswith("/"):
        return urljoin(base_url + "/", maybe_url.lstrip("/"))
    # treat as relative path
    return urljoin(base_url + "/", maybe_url)


def run_config(
    cfg: RunConfig,
    out_dir: pathlib.Path,
    *,
    timeout_ms: int,
    action_timeout_ms: int = 5_000,
    headed: bool,
    use_llm: bool,
    model: str,
    use_llm_crop: bool,
    max_crop_retries: int = 2,
    save_source: bool,
    cli_fallback_viewport: Viewport,
) -> pathlib.Path:
    """
    Runs required screenshots from config file.
    If use_llm: LLM drives multi-step actions until it returns done.
    """
    _ensure_dir(out_dir)
    _configure_logging(out_dir)

    state_path = _auth_state_path(out_dir)
    if not state_path.exists():
        raise RuntimeError(f"Missing {state_path}. Run: shots login --base-url {cfg.base_url} --out-dir {out_dir}")

    total_shots = sum(len(g.shots) for g in cfg.groups)
    log.info("run_config: base_url=%s groups=%d shots=%d use_llm=%s model=%s timeout=%dms action_timeout=%dms",
             cfg.base_url, len(cfg.groups), total_shots, use_llm, model, timeout_ms, action_timeout_ms)

    client = None
    if use_llm:
        from .llm import make_openai_client

        client = make_openai_client()
        log.info("OpenAI client created")

    report: dict[str, Any] = {"base_url": cfg.base_url, "groups": [], "config": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        shot_counter = 0

        for group in cfg.groups:
            log.info("=== group: %s (output=%s, %d shots) ===", group.id, group.output, len(group.shots))
            group_dir = out_dir / safe_filename(group.folder or group.id)
            _ensure_dir(group_dir)

            group_pngs: list[bytes] = []
            group_report: dict[str, Any] = {
                "id": group.id,
                "output": group.output,
                "shots": [],
            }
            group_ok = True

            for shot in group.shots:
                shot_counter += 1
                log.info("--- shot %d/%d: %s ---", shot_counter, total_shots, shot.id)
                vp = _resolve_viewport_for_shot(cfg.defaults, shot, cli_fallback_viewport)

                context = browser.new_context(
                    storage_state=str(state_path),
                    viewport={"width": vp.width, "height": vp.height},
                    device_scale_factor=vp.scale,
                )
                page = context.new_page()

                shot_history: list[dict[str, Any]] = []
                final_url = ""

                try:
                    start = shot.url or cfg.start
                    start_url = _absolutize(cfg.base_url, start)
                    start_url = normalize_url(start_url)

                    log.info("goto %s", start_url)
                    page.goto(start_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    log.info("initial page loaded, waiting for stability")
                    wait_until_stable(page, timeout_ms=timeout_ms)

                    max_steps = int(cfg.defaults.get("max_nav_steps", 12))

                    if not use_llm and not shot.url:
                        raise RuntimeError("Shot has no url and --use-llm is false; cannot acquire from description.")

                    acquired = False
                    for step_i in range(1, max_steps + 1):
                        log.info("step %d/%d: waiting for stability", step_i, max_steps)
                        wait_until_stable(page, timeout_ms=timeout_ms)

                        log.debug("taking screenshot for LLM")
                        source_png = page.screenshot(full_page=vp.full_page)

                        if not use_llm:
                            acquired = True
                            break

                        from .llm import next_action_for_shot, _action_signature, failed_signatures

                        page_ctx = _get_page_context(page)
                        log.debug("page_context:\n%s", page_ctx)

                        carry_note = _pick_carry_note(shot_history)
                        prev_failed = failed_signatures(shot_history)
                        log.info("step %d/%d: calling LLM", step_i, max_steps)
                        action = next_action_for_shot(
                            client=client,
                            model=model,
                            base_url=cfg.base_url,
                            current_url=page.url,
                            goal_description=shot.description,
                            preview_png_bytes=source_png,
                            step_index=step_i,
                            history=shot_history,
                            carry_note=carry_note,
                            page_context=page_ctx,
                        )

                        sig = _action_signature(action)
                        if sig in prev_failed and action.type not in ("done", "fail", "wait", "scroll"):
                            log.warning("step %d/%d: LLM repeated a failed action (%s), re-querying", step_i, max_steps, action.type)
                            action = next_action_for_shot(
                                client=client,
                                model=model,
                                base_url=cfg.base_url,
                                current_url=page.url,
                                goal_description=shot.description,
                                preview_png_bytes=source_png,
                                step_index=step_i,
                                history=shot_history,
                                carry_note="Your previous suggestion was IDENTICAL to an action that already failed. You MUST pick a different approach.",
                                page_context=page_ctx,
                            )

                        log.info("step %d/%d: executing action type=%s reason=%s", step_i, max_steps, action.type, action.reason[:80] if action.reason else "")
                        url_before = page.url
                        outcome = _execute_action(page, action, timeout_ms=action_timeout_ms, nav_timeout_ms=timeout_ms)
                        log.info("step %d/%d: action result ok=%s error=%s", step_i, max_steps, outcome.ok, outcome.error or "")
                        wait_until_stable(page, timeout_ms=timeout_ms)

                        shot_history.append(
                            {
                                "step": step_i,
                                "url_before": url_before,
                                "url_after": page.url,
                                "action": action.__dict__,
                                "outcome": {"ok": outcome.ok, "error": outcome.error, "extra": outcome.extra},
                            }
                        )

                        if action.type == "done":
                            acquired = True
                            log.info("LLM says done")
                            break
                        if action.type == "fail":
                            raise RuntimeError(f"LLM failed: {action.reason}")

                    if not acquired:
                        raise RuntimeError(f"Failed to acquire shot within {max_steps} steps.")

                    # Final capture
                    log.info("final capture")
                    wait_until_stable(page, timeout_ms=timeout_ms)
                    final_source = page.screenshot(full_page=vp.full_page)
                    final_url = page.url

                    if not same_origin(cfg.base_url, final_url):
                        raise RuntimeError(f"Final URL moved cross-origin unexpectedly: {final_url}")

                    ts = now_ts()

                    if save_source:
                        sources_dir = group_dir / "sources"
                        _ensure_dir(sources_dir)
                        (sources_dir / f"{safe_filename(shot.id)}-{ts}-source.png").write_bytes(final_source)

                    out_bytes = final_source

                    # Optional crop with validation loop
                    if use_llm and use_llm_crop:
                        from .llm import pick_crop, validate_crop

                        log.info("requesting LLM crop")
                        full_w, full_h = get_png_size(final_source)
                        preview_bytes, preview_w, preview_h, scale_factor = downscale_png(final_source, max_w=1280)
                        log.info("crop preview: %dx%d (scale=%.3f from %dx%d)", preview_w, preview_h, scale_factor, full_w, full_h)

                        rejection_reason = ""
                        for crop_attempt in range(1, max_crop_retries + 1):
                            log.info("crop attempt %d/%d", crop_attempt, max_crop_retries)
                            crop = pick_crop(
                                client=client,
                                model=model,
                                base_url=cfg.base_url,
                                current_url=final_url,
                                preview_png_bytes=preview_bytes,
                                preview_w=preview_w,
                                preview_h=preview_h,
                                goal_description=shot.description,
                                rejection_reason=rejection_reason,
                            )
                            if crop is None:
                                log.warning("LLM returned no crop, using full image")
                                break

                            if scale_factor < 1.0:
                                inv = 1.0 / scale_factor
                                fx, fy, fw, fh = clamp_crop(
                                    int(crop.x * inv), int(crop.y * inv),
                                    int(crop.w * inv), int(crop.h * inv),
                                    full_w, full_h,
                                )
                            else:
                                fx, fy, fw, fh = clamp_crop(crop.x, crop.y, crop.w, crop.h, full_w, full_h)

                            out_bytes = crop_png(final_source, Crop(fx, fy, fw, fh, crop.rationale))
                            log.info("cropped to %dx%d at (%d,%d): %s", fw, fh, fx, fy, crop.rationale[:80])

                            validation = validate_crop(
                                client=client,
                                model=model,
                                cropped_png_bytes=out_bytes,
                                goal_description=shot.description,
                            )
                            if validation.ok:
                                log.info("crop validation passed")
                                break
                            else:
                                log.warning("crop validation failed: %s", validation.reason)
                                rejection_reason = validation.reason
                        else:
                            log.warning("exhausted %d crop retries, using last attempt", max_crop_retries)

                    # Apply label if configured
                    label_template = shot.label or group.label
                    if label_template:
                        label_text = render_label(label_template, {
                            "url": desensitize_url(final_url, cfg.base_url),
                            "id": shot.id,
                            "title": shot.description.strip()[:80],
                        })
                        if group.label_date:
                            from datetime import datetime, timezone
                            label_text += "\n" + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                        out_bytes = add_label_banner(out_bytes, label_text)
                        log.info("added label: %s", label_text.replace("\n", " | "))

                    # Save individual shot PNG
                    shot_png_path = group_dir / f"{safe_filename(shot.id)}.png"
                    shot_png_path.write_bytes(out_bytes)
                    group_pngs.append(out_bytes)

                    group_report["shots"].append(
                        {
                            "id": shot.id,
                            "status": "ok",
                            "output": str(shot_png_path),
                            "final_url": final_url,
                            "viewport": {"width": vp.width, "height": vp.height, "scale": vp.scale, "full_page": vp.full_page},
                            "history_tail": shot_history[-25:],
                        }
                    )

                    log.info("[OK] %s -> %s", shot.id, shot_png_path)
                    print(f"[OK] {shot.id} -> {shot_png_path}")

                except Exception as e:
                    log.error("[ERROR] %s: %s", shot.id, e)
                    group_report["shots"].append({"id": shot.id, "status": "error", "error": str(e), "final_url": final_url, "history_tail": shot_history[-25:]})
                    print(f"[ERROR] {shot.id}: {e}")
                    group_ok = False

                finally:
                    context.close()

            # Group output assembly
            if group_ok and group_pngs:
                if group.output == "pdf":
                    pdf_path = group_dir / "output.pdf"
                    pdf_bytes = pngs_to_pdf(group_pngs)
                    pdf_path.write_bytes(pdf_bytes)
                    group_report["output_file"] = str(pdf_path)
                    log.info("[OK] group %s -> %s (%d pages)", group.id, pdf_path, len(group_pngs))
                    print(f"[OK] group {group.id} -> {pdf_path} ({len(group_pngs)} pages)")
                else:
                    # png mode — single shot, symlink or copy as output.png
                    output_path = group_dir / "output.png"
                    if output_path.exists():
                        prev_dir = group_dir / "previous"
                        _ensure_dir(prev_dir)
                        prev_path = prev_dir / f"{safe_filename(group.id)}-{now_ts()}.png"
                        output_path.rename(prev_path)
                    output_path.write_bytes(group_pngs[0])
                    group_report["output_file"] = str(output_path)

            report["groups"].append(group_report)

        browser.close()

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Report written to %s", report_path)
    log.info("Log written to %s", out_dir / "shots.log")
    return report_path
