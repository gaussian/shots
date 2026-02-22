from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


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


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try common system sans-serif fonts, fall back to Pillow default."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "arial.ttf",
        "DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default(size=size)


def add_label_banner(png_bytes: bytes, label_text: str, font_size: int = 32) -> bytes:
    """
    Add a white banner with black text below the image. Additive — does not
    crop into the screenshot, just extends the canvas downward.
    """
    im = Image.open(BytesIO(png_bytes)).convert("RGBA")
    w, h = im.size

    font = _get_font(font_size)
    padding = font_size // 2
    banner_h = font_size + 2 * padding

    # New canvas: original + banner
    out = Image.new("RGBA", (w, h + banner_h), (255, 255, 255, 255))
    out.paste(im, (0, 0))

    draw = ImageDraw.Draw(out)
    bbox = draw.textbbox((0, 0), label_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_x = (w - text_w) // 2
    text_y = h + padding
    draw.text((text_x, text_y), label_text, fill=(0, 0, 0, 255), font=font)

    buf = BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def pngs_to_pdf(png_bytes_list: list[bytes]) -> bytes:
    """
    Combine multiple PNG images into a single PDF (one image per page).
    Uses Pillow's built-in PDF support — no extra dependencies.
    """
    images: list[Image.Image] = []
    for png_bytes in png_bytes_list:
        im = Image.open(BytesIO(png_bytes)).convert("RGB")
        images.append(im)

    buf = BytesIO()
    if len(images) == 1:
        images[0].save(buf, format="PDF")
    else:
        images[0].save(buf, format="PDF", save_all=True, append_images=images[1:])
    return buf.getvalue()
