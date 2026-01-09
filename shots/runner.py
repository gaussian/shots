from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from playwright.sync_api import BrowserContext, Page, sync_playwright

from .config import RunConfig, ShotSpec
from .image_ops import Crop, clamp_crop, crop_png, downscale_png, get_png_size
from .stability import wait_until_stable
from .utils import StepOutcome, normalize_url, now_ts, safe_filename, same_origin
from .viewport import Viewport, viewport_from_preset, viewport_from_values


def _ensure_dir(p: pathlib.Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _resolve_viewport_for_shot(defaults: Dict[str, Any], shot: ShotSpec, fallback: Viewport) -> Viewport:
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
        print("4) Return here and press ENTER.\n")
        input("Press ENTER when you are fully logged in... ")

        context.storage_state(path=str(state_path))
        print(f"Saved auth state: {state_path}")

        context.close()
        browser.close()

    return state_path


def _execute_action(page: Page, action: Any, timeout_ms: int) -> StepOutcome:
    """
    Executes one action with optional repeat. Returns StepOutcome (ok/error).
    Action is expected to be llm.NavAction.
    """
    from .llm import NavAction  # local import to keep deps clean

    if not isinstance(action, NavAction):
        return StepOutcome(ok=False, error="Invalid action type.")

    def do_once() -> None:
        if action.type == "goto" and action.url:
            page.goto(action.url, wait_until="domcontentloaded", timeout=timeout_ms)
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


def _pick_carry_note(history: List[Dict[str, Any]]) -> str:
    for h in reversed(history):
        act = h.get("action") or {}
        np = act.get("next_prompt")
        if isinstance(np, str) and np.strip():
            return np.strip()
    return ""


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
    headed: bool,
    use_llm: bool,
    model: str,
    use_llm_crop: bool,
    save_source: bool,
    cli_fallback_viewport: Viewport,
) -> pathlib.Path:
    """
    Runs required screenshots from config file.
    If use_llm: LLM drives multi-step actions until it returns done.
    """
    _ensure_dir(out_dir)
    state_path = _auth_state_path(out_dir)
    if not state_path.exists():
        raise RuntimeError(f"Missing {state_path}. Run: shots login --base-url {cfg.base_url} --out-dir {out_dir}")

    client = None
    if use_llm:
        from .llm import make_openai_client
        client = make_openai_client()

    report: Dict[str, Any] = {"base_url": cfg.base_url, "shots": [], "config": None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)

        for idx, shot in enumerate(cfg.shots, start=1):
            vp = _resolve_viewport_for_shot(cfg.defaults, shot, cli_fallback_viewport)

            # New context per shot so scale can vary.
            context = browser.new_context(
                storage_state=str(state_path),
                viewport={"width": vp.width, "height": vp.height},
                device_scale_factor=vp.scale,
            )
            page = context.new_page()

            shot_history: List[Dict[str, Any]] = []
            final_url = ""
            output_path: Optional[pathlib.Path] = None

            try:
                # Choose initial URL: shot.url else config.start
                start = shot.url or cfg.start
                start_url = _absolutize(cfg.base_url, start)
                start_url = normalize_url(start_url)

                page.goto(start_url, wait_until="domcontentloaded", timeout=timeout_ms)
                wait_until_stable(page, timeout_ms=timeout_ms)

                max_steps = int(cfg.defaults.get("max_nav_steps", 12))

                if not use_llm and not shot.url:
                    raise RuntimeError("Shot has no url and --use-llm is false; cannot acquire from description.")

                acquired = False
                for step_i in range(1, max_steps + 1):
                    wait_until_stable(page, timeout_ms=timeout_ms)

                    # Source screenshot (for eventual crop & debugging)
                    source_png = page.screenshot(full_page=vp.full_page)

                    # Downscale for LLM
                    preview_png, pw, ph, scale = downscale_png(source_png, max_w=1000)

                    if not use_llm:
                        acquired = True
                        break

                    from .llm import next_action_for_shot

                    carry_note = _pick_carry_note(shot_history)
                    action = next_action_for_shot(
                        client=client,
                        model=model,
                        base_url=cfg.base_url,
                        current_url=page.url,
                        goal_description=shot.description,
                        preview_png_bytes=preview_png,
                        step_index=step_i,
                        history=shot_history,
                        carry_note=carry_note,
                    )

                    url_before = page.url
                    outcome = _execute_action(page, action, timeout_ms=timeout_ms)
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
                        break
                    if action.type == "fail":
                        raise RuntimeError(f"LLM failed: {action.reason}")

                if not acquired:
                    raise RuntimeError(f"Failed to acquire shot within {max_steps} steps.")

                # Final capture (stable)
                wait_until_stable(page, timeout_ms=timeout_ms)
                final_source = page.screenshot(full_page=vp.full_page)
                final_url = page.url

                if not same_origin(cfg.base_url, final_url):
                    raise RuntimeError(f"Final URL moved cross-origin unexpectedly: {final_url}")

                ts = now_ts()
                base_name = f"{idx:02d}-{safe_filename(shot.id)}-{ts}"

                if save_source:
                    (out_dir / f"{base_name}-source.png").write_bytes(final_source)

                out_bytes = final_source

                # Optional crop
                if use_llm and use_llm_crop:
                    from .llm import pick_crop

                    preview_png, pw, ph, sc = downscale_png(final_source, max_w=1000)
                    crop = pick_crop(
                        client=client,
                        model=model,
                        base_url=cfg.base_url,
                        current_url=final_url,
                        preview_png_bytes=preview_png,
                        preview_w=pw,
                        preview_h=ph,
                    )
                    if crop is not None:
                        full_w, full_h = get_png_size(final_source)
                        inv = 1.0 / sc
                        fx = int(round(crop.x * inv))
                        fy = int(round(crop.y * inv))
                        fw = int(round(crop.w * inv))
                        fh = int(round(crop.h * inv))
                        fx, fy, fw, fh = clamp_crop(fx, fy, fw, fh, full_w, full_h)
                        out_bytes = crop_png(final_source, Crop(fx, fy, fw, fh, crop.rationale))

                output_path = out_dir / f"{base_name}.png"
                output_path.write_bytes(out_bytes)

                report["shots"].append(
                    {
                        "id": shot.id,
                        "status": "ok",
                        "output": str(output_path),
                        "final_url": final_url,
                        "viewport": {"width": vp.width, "height": vp.height, "scale": vp.scale, "full_page": vp.full_page},
                        "history_tail": shot_history[-25:],
                    }
                )

                print(f"[OK] {shot.id} -> {output_path}")

            except Exception as e:
                report["shots"].append({"id": shot.id, "status": "error", "error": str(e), "final_url": final_url})
                print(f"[ERROR] {shot.id}: {e}")

            finally:
                context.close()

        browser.close()

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path
