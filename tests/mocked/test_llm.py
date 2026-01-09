"""Tests for shots.llm module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from shots.image_ops import Crop
from shots.llm import (
    NavAction,
    _parse_action,
    llm_available,
    next_action_for_shot,
    pick_crop,
)


class TestLlmAvailable:
    def test_returns_bool(self):
        result = llm_available()
        assert isinstance(result, bool)


class TestParseAction:
    def test_parses_goto_action(self):
        raw = '{"type": "goto", "url": "https://example.com/page", "reason": "Navigate"}'
        action = _parse_action(raw)
        assert action.type == "goto"
        assert action.url == "https://example.com/page"
        assert action.reason == "Navigate"

    def test_parses_click_role_action(self):
        raw = '{"type": "click_role", "role": "button", "name": "Submit", "nth": 0}'
        action = _parse_action(raw)
        assert action.type == "click_role"
        assert action.role == "button"
        assert action.name == "Submit"
        assert action.nth == 0

    def test_parses_click_text_action(self):
        raw = '{"type": "click_text", "text": "Click me"}'
        action = _parse_action(raw)
        assert action.type == "click_text"
        assert action.text == "Click me"

    def test_parses_type_text_action(self):
        raw = '{"type": "type_text", "selector": "#input", "input_text": "Hello"}'
        action = _parse_action(raw)
        assert action.type == "type_text"
        assert action.selector == "#input"
        assert action.input_text == "Hello"

    def test_parses_press_key_action(self):
        raw = '{"type": "press_key", "key": "Enter"}'
        action = _parse_action(raw)
        assert action.type == "press_key"
        assert action.key == "Enter"

    def test_parses_scroll_action(self):
        raw = '{"type": "scroll", "scroll_y": 500}'
        action = _parse_action(raw)
        assert action.type == "scroll"
        assert action.scroll_y == 500

    def test_parses_wait_action(self):
        raw = '{"type": "wait", "ms": 1000}'
        action = _parse_action(raw)
        assert action.type == "wait"
        assert action.ms == 1000

    def test_parses_done_action(self):
        raw = '{"type": "done", "reason": "Screenshot acquired"}'
        action = _parse_action(raw)
        assert action.type == "done"
        assert action.reason == "Screenshot acquired"

    def test_parses_fail_action(self):
        raw = '{"type": "fail", "reason": "Cannot proceed"}'
        action = _parse_action(raw)
        assert action.type == "fail"
        assert action.reason == "Cannot proceed"

    def test_parses_repeat(self):
        raw = '{"type": "scroll", "scroll_y": 500, "repeat": 3}'
        action = _parse_action(raw)
        assert action.repeat == 3
        assert action.scroll_y == 500

    def test_default_repeat_is_1(self):
        raw = '{"type": "wait", "ms": 1000}'
        action = _parse_action(raw)
        assert action.repeat == 1

    def test_reason_truncated_to_400_chars(self):
        long_reason = "x" * 500
        raw = json.dumps({"type": "done", "reason": long_reason})
        action = _parse_action(raw)
        assert len(action.reason) == 400

    def test_next_prompt_truncated_to_400_chars(self):
        long_prompt = "x" * 500
        raw = json.dumps({"type": "done", "next_prompt": long_prompt})
        action = _parse_action(raw)
        assert len(action.next_prompt) == 400

    def test_parses_next_prompt(self):
        raw = '{"type": "done", "next_prompt": "Remember this for later"}'
        action = _parse_action(raw)
        assert action.next_prompt == "Remember this for later"


class TestNextActionForShot:
    def test_returns_nav_action(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        action = next_action_for_shot(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            goal_description="Capture dashboard",
            preview_png_bytes=sample_png_bytes,
            step_index=1,
            history=[],
        )
        assert isinstance(action, NavAction)
        assert action.type == "done"

    def test_rejects_cross_origin_goto(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        # Configure mock to return cross-origin URL
        mock_openai_client.responses.create.return_value.output_text = (
            '{"type": "goto", "url": "https://malicious.com/page"}'
        )
        action = next_action_for_shot(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            goal_description="Capture dashboard",
            preview_png_bytes=sample_png_bytes,
            step_index=1,
            history=[],
        )
        # Should be converted to wait action
        assert action.type == "wait"

    def test_allows_same_origin_goto(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        mock_openai_client.responses.create.return_value.output_text = (
            '{"type": "goto", "url": "https://example.com/other"}'
        )
        action = next_action_for_shot(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            goal_description="Capture dashboard",
            preview_png_bytes=sample_png_bytes,
            step_index=1,
            history=[],
        )
        assert action.type == "goto"
        assert action.url == "https://example.com/other"

    def test_clamps_repeat_max_10(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        mock_openai_client.responses.create.return_value.output_text = (
            '{"type": "scroll", "scroll_y": 500, "repeat": 100}'
        )
        action = next_action_for_shot(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            goal_description="Capture dashboard",
            preview_png_bytes=sample_png_bytes,
            step_index=1,
            history=[],
        )
        assert action.repeat == 10

    def test_clamps_repeat_min_1(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        mock_openai_client.responses.create.return_value.output_text = (
            '{"type": "scroll", "scroll_y": 500, "repeat": -5}'
        )
        action = next_action_for_shot(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            goal_description="Capture dashboard",
            preview_png_bytes=sample_png_bytes,
            step_index=1,
            history=[],
        )
        assert action.repeat == 1

    def test_passes_history_to_client(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        history = [{"action": {"type": "click"}, "result": "ok"}]
        next_action_for_shot(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            goal_description="Capture dashboard",
            preview_png_bytes=sample_png_bytes,
            step_index=1,
            history=history,
        )
        # Verify the client was called
        mock_openai_client.responses.create.assert_called_once()


class TestPickCrop:
    def test_returns_crop_on_valid_response(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        mock_openai_client.responses.create.return_value.output_text = (
            '{"x": 10, "y": 20, "w": 100, "h": 80, "rationale": "Focus on main content"}'
        )
        crop = pick_crop(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            preview_png_bytes=sample_png_bytes,
            preview_w=100,
            preview_h=100,
        )
        assert isinstance(crop, Crop)
        assert crop.x == 10
        assert crop.y == 20
        assert crop.w == 100
        assert crop.h == 80
        assert crop.rationale == "Focus on main content"

    def test_returns_none_on_zero_crop(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        mock_openai_client.responses.create.return_value.output_text = (
            '{"x": 0, "y": 0, "w": 0, "h": 0, "rationale": "Not presentable"}'
        )
        crop = pick_crop(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            preview_png_bytes=sample_png_bytes,
            preview_w=100,
            preview_h=100,
        )
        assert crop is None

    def test_returns_none_on_invalid_json(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        mock_openai_client.responses.create.return_value.output_text = "not valid json"
        crop = pick_crop(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            preview_png_bytes=sample_png_bytes,
            preview_w=100,
            preview_h=100,
        )
        assert crop is None

    def test_truncates_rationale(self, mock_openai_client: MagicMock, sample_png_bytes: bytes):
        long_rationale = "x" * 500
        mock_openai_client.responses.create.return_value.output_text = json.dumps(
            {"x": 10, "y": 10, "w": 50, "h": 50, "rationale": long_rationale}
        )
        crop = pick_crop(
            client=mock_openai_client,
            model="gpt-4.1",
            base_url="https://example.com",
            current_url="https://example.com/app",
            preview_png_bytes=sample_png_bytes,
            preview_w=100,
            preview_h=100,
        )
        assert crop is not None
        assert len(crop.rationale) == 400


class TestNavAction:
    def test_nav_action_defaults(self):
        action = NavAction(type="done")
        assert action.type == "done"
        assert action.reason == ""
        assert action.url is None
        assert action.repeat == 1

    def test_nav_action_with_all_fields(self):
        action = NavAction(
            type="click_role",
            reason="Click the button",
            role="button",
            name="Submit",
            nth=0,
            repeat=2,
        )
        assert action.type == "click_role"
        assert action.role == "button"
        assert action.name == "Submit"
        assert action.nth == 0
        assert action.repeat == 2
