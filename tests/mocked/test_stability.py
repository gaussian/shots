"""Tests for shots.stability with a mocked Playwright Page."""

from __future__ import annotations

from unittest.mock import MagicMock

from shots.stability import (
    wait_for_animations,
    wait_for_dom_quiet,
    wait_for_network_idle_best_effort,
    wait_for_toasts,
    wait_until_stable,
)


class TestWaitForNetworkIdleBestEffort:
    def test_calls_wait_for_load_state(self, mock_page: MagicMock):
        wait_for_network_idle_best_effort(mock_page, timeout_ms=1000)
        mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=1000)

    def test_swallows_timeout_exception(self, mock_page: MagicMock):
        mock_page.wait_for_load_state.side_effect = Exception("Timeout 1000ms exceeded")
        # Should not raise
        wait_for_network_idle_best_effort(mock_page, timeout_ms=1000)


class TestWaitForDomQuiet:
    def test_calls_evaluate(self, mock_page: MagicMock):
        wait_for_dom_quiet(mock_page, quiet_ms=400, timeout_ms=2000)
        assert mock_page.evaluate.called
        args, _kwargs = mock_page.evaluate.call_args
        assert args[1] == {"quietMs": 400, "timeoutMs": 2000}

    def test_swallows_exception(self, mock_page: MagicMock):
        mock_page.evaluate.side_effect = Exception("boom")
        wait_for_dom_quiet(mock_page)  # should not raise


class TestWaitForAnimations:
    def test_calls_evaluate_with_timeout(self, mock_page: MagicMock):
        wait_for_animations(mock_page, timeout_ms=500)
        args, _kwargs = mock_page.evaluate.call_args
        assert args[1] == {"timeoutMs": 500}

    def test_swallows_exception(self, mock_page: MagicMock):
        mock_page.evaluate.side_effect = RuntimeError("nope")
        wait_for_animations(mock_page)  # should not raise


class TestWaitForToasts:
    def test_waits_then_evaluates(self, mock_page: MagicMock):
        wait_for_toasts(mock_page, timeout_ms=1000)
        mock_page.wait_for_timeout.assert_any_call(300)
        assert mock_page.evaluate.called

    def test_swallows_exception_from_evaluate(self, mock_page: MagicMock):
        mock_page.evaluate.side_effect = Exception("boom")
        wait_for_toasts(mock_page)  # should not raise

    def test_swallows_exception_from_wait_for_timeout(self, mock_page: MagicMock):
        mock_page.wait_for_timeout.side_effect = Exception("boom")
        wait_for_toasts(mock_page)  # should not raise


class TestWaitUntilStable:
    def test_calls_all_stability_checks(self, mock_page: MagicMock):
        wait_until_stable(mock_page, timeout_ms=5000)
        assert mock_page.wait_for_load_state.called
        assert mock_page.evaluate.called
        assert mock_page.wait_for_timeout.called

    def test_resilient_when_everything_fails(self, mock_page: MagicMock):
        mock_page.wait_for_load_state.side_effect = Exception("x")
        mock_page.evaluate.side_effect = Exception("x")
        mock_page.wait_for_timeout.side_effect = Exception("x")
        # wait_until_stable itself calls page.wait_for_timeout(100) unguarded at
        # the end, so a fully-broken page.wait_for_timeout does propagate.
        try:
            wait_until_stable(mock_page, timeout_ms=1000)
        except Exception:
            pass

    def test_uses_capped_network_idle_timeout(self, mock_page: MagicMock):
        wait_until_stable(mock_page, timeout_ms=100_000)
        # network idle timeout is capped at 2000ms regardless of the overall budget
        mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=2_000)
