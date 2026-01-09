"""Tests for shots.image_ops module."""

from __future__ import annotations

import base64
from io import BytesIO

import pytest
from PIL import Image

from shots.image_ops import (
    Crop,
    b64_png,
    clamp_crop,
    crop_png,
    downscale_png,
    get_png_size,
)


class TestB64Png:
    def test_encodes_to_base64(self, sample_png_bytes: bytes):
        result = b64_png(sample_png_bytes)
        assert isinstance(result, str)
        # Base64 contains only ASCII characters
        assert result.isascii()

    def test_roundtrip(self, sample_png_bytes: bytes):
        encoded = b64_png(sample_png_bytes)
        decoded = base64.b64decode(encoded)
        assert decoded == sample_png_bytes


class TestCrop:
    def test_crop_dataclass(self):
        crop = Crop(x=10, y=20, w=100, h=200, rationale="Test crop")
        assert crop.x == 10
        assert crop.y == 20
        assert crop.w == 100
        assert crop.h == 200
        assert crop.rationale == "Test crop"

    def test_crop_default_rationale(self):
        crop = Crop(x=10, y=20, w=100, h=200)
        assert crop.rationale == ""

    def test_crop_is_frozen(self):
        from dataclasses import FrozenInstanceError

        crop = Crop(x=10, y=20, w=100, h=200)
        with pytest.raises(FrozenInstanceError):
            crop.x = 50  # type: ignore[misc]


class TestClampCrop:
    @pytest.mark.parametrize(
        "x,y,w,h,W,H,expected",
        [
            # Normal case - within bounds
            (10, 10, 50, 50, 100, 100, (10, 10, 50, 50)),
            # x out of bounds (negative)
            (-10, 10, 50, 50, 100, 100, (0, 10, 50, 50)),
            # y out of bounds (negative)
            (10, -10, 50, 50, 100, 100, (10, 0, 50, 50)),
            # x too large
            (200, 10, 50, 50, 100, 100, (99, 10, 1, 50)),
            # Width exceeds available space
            (80, 10, 50, 50, 100, 100, (80, 10, 20, 50)),
            # Height exceeds available space
            (10, 80, 50, 50, 100, 100, (10, 80, 50, 20)),
            # Zero width clamped to 1
            (10, 10, 0, 50, 100, 100, (10, 10, 1, 50)),
            # Zero height clamped to 1
            (10, 10, 50, 0, 100, 100, (10, 10, 50, 1)),
            # Negative width clamped to 1
            (10, 10, -10, 50, 100, 100, (10, 10, 1, 50)),
        ],
    )
    def test_clamp_crop(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        W: int,
        H: int,
        expected: tuple[int, int, int, int],
    ):
        result = clamp_crop(x, y, w, h, W, H)
        assert result == expected


class TestDownscalePng:
    def test_no_downscale_when_small(self, sample_png_bytes: bytes):
        # sample_png_bytes is 100x100
        _, w, h, scale = downscale_png(sample_png_bytes, max_w=1000)
        assert w == 100
        assert h == 100
        assert scale == 1.0

    def test_downscale_when_large(self, large_png_bytes: bytes):
        # large_png_bytes is 2000x1500
        _, w, h, scale = downscale_png(large_png_bytes, max_w=1000)
        assert w == 1000
        assert h == 750  # Proportional: 1500 * (1000/2000)
        assert scale == 0.5

    def test_output_is_valid_png(self, large_png_bytes: bytes):
        result_bytes, _, _, _ = downscale_png(large_png_bytes, max_w=500)
        img = Image.open(BytesIO(result_bytes))
        assert img.format == "PNG"

    def test_returns_new_bytes_even_when_no_resize(self, sample_png_bytes: bytes):
        result_bytes, _, _, _ = downscale_png(sample_png_bytes, max_w=1000)
        # Should return valid PNG bytes
        img = Image.open(BytesIO(result_bytes))
        assert img.format == "PNG"


class TestCropPng:
    def test_crop_produces_correct_size(self, sample_png_bytes: bytes):
        crop = Crop(x=10, y=10, w=50, h=50)
        result = crop_png(sample_png_bytes, crop)
        img = Image.open(BytesIO(result))
        assert img.size == (50, 50)

    def test_crop_clamped_to_image_bounds(self, sample_png_bytes: bytes):
        # Crop extending beyond 100x100 image
        crop = Crop(x=80, y=80, w=100, h=100)
        result = crop_png(sample_png_bytes, crop)
        img = Image.open(BytesIO(result))
        # Should be clamped to 20x20
        assert img.size == (20, 20)

    def test_crop_output_is_png(self, sample_png_bytes: bytes):
        crop = Crop(x=0, y=0, w=50, h=50)
        result = crop_png(sample_png_bytes, crop)
        img = Image.open(BytesIO(result))
        assert img.format == "PNG"


class TestGetPngSize:
    def test_returns_correct_size(self, sample_png_bytes: bytes):
        width, height = get_png_size(sample_png_bytes)
        assert width == 100
        assert height == 100

    def test_large_image_size(self, large_png_bytes: bytes):
        width, height = get_png_size(large_png_bytes)
        assert width == 2000
        assert height == 1500
