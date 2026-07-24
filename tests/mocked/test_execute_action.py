"""Tests for shots.runner._execute_action and _get_page_context, using a mocked Page."""

from __future__ import annotations

from unittest.mock import MagicMock

from shots.llm import NavAction
from shots.runner import _execute_action, _get_page_context


class TestExecuteActionInvalidType:
    def test_non_navaction_returns_error(self, mock_page: MagicMock):
        outcome = _execute_action(mock_page, {"type": "goto"}, timeout_ms=1000)
        assert outcome.ok is False
        assert "Invalid action type" in outcome.error


class TestExecuteActionGoto:
    def test_goto_calls_page_goto(self, mock_page: MagicMock):
        action = NavAction(type="goto", url="https://example.com/page")
        outcome = _execute_action(mock_page, action, timeout_ms=1000, nav_timeout_ms=5000)
        assert outcome.ok is True
        mock_page.goto.assert_called_once_with("https://example.com/page", wait_until="domcontentloaded", timeout=5000)

    def test_goto_falls_back_to_timeout_ms_when_no_nav_timeout(self, mock_page: MagicMock):
        action = NavAction(type="goto", url="https://example.com/page")
        _execute_action(mock_page, action, timeout_ms=1000)
        mock_page.goto.assert_called_once_with("https://example.com/page", wait_until="domcontentloaded", timeout=1000)

    def test_goto_without_url_does_nothing_but_ok(self, mock_page: MagicMock):
        action = NavAction(type="goto", url=None)
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is True
        mock_page.goto.assert_not_called()


class TestExecuteActionClickRole:
    def test_click_role_clicks_locator(self, mock_page: MagicMock):
        locator = MagicMock()
        mock_page.get_by_role.return_value = locator
        action = NavAction(type="click_role", role="button", name="Submit")
        outcome = _execute_action(mock_page, action, timeout_ms=2000)
        assert outcome.ok is True
        mock_page.get_by_role.assert_called_once_with("button", name="Submit")
        locator.first.click.assert_called_once_with(timeout=2000)

    def test_click_role_with_nth(self, mock_page: MagicMock):
        locator = MagicMock()
        nth_locator = MagicMock()
        locator.nth.return_value = nth_locator
        mock_page.get_by_role.return_value = locator
        action = NavAction(type="click_role", role="link", name="Home", nth=2)
        _execute_action(mock_page, action, timeout_ms=2000)
        locator.nth.assert_called_once_with(2)
        nth_locator.first.click.assert_called_once_with(timeout=2000)


class TestExecuteActionClickText:
    def test_click_text_clicks_locator(self, mock_page: MagicMock):
        locator = MagicMock()
        mock_page.get_by_text.return_value = locator
        action = NavAction(type="click_text", text="Sign in")
        outcome = _execute_action(mock_page, action, timeout_ms=1500)
        assert outcome.ok is True
        mock_page.get_by_text.assert_called_once_with("Sign in", exact=False)
        locator.first.click.assert_called_once_with(timeout=1500)


class TestExecuteActionTypeText:
    def test_type_text_with_selector(self, mock_page: MagicMock):
        locator = MagicMock()
        mock_page.locator.return_value = locator
        action = NavAction(type="type_text", selector="#email", input_text="me@example.com")
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is True
        locator.click.assert_called_once_with(timeout=1000)
        locator.fill.assert_called_once_with("me@example.com", timeout=1000)

    def test_type_text_without_selector_uses_keyboard(self, mock_page: MagicMock):
        action = NavAction(type="type_text", input_text="hello")
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is True
        mock_page.keyboard.type.assert_called_once_with("hello")

    def test_type_text_none_input_defaults_to_empty_string(self, mock_page: MagicMock):
        action = NavAction(type="type_text", input_text=None)
        _execute_action(mock_page, action, timeout_ms=1000)
        mock_page.keyboard.type.assert_called_once_with("")


class TestExecuteActionPressKey:
    def test_press_key(self, mock_page: MagicMock):
        action = NavAction(type="press_key", key="Enter")
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is True
        mock_page.keyboard.press.assert_called_once_with("Enter")


class TestExecuteActionScroll:
    def test_scroll_uses_scroll_y(self, mock_page: MagicMock):
        action = NavAction(type="scroll", scroll_y=400)
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is True
        mock_page.mouse.wheel.assert_called_once_with(0, 400)

    def test_scroll_defaults_to_800(self, mock_page: MagicMock):
        action = NavAction(type="scroll", scroll_y=None)
        _execute_action(mock_page, action, timeout_ms=1000)
        mock_page.mouse.wheel.assert_called_once_with(0, 800)


