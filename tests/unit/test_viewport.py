"""Tests for shots.viewport module."""

from __future__ import annotations

import pytest

from shots.viewport import (
    VIEWPORT_PRESETS,
    Viewport,
    viewport_from_preset,
    viewport_from_values,
)


class TestViewportPresets:
    def test_all_presets_exist(self):
        expected_presets = {"desktop", "laptop", "tablet", "mobile"}
        assert set(VIEWPORT_PRESETS.keys()) == expected_presets

    @pytest.mark.parametrize("preset", VIEWPORT_PRESETS.keys())
    def test_presets_have_required_keys(self, preset: str):
        vp = VIEWPORT_PRESETS[preset]
        assert "width" in vp
        assert "height" in vp
        assert "scale" in vp
        assert "full_page" in vp

    @pytest.mark.parametrize("preset", VIEWPORT_PRESETS.keys())
    def test_presets_have_positive_dimensions(self, preset: str):
        vp = VIEWPORT_PRESETS[preset]
        assert vp["width"] > 0
        assert vp["height"] > 0
        assert vp["scale"] > 0


class TestViewportFromPreset:
    def test_desktop_preset(self):
        vp = viewport_from_preset("desktop")
        assert vp.width == 1920
        assert vp.height == 1080
        assert vp.scale == 2
        assert vp.full_page is True

    def test_laptop_preset(self):
        vp = viewport_from_preset("laptop")
        assert vp.width == 1440
        assert vp.height == 900
        assert vp.scale == 2

    def test_tablet_preset(self):
        vp = viewport_from_preset("tablet")
        assert vp.width == 834
        assert vp.height == 1112
        assert vp.scale == 2

    def test_mobile_preset(self):
        vp = viewport_from_preset("mobile")
        assert vp.width == 390
        assert vp.height == 844
        assert vp.scale == 3

    def test_full_page_override_true(self):
        vp = viewport_from_preset("desktop", full_page_override=True)
        assert vp.full_page is True

    def test_full_page_override_false(self):
        vp = viewport_from_preset("desktop", full_page_override=False)
        assert vp.full_page is False

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown viewport preset"):
            viewport_from_preset("nonexistent")


class TestViewportFromValues:
    def test_creates_viewport(self):
        vp = viewport_from_values(1280, 720, 1, False)
        assert vp.width == 1280
        assert vp.height == 720
        assert vp.scale == 1
        assert vp.full_page is False

    def test_values_are_converted_to_int(self):
        vp = viewport_from_values(1280.5, 720.9, 2.1, True)  # type: ignore[arg-type]
        assert isinstance(vp.width, int)
        assert isinstance(vp.height, int)
        assert isinstance(vp.scale, int)
        assert vp.width == 1280
        assert vp.height == 720
        assert vp.scale == 2


class TestViewportDataclass:
    def test_viewport_is_frozen(self):
        from dataclasses import FrozenInstanceError

        vp = Viewport(width=1920, height=1080, scale=2, full_page=True)
        with pytest.raises(FrozenInstanceError):
            vp.width = 1280  # type: ignore[misc]

    def test_viewport_equality(self):
        vp1 = Viewport(width=1920, height=1080, scale=2, full_page=True)
        vp2 = Viewport(width=1920, height=1080, scale=2, full_page=True)
        assert vp1 == vp2

    def test_viewport_hashable(self):
        vp = Viewport(width=1920, height=1080, scale=2, full_page=True)
        # Should be hashable due to frozen=True
        assert hash(vp) is not None
