from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO

from PIL import Image


def b64_png(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("utf-8")


@dataclass(frozen=True)
class Crop:
    x: int
    y: int
    w: int
    h: int
    rationale: str = ""


def clamp_crop(x: int, y: int, w: int, h: int, W: int, H: int) -> tuple[int, int, int, int]:
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = max(1, min(w, W - x))
    h = max(1, min(h, H - y))
    return x, y, w, h


def downscale_png(png_bytes: bytes, max_w: int = 1000) -> tuple[bytes, int, int, float]:
    """
    Returns (preview_png_bytes, preview_w, preview_h, scale_factor)
    scale_factor = preview_w / full_w
    """
    im = Image.open(BytesIO(png_bytes)).convert("RGBA")
    full_w, full_h = im.size

    if full_w <= max_w:
        buf = BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue(), full_w, full_h, 1.0

    scale = max_w / float(full_w)
    new_w = max_w
    new_h = int(full_h * scale)

    preview = im.resize((new_w, new_h), resample=Image.LANCZOS)
    buf = BytesIO()
    preview.save(buf, format="PNG")
    return buf.getvalue(), new_w, new_h, scale


def crop_png(png_bytes: bytes, crop: Crop) -> bytes:
    im = Image.open(BytesIO(png_bytes)).convert("RGBA")
    W, H = im.size
    x, y, w, h = clamp_crop(crop.x, crop.y, crop.w, crop.h, W, H)
    out = im.crop((x, y, x + w, y + h))
    buf = BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def get_png_size(png_bytes: bytes) -> tuple[int, int]:
    im = Image.open(BytesIO(png_bytes))
    return im.size
