from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .image_ops import Crop, b64_png
from .utils import is_http_url, same_origin


def llm_available() -> bool:
    try:
        import openai  # noqa: F401

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
    )

    user_text = (
        f"Step {step_index}\n"
        f"Current URL: {current_url}\n\n"
        f"SHOT GOAL:\n{goal_description}\n\n"
        f"Carry note (if any): {carry_note}\n\n"
        f"Recent history:\n{json.dumps(history[-10:], indent=2)}"
    )

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

    raw = (resp.output_text or "").strip()
    action = _parse_action(raw)

    # Safety: enforce same-origin for goto
    if action.type == "goto" and action.url:
        if not (is_http_url(action.url) and same_origin(base_url, action.url)):
            return NavAction(type="wait", ms=700, reason="Rejected cross-origin/invalid goto URL; waiting.")

    # Clamp repeat
    if action.repeat < 1:
        action.repeat = 1
    if action.repeat > 10:
        action.repeat = 10

    return action


def pick_crop(
    client: Any,
    model: str,
    base_url: str,
    current_url: str,
    preview_png_bytes: bytes,
    preview_w: int,
    preview_h: int,
) -> Crop | None:
    """
    Vision model chooses a crop rectangle on the preview image.
    Returns None if it decides the page is not presentable.
    """
    system = (
        "You are selecting a marketing screenshot crop.\n"
        "Return ONLY valid JSON with keys: x, y, w, h (integers), rationale (string).\n\n"
        f"The image is {preview_w}x{preview_h} pixels.\n"
        "Rules:\n"
        "- Choose a crop that highlights the primary value/UI.\n"
        "- Avoid modals, cookie banners, toasts, empty whitespace.\n"
        "- Prefer aspect close to 16:9 or 3:2 when reasonable.\n"
        "- Keep within bounds.\n"
        "- If not presentable, return x=y=w=h=0.\n"
    )

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": f"base_url={base_url}\ncurrent_url={current_url}"},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{b64_png(preview_png_bytes)}"},
                ],
            },
        ],
    )

    raw = (resp.output_text or "").strip()
    try:
        obj = json.loads(raw)
        x = int(obj.get("x", 0))
        y = int(obj.get("y", 0))
        w = int(obj.get("w", 0))
        h = int(obj.get("h", 0))
        rationale = str(obj.get("rationale", ""))[:400]
        if x == 0 and y == 0 and w == 0 and h == 0:
            return None
        # We'll clamp later at the caller.
        return Crop(x=x, y=y, w=w, h=h, rationale=rationale)
    except Exception:
        return None
