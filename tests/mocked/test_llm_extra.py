"""Additional tests for shots.llm: client construction, failure bookkeeping, and
crop validation, complementing tests/mocked/test_llm.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from shots.llm import (
    NavAction,
    _action_signature,
    _summarize_failures,
    failed_signatures,
    make_openai_client,
    validate_crop,
)


class TestMakeOpenaiClient:
    def test_constructs_openai_client(self, mocker):
        mock_openai_cls = MagicMock()
        mocker.patch("openai.OpenAI", mock_openai_cls)
        client = make_openai_client()
        mock_openai_cls.assert_called_once_with()
        assert client is mock_openai_cls.return_value


class TestActionSignature:
    def test_signature_contains_key_fields(self):
        action = NavAction(type="click_role", role="button", name="Submit", text=None, selector=None, url=None)
        sig = _action_signature(action)
        assert sig == ("click_role", "button", "Submit", None, None, None)

    def test_different_actions_have_different_signatures(self):
        a = NavAction(type="click_role", role="button", name="Submit")
        b = NavAction(type="click_role", role="button", name="Cancel")
        assert _action_signature(a) != _action_signature(b)

    def test_same_fields_produce_equal_signature(self):
        a = NavAction(type="goto", url="https://example.com/x")
        b = NavAction(type="goto", url="https://example.com/x", reason="different reason text")
        assert _action_signature(a) == _action_signature(b)


class TestFailedSignatures:
    def test_empty_history_returns_empty_set(self):
        assert failed_signatures([]) == set()

    def test_successful_actions_excluded(self):
        history = [{"action": {"type": "click_role", "role": "button", "name": "X"}, "outcome": {"ok": True}}]
        assert failed_signatures(history) == set()

    def test_failed_actions_included(self):
        history = [
            {
                "action": {
                    "type": "click_role",
                    "role": "button",
                    "name": "X",
                    "text": None,
                    "selector": None,
                    "url": None,
                },
                "outcome": {"ok": False, "error": "timeout"},
            }
        ]
        result = failed_signatures(history)
        assert ("click_role", "button", "X", None, None, None) in result

    def test_mixed_history_only_failures_included(self):
        history = [
            {"action": {"type": "goto", "url": "/a"}, "outcome": {"ok": True}},
            {"action": {"type": "click_text", "text": "Sign in"}, "outcome": {"ok": False, "error": "nope"}},
        ]
        result = failed_signatures(history)
        assert len(result) == 1
        assert ("click_text", None, None, "Sign in", None, None) in result


class TestSummarizeFailures:
    def test_no_failures_returns_empty_string(self):
        history = [{"action": {"type": "goto"}, "outcome": {"ok": True}}]
        assert _summarize_failures(history) == ""

    def test_summarizes_click_role_failure(self):
        history = [
            {
                "action": {"type": "click_role", "role": "button", "name": "Submit"},
                "outcome": {"ok": False, "error": "Timeout exceeded"},
            }
        ]
        result = _summarize_failures(history)
        assert "click_role" in result
        assert "role=button" in result
        assert 'name="Submit"' in result
        assert "Timeout exceeded" in result

    def test_summarizes_goto_failure_with_url(self):
        history = [
            {
                "action": {"type": "goto", "url": "https://example.com/missing"},
                "outcome": {"ok": False, "error": "404"},
            }
        ]
        result = _summarize_failures(history)
        assert "url=https://example.com/missing" in result

    def test_summarizes_type_text_failure_with_selector(self):
        history = [
            {
                "action": {"type": "type_text", "selector": "#email"},
                "outcome": {"ok": False, "error": "not visible"},
            }
        ]
        result = _summarize_failures(history)
        assert 'selector="#email"' in result

    def test_truncates_long_error_messages(self):
        history = [
            {
                "action": {"type": "click_text", "text": "x"},
                "outcome": {"ok": False, "error": "e" * 200},
            }
        ]
        result = _summarize_failures(history)
        # error is sliced to 80 chars in the summary line
        assert "e" * 80 in result
        assert "e" * 200 not in result

    def test_multiple_failures_produce_multiple_lines(self):
        history = [
            {"action": {"type": "click_text", "text": "A"}, "outcome": {"ok": False, "error": "e1"}},
            {"action": {"type": "click_text", "text": "B"}, "outcome": {"ok": False, "error": "e2"}},
        ]
        result = _summarize_failures(history)
        assert len(result.split("\n")) == 2


class TestValidateCrop:
    def test_returns_ok_true(self, mock_openai_client, sample_png_bytes: bytes):
        mock_openai_client.responses.create.return_value.output_text = '{"ok": true, "reason": ""}'
        result = validate_crop(
            client=mock_openai_client,
            model="gpt-4.1",
            cropped_png_bytes=sample_png_bytes,
            goal_description="Capture the dashboard",
        )
        assert result.ok is True
        assert result.reason == ""

    def test_returns_ok_false_with_reason(self, mock_openai_client, sample_png_bytes: bytes):
        mock_openai_client.responses.create.return_value.output_text = (
            '{"ok": false, "reason": "Cuts off the sidebar label"}'
        )
        result = validate_crop(
            client=mock_openai_client,
            model="gpt-4.1",
            cropped_png_bytes=sample_png_bytes,
            goal_description="Capture the dashboard",
        )
        assert result.ok is False
        assert result.reason == "Cuts off the sidebar label"

    def test_invalid_json_defaults_to_ok_true(self, mock_openai_client, sample_png_bytes: bytes):
        mock_openai_client.responses.create.return_value.output_text = "not json at all"
        result = validate_crop(
            client=mock_openai_client,
            model="gpt-4.1",
            cropped_png_bytes=sample_png_bytes,
            goal_description="Capture the dashboard",
        )
        # Fails open so a parsing hiccup doesn't discard an otherwise-good crop.
        assert result.ok is True
        assert result.reason == ""

    def test_truncates_reason_to_400_chars(self, mock_openai_client, sample_png_bytes: bytes):
        import json

        long_reason = "x" * 500
        mock_openai_client.responses.create.return_value.output_text = json.dumps({"ok": False, "reason": long_reason})
        result = validate_crop(
            client=mock_openai_client,
            model="gpt-4.1",
            cropped_png_bytes=sample_png_bytes,
            goal_description="Capture the dashboard",
        )
        assert len(result.reason) == 400

    def test_calls_client_with_expected_model(self, mock_openai_client, sample_png_bytes: bytes):
        validate_crop(
            client=mock_openai_client,
            model="gpt-custom",
            cropped_png_bytes=sample_png_bytes,
            goal_description="Capture the dashboard",
        )
        _, kwargs = mock_openai_client.responses.create.call_args
        assert kwargs["model"] == "gpt-custom"