class TestExecuteActionWait:
    def test_wait_uses_ms(self, mock_page: MagicMock):
        action = NavAction(type="wait", ms=1500)
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is True
        mock_page.wait_for_timeout.assert_any_call(1500)

    def test_wait_defaults_to_800(self, mock_page: MagicMock):
        action = NavAction(type="wait", ms=None)
        _execute_action(mock_page, action, timeout_ms=1000)
        mock_page.wait_for_timeout.assert_any_call(800)


class TestExecuteActionTerminal:
    def test_done_returns_ok_with_terminal_extra(self, mock_page: MagicMock):
        action = NavAction(type="done")
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is True
        assert outcome.extra == {"terminal": "done"}
        mock_page.wait_for_timeout.assert_not_called()

    def test_fail_returns_ok_with_terminal_extra(self, mock_page: MagicMock):
        action = NavAction(type="fail", reason="cannot proceed")
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is True
        assert outcome.extra == {"terminal": "fail"}


class TestExecuteActionRepeat:
    def test_repeats_action_n_times(self, mock_page: MagicMock):
        action = NavAction(type="press_key", key="Tab", repeat=3)
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is True
        assert mock_page.keyboard.press.call_count == 3

    def test_repeat_zero_still_runs_once(self, mock_page: MagicMock):
        action = NavAction(type="press_key", key="Tab", repeat=0)
        _execute_action(mock_page, action, timeout_ms=1000)
        assert mock_page.keyboard.press.call_count == 1


class TestExecuteActionErrorHandling:
    def test_exception_returns_error_outcome(self, mock_page: MagicMock):
        mock_page.get_by_role.side_effect = Exception("Timeout 1000ms exceeded")
        action = NavAction(type="click_role", role="button", name="Missing")
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is False
        assert "Timeout 1000ms exceeded" in outcome.error

    def test_goto_exception_returns_error_outcome(self, mock_page: MagicMock):
        mock_page.goto.side_effect = TimeoutError("nav timed out")
        action = NavAction(type="goto", url="https://example.com/x")
        outcome = _execute_action(mock_page, action, timeout_ms=1000)
        assert outcome.ok is False
        assert "nav timed out" in outcome.error


class TestGetPageContext:
    def test_returns_empty_string_on_snapshot_exception(self, mock_page: MagicMock):
        mock_page.accessibility.snapshot.side_effect = Exception("no a11y")
        result = _get_page_context(mock_page)
        assert result == ""

    def test_returns_empty_string_on_falsy_snapshot(self, mock_page: MagicMock):
        mock_page.accessibility.snapshot.return_value = None
        result = _get_page_context(mock_page)
        assert result == ""

    def test_extracts_interactive_elements(self, mock_page: MagicMock):
        mock_page.accessibility.snapshot.return_value = {
            "role": "WebArea",
            "name": "",
            "children": [
                {"role": "button", "name": "Submit", "children": []},
                {"role": "generic", "name": "ignored", "children": []},
                {"role": "link", "name": "Home", "description": "/home", "children": []},
            ],
        }
        mock_page.evaluate.return_value = []
        result = _get_page_context(mock_page)
        assert 'button "Submit"' in result
        assert 'link "Home" (/home)' in result
        assert "ignored" not in result

    def test_includes_link_hrefs_from_evaluate(self, mock_page: MagicMock):
        mock_page.accessibility.snapshot.return_value = {"role": "WebArea", "children": []}
        mock_page.evaluate.return_value = [
            {"text": "Docs", "href": "/docs"},
            {"text": "", "href": "#"},
        ]
        result = _get_page_context(mock_page)
        assert "LINK HREFS" in result
        assert "href=/docs" in result

    def test_evaluate_exception_is_swallowed(self, mock_page: MagicMock):
        mock_page.accessibility.snapshot.return_value = {
            "role": "WebArea",
            "children": [{"role": "button", "name": "X", "children": []}],
        }
        mock_page.evaluate.side_effect = Exception("boom")
        result = _get_page_context(mock_page)
        assert 'button "X"' in result
        assert "LINK HREFS" not in result

    def test_respects_max_items(self, mock_page: MagicMock):
        children = [{"role": "button", "name": f"btn{i}", "children": []} for i in range(10)]
        mock_page.accessibility.snapshot.return_value = {"role": "WebArea", "children": children}
        mock_page.evaluate.return_value = []
        result = _get_page_context(mock_page, max_items=3)
        lines = [line for line in result.split("\n") if line.strip()]
        assert len(lines) <= 3
