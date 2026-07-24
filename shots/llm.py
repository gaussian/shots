from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from .image_ops import Crop, b64_png
from .utils import is_http_url, same_origin

log = logging.getLogger("shots.llm")


def llm_available() -> bool:
    try:
        import openai

        return True
    except Exception:
        return False


def make_openai_client() -> Any:
    from openai import OpenAI  # type: ignore

    return OpenAI()


@dataclass
class NavAction:
    """
    Single step per loop; may include repeat for "click 3 times".
    """

    type: str  # goto | click_role | click_text | type_text | press_key | scroll | wait | done | fail
    reason: str = ""

    url: str | None = None
    ms: int | None = None

    role: str | None = None
    name: str | None = None
    text: str | None = None
    nth: int | None = None

    repeat: int = 1

    selector: str | None = None
    input_text: str | None = None

    key: str | None = None
    scroll_y: int | None = None

    next_prompt: str | None = None


def _parse_action(raw: str) -> NavAction:
    obj = json.loads(raw)
    t = str(obj.get("type", "")).strip()
    return NavAction(
        type=t,
        reason=str(obj.get("reason", ""))[:400],
        url=str(obj["url"]) if obj.get("url") else None,
        ms=int(obj["ms"]) if obj.get("ms") is not None else None,
        role=str(obj["role"]) if obj.get("role") else None,
        name=str(obj["name"]) if obj.get("name") else None,
        text=str(obj["text"]) if obj.get("text") else None,
        nth=int(obj["nth"]) if obj.get("nth") is not None else None,
        repeat=int(obj.get("repeat", 1) or 1),
        selector=str(obj["selector"]) if obj.get("selector") else None,
        input_text=str(obj["input_text"]) if obj.get("input_text") else None,
        key=str(obj["key"]) if obj.get("key") else None,
        scroll_y=int(obj["scroll_y"]) if obj.get("scroll_y") is not None else None,
        next_prompt=str(obj["next_prompt"])[:400] if obj.get("next_prompt") else None,
    )


def _summarize_failures(history: list[dict[str, Any]]) -> str:
    """Build a short summary of failed actions so the LLM doesn't repeat them."""
    lines: list[str] = []
    for h in history:
        outcome = h.get("outcome") or {}
        if outcome.get("ok"):
            continue
        act = h.get("action") or {}
        t = act.get("type", "?")
        parts = [t]
        if act.get("role"):
            parts.append(f"role={act['role']}")
        if act.get("name"):
            parts.append(f'name="{act["name"]}"')
        if act.get("text"):
            parts.append(f'text="{act["text"]}"')
        if act.get("selector"):
            parts.append(f'selector="{act["selector"]}"')
        if act.get("url") and t == "goto":
            parts.append(f"url={act['url']}")
        err = str(outcome.get("error", ""))[:80]
        lines.append(f"- {' '.join(parts)} → {err}")
    return "\n".join(lines)


def _action_signature(action: NavAction) -> tuple:
    """Key fields that identify what an action targets (for dedup)."""
    return (action.type, action.role, action.name, action.text, action.selector, action.url)


def failed_signatures(history: list[dict[str, Any]]) -> set[tuple]:
    """Return the set of action signatures that have already failed."""
    sigs: set[tuple] = set()
    for h in history:
        outcome = h.get("outcome") or {}
        if outcome.get("ok"):
            continue
        act = h.get("action") or {}
        sigs.add(
            (
                act.get("type"),
                act.get("role"),
                act.get("name"),
                act.get("text"),
                act.get("selector"),
                act.get("url"),
            )
        )
    return sigs


def next_action_for_shot(
    client: Any,
    model: str,
    base_url: str,
    current_url: str,
    goal_description: str,
    preview_png_bytes: bytes,
    step_index: int,
    history: list[dict[str, Any]],
    carry_note: str = "",
    page_context: str = "",
) -> NavAction:
    """
    Vision model chooses ONE next action toward achieving the described screenshot.
    """
    system = (
        "You are driving a browser to acquire a REQUIRED marketing screenshot of a SaaS app.\n"
        "Return ONLY valid JSON with keys:\n"
        "type, reason, url, role, name, text, nth, repeat, selector, input_text, key, scroll_y, ms, next_prompt.\n\n"
        "Allowed types:\n"
        "- goto: provide absolute url\n"
        "- click_role: provide role + name (accessible name)\n"
        "- click_text: provide text (best effort)\n"
        "- type_text: provide selector (optional) and input_text\n"
        "- press_key: provide key\n"
        "- scroll: provide scroll_y\n"
        "- wait: provide ms\n"
        "- done\n"
        "- fail\n\n"
        "Rules:\n"
        f"- Stay same-origin as base_url={base_url}.\n"
        "- Prefer click_role over click_text.\n"
        "- Prefer repeat over returning multiple actions.\n"
        "- If modals/tours/cookie banners block UI, close/dismiss them.\n"
        "- Keep actions small and safe.\n"
        "- NEVER repeat an action that already failed. If click_role/click_text timed out, the element likely doesn't exist with that name — try a different locator, use goto with a direct URL, or try click_text instead of click_role.\n"
        "- Use the PAGE ELEMENTS list to find exact role names, link text, and href URLs. Do NOT guess URLs — use the hrefs shown in the page context.\n"
    )

    failures = _summarize_failures(history)
    failure_block = f"\nFAILED ACTIONS (do NOT repeat these):\n{failures}\n" if failures else ""
    context_block = f"\nPAGE ELEMENTS:\n{page_context}\n" if page_context else ""

    user_text = (
        f"Step {step_index}\n"
        f"Current URL: {current_url}\n\n"
        f"SHOT GOAL:\n{goal_description}\n\n"
        f"Carry note (if any): {carry_note}\n"
        f"{context_block}"
        f"{failure_block}\n"
        f"Recent history:\n{json.dumps(history[-5:], indent=2)}"
    )

    log.info("LLM nav request: model=%s step=%d url=%s", model, step_index, current_url)
    log.debug("LLM prompt:\n%s", user_text)

    t0 = time.monotonic()
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{b64_png(preview_png_bytes)}"},
                ],
            },
        ],
    )
    elapsed = time.monotonic() - t0

    raw = (resp.output_text or "").strip()
    log.info("LLM nav response (%.1fs): %s", elapsed, raw)

    action = _parse_action(raw)

    # Safety: enforce same-origin for goto
    if action.type == "goto" and action.url:
        if not (is_http_url(action.url) and same_origin(base_url, action.url)):
            log.warning("Rejected cross-origin goto: %s", action.url)
            return NavAction(type="wait", ms=700, reason="Rejected cross-origin/invalid goto URL; waiting.")

    # Clamp repeat
    if action.repeat < 1:
        action.repeat = 1
    if action.repeat > 10:
        action.repeat = 10

    return action


