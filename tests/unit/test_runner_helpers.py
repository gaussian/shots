"""Tests for pure/non-Playwright shots.runner helper functions."""

from __future__ import annotations

import pathlib

from shots.config import ShotSpec
from shots.runner import (
    _absolutize,
    _auth_state_path,
    _ensure_dir,
    _pick_carry_note,
    _resolve_viewport_for_shot,
)
from shots.viewport import Viewport


class TestAuthStatePath:
    def test_returns_storage_state_json_under_out_dir(self):
        out_dir = pathlib.Path("/tmp/some_out")
        result = _auth_state_path(out_dir)
        assert result == out_dir / "storage_state.json"


class TestEnsureDir:
    def test_creates_directory(self, tmp_path: pathlib.Path):
        target = tmp_path / "nested" / "dir"
        assert not target.exists()
        _ensure_dir(target)
        assert target.exists()
        assert target.is_dir()

    def test_idempotent_on_existing_dir(self, tmp_path: pathlib.Path):
        target = tmp_path / "already"
        target.mkdir()
        _ensure_dir(target)  # should not raise
        assert target.exists()


class TestAbsolutize:
    def test_absolute_http_url_returned_as_is(self):
        assert _absolutize("https://example.com", "http://other.com/x") == "http://other.com/x"

    def test_absolute_https_url_returned_as_is(self):
        assert _absolutize("https://example.com", "https://example.com/page") == "https://example.com/page"

    def test_leading_slash_path_joined_to_base(self):
        assert _absolutize("https://example.com", "/dashboard") == "https://example.com/dashboard"

    def test_relative_path_joined_to_base(self):
        assert _absolutize("https://example.com", "dashboard") == "https://example.com/dashboard"

    def test_leading_slash_with_trailing_slash_base(self):
        result = _absolutize("https://example.com", "/a/b")
        assert result == "https://example.com/a/b"


class TestResolveViewportForShot:
    def make_fallback(self) -> Viewport:
        return Viewport(width=1280, height=720, scale=1, full_page=True)

    def test_uses_shot_viewport_dict(self):
        shot = ShotSpec(id="s", description="d", viewport={"width": 800, "height": 600, "scale": 2})
        vp = _resolve_viewport_for_shot({}, shot, self.make_fallback())
        assert vp.width == 800
        assert vp.height == 600
        assert vp.scale == 2

    def test_shot_viewport_dict_falls_back_for_missing_keys(self):
        shot = ShotSpec(id="s", description="d", viewport={"width": 800})
        fallback = self.make_fallback()
        vp = _resolve_viewport_for_shot({}, shot, fallback)
        assert vp.width == 800
        assert vp.height == fallback.height
        assert vp.scale == fallback.scale

    def test_uses_viewport_preset_from_shot(self):
        shot = ShotSpec(id="s", description="d", viewport_preset="mobile")
        vp = _resolve_viewport_for_shot({}, shot, self.make_fallback())
        assert vp.width == 390
        assert vp.height == 844

    def test_uses_viewport_preset_from_defaults(self):
        shot = ShotSpec(id="s", description="d")
        vp = _resolve_viewport_for_shot({"viewport_preset": "tablet"}, shot, self.make_fallback())
        assert vp.width == 834
        assert vp.height == 1112

    def test_falls_back_to_cli_viewport(self):
        shot = ShotSpec(id="s", description="d")
        fallback = self.make_fallback()
        vp = _resolve_viewport_for_shot({}, shot, fallback)
        assert vp.width == fallback.width
        assert vp.height == fallback.height
        assert vp.scale == fallback.scale

    def test_shot_full_page_overrides_defaults(self):
        shot = ShotSpec(id="s", description="d", full_page=False)
        vp = _resolve_viewport_for_shot({"full_page": True}, shot, self.make_fallback())
        assert vp.full_page is False

    def test_defaults_full_page_used_when_shot_unset(self):
        shot = ShotSpec(id="s", description="d")
        vp = _resolve_viewport_for_shot({"full_page": False}, shot, self.make_fallback())
        assert vp.full_page is False

    def test_fallback_full_page_used_when_nothing_else_set(self):
        shot = ShotSpec(id="s", description="d")
        fallback = Viewport(width=100, height=100, scale=1, full_page=False)
        vp = _resolve_viewport_for_shot({}, shot, fallback)
        assert vp.full_page is False


class TestPickCarryNote:
    def test_empty_history_returns_empty_string(self):
        assert _pick_carry_note([]) == ""

    def test_no_next_prompt_returns_empty_string(self):
        history = [{"action": {"type": "click_role"}}]
        assert _pick_carry_note(history) == ""

    def test_returns_most_recent_next_prompt(self):
        history = [
            {"action": {"next_prompt": "first note"}},
            {"action": {"next_prompt": "second note"}},
        ]
        assert _pick_carry_note(history) == "second note"

    def test_skips_blank_next_prompt_and_finds_earlier(self):
        history = [
            {"action": {"next_prompt": "real note"}},
            {"action": {"next_prompt": "   "}},
        ]
        assert _pick_carry_note(history) == "real note"

    def test_missing_action_key_handled(self):
        history = [{"outcome": {"ok": True}}]
        assert _pick_carry_note(history) == ""

    def test_strips_whitespace(self):
        history = [{"action": {"next_prompt": "  padded  "}}]
        assert _pick_carry_note(history) == "padded"
