from __future__ import annotations

from dataclasses import dataclass

VIEWPORT_PRESETS: dict[str, dict[str, int | bool]] = {
    "desktop": {"width": 1920, "height": 1080, "scale": 2, "full_page": True},
    "laptop": {"width": 1440, "height": 900, "scale": 2, "full_page": True},
    "tablet": {"width": 834, "height": 1112, "scale": 2, "full_page": True},
    "mobile": {"width": 390, "height": 844, "scale": 3, "full_page": True},
}


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int
    scale: int
    full_page: bool


def viewport_from_preset(preset: str, full_page_override: bool | None = None) -> Viewport:
    vp = VIEWPORT_PRESETS.get(preset)
    if not vp:
        raise ValueError(f"Unknown viewport preset: {preset}")
    full_page = bool(vp["full_page"]) if full_page_override is None else bool(full_page_override)
    return Viewport(width=int(vp["width"]), height=int(vp["height"]), scale=int(vp["scale"]), full_page=full_page)


def viewport_from_values(width: int, height: int, scale: int, full_page: bool) -> Viewport:
    return Viewport(width=int(width), height=int(height), scale=int(scale), full_page=bool(full_page))