@dataclass
class CropValidation:
    ok: bool
    reason: str = ""


def pick_crop(
    client: Any,
    model: str,
    base_url: str,
    current_url: str,
    preview_png_bytes: bytes,
    preview_w: int,
    preview_h: int,
    goal_description: str = "",
    rejection_reason: str = "",
) -> Crop | None:
    """
    Vision model chooses a crop rectangle on the preview image.
    Returns None if it decides the page is not presentable.
    """
    goal_hint = f"The screenshot goal is: {goal_description}\n" if goal_description else ""
    rejection_block = ""
    if rejection_reason:
        rejection_block = (
            f"\nPREVIOUS CROP WAS REJECTED: {rejection_reason}\n"
            "Choose a LARGER area that includes the missing content.\n"
        )
    system = (
        "You are selecting a marketing screenshot crop.\n"
        "Return ONLY valid JSON with keys: x, y, w, h (integers), rationale (string).\n\n"
        f"The image is {preview_w}x{preview_h} pixels.\n"
        f"{goal_hint}"
        "Rules:\n"
        "- Choose a crop that highlights the specific UI described in the goal.\n"
        "- CRITICAL: Do NOT cut off any text or labels. Include ALL content described in the goal.\n"
        "- Include generous margins — it is FAR better to include a little extra than to cut off any content.\n"
        "- Make sure field labels on the left side are fully visible (not clipped).\n"
        "- Make sure all content at the bottom of the target area is included.\n"
        "- Exclude navigation bars, sidebars, and clearly unrelated UI sections.\n"
        "- Avoid modals, cookie banners, toasts.\n"
        "- Keep within bounds.\n"
        "- If not presentable, return x=y=w=h=0.\n"
    )

    user_text = f"base_url={base_url}\ncurrent_url={current_url}{rejection_block}"

    log.info(
        "LLM crop request: model=%s url=%s (%dx%d)%s",
        model,
        current_url,
        preview_w,
        preview_h,
        " (retry)" if rejection_reason else "",
    )

    t0 = time.monotonic()
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{b64_png(preview_png_bytes)}"},
                ],
            },
        ],
    )
    elapsed = time.monotonic() - t0

    raw = (resp.output_text or "").strip()
    log.info("LLM crop response (%.1fs): %s", elapsed, raw)

    try:
        obj = json.loads(raw)
        x = int(obj.get("x", 0))
        y = int(obj.get("y", 0))
        w = int(obj.get("w", 0))
        h = int(obj.get("h", 0))
        rationale = str(obj.get("rationale", ""))[:400]
        if x == 0 and y == 0 and w == 0 and h == 0:
            return None
        return Crop(x=x, y=y, w=w, h=h, rationale=rationale)
    except Exception:
        log.warning("Failed to parse crop response: %s", raw)
        return None


def validate_crop(
    client: Any,
    model: str,
    cropped_png_bytes: bytes,
    goal_description: str,
) -> CropValidation:
    """
    Ask the LLM whether the cropped image fully satisfies the goal.
    """
    system = (
        "You are reviewing a cropped screenshot for a marketing image.\n"
        "Return ONLY valid JSON with keys: ok (boolean), reason (string).\n\n"
        "Check whether the cropped image contains all the VISUAL CONTENT described in the goal.\n"
        "Focus ONLY on whether the described UI elements, fields, and data are visible and not clipped.\n"
        "IGNORE navigation instructions in the goal (URLs, click instructions, scroll instructions) — "
        "those are for the browser operator, not for the screenshot content.\n"
        "Set ok=true if all described visual content is visible and not clipped.\n"
        "Set ok=false ONLY if actual UI content (fields, labels, data) is missing or cut off.\n"
        "When ok=false, explain specifically what visual content is missing or clipped.\n"
    )

    user_text = f"GOAL:\n{goal_description}"

    log.info("LLM crop validation request")

    t0 = time.monotonic()
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_text},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{b64_png(cropped_png_bytes)}"},
                ],
            },
        ],
    )
    elapsed = time.monotonic() - t0

    raw = (resp.output_text or "").strip()
    log.info("LLM crop validation response (%.1fs): %s", elapsed, raw)

    try:
        obj = json.loads(raw)
        ok = bool(obj.get("ok", False))
        reason = str(obj.get("reason", ""))[:400]
        return CropValidation(ok=ok, reason=reason)
    except Exception:
        log.warning("Failed to parse crop validation response: %s", raw)
        return CropValidation(ok=True, reason="")
