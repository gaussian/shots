"""Tests for shots.image_ops: label banners, PDF assembly, and font resolution."""

from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from shots.image_ops import _get_font, add_label_banner, pngs_to_pdf


class TestGetFont:
    def test_returns_usable_font(self):
        font = _get_font(24)
        assert font is not None

    def test_different_sizes_return_font(self):
        small = _get_font(10)
        large = _get_font(48)
        assert small is not None
        assert large is not None


class TestAddLabelBanner:
    def test_output_is_taller_than_input(self, sample_png_bytes: bytes):
        original = Image.open(BytesIO(sample_png_bytes))
        result = add_label_banner(sample_png_bytes, "Hello world")
        out_img = Image.open(BytesIO(result))
        assert out_img.height > original.height
        assert out_img.width == original.width

    def test_output_is_valid_png(self, sample_png_bytes: bytes):
        result = add_label_banner(sample_png_bytes, "Label text")
        img = Image.open(BytesIO(result))
        assert img.format == "PNG"

    def test_multiline_label_taller_than_single_line(self, sample_png_bytes: bytes):
        single = add_label_banner(sample_png_bytes, "One line")
        multi = add_label_banner(sample_png_bytes, "One line\nTwo lines")
        single_img = Image.open(BytesIO(single))
        multi_img = Image.open(BytesIO(multi))
        assert multi_img.height > single_img.height

    def test_larger_font_size_increases_banner_height(self, sample_png_bytes: bytes):
        small_font = add_label_banner(sample_png_bytes, "Label", font_size=16)
        large_font = add_label_banner(sample_png_bytes, "Label", font_size=64)
        small_img = Image.open(BytesIO(small_font))
        large_img = Image.open(BytesIO(large_font))
        assert large_img.height > small_img.height

    def test_empty_label_still_produces_valid_image(self, sample_png_bytes: bytes):
        result = add_label_banner(sample_png_bytes, "")
        img = Image.open(BytesIO(result))
        assert img.format == "PNG"


class TestPngsToPdf:
    def test_single_image_pdf(self, sample_png_bytes: bytes):
        result = pngs_to_pdf([sample_png_bytes])
        assert result[:5] == b"%PDF-"

    def test_multi_image_pdf(self, sample_png_bytes: bytes, large_png_bytes: bytes):
        result = pngs_to_pdf([sample_png_bytes, large_png_bytes])
        assert result[:5] == b"%PDF-"

    def test_pdf_bytes_nonempty(self, sample_png_bytes: bytes):
        result = pngs_to_pdf([sample_png_bytes])
        assert len(result) > 0

    def test_raises_on_empty_list(self):
        with pytest.raises(IndexError):
            pngs_to_pdf([])
