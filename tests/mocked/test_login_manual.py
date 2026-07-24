"""Tests for shots.runner.login_manual with a mocked Playwright stack."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

from shots.runner import login_manual
from shots.viewport import Viewport


def _patch_sync_playwright(mocker, mock_browser: MagicMock, mock_context: MagicMock, mock_page: MagicMock):
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    mock_p = MagicMock()
    mock_p.chromium.launch.return_value = mock_browser

    mock_sync_playwright = mocker.patch("shots.runner.sync_playwright")
    mock_sync_playwright.return_value.__enter__.return_value = mock_p
    mock_sync_playwright.return_value.__exit__.return_value = False
    return mock_sync_playwright, mock_p


class TestLoginManualTty:
    def test_saves_storage_state_when_tty(
        self,
        mocker,
        tmp_out_dir: pathlib.Path,
        mock_browser: MagicMock,
        mock_browser_context: MagicMock,
        mock_page: MagicMock,
    ):
        _patch_sync_playwright(mocker, mock_browser, mock_browser_context, mock_page)
        mocker.patch("sys.stdin.isatty", return_value=True)
        mocker.patch("builtins.input", return_value="")

        viewport = Viewport(width=1280, height=800, scale=1, full_page=True)
        result = login_manual(base_url="https://example.com", out_dir=tmp_out_dir, viewport=viewport)

        assert result == tmp_out_dir / "storage_state.json"
        mock_page.goto.assert_called_once_with("https://example.com", wait_until="domcontentloaded")
        mock_browser_context.storage_state.assert_called_once_with(path=str(result))
        mock_browser_context.close.assert_called_once()
        mock_browser.close.assert_called_once()
        mock_browser.new_context.assert_called_once_with(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=1,
        )

    def test_creates_out_dir(
        self,
        mocker,
        tmp_path: pathlib.Path,
        mock_browser: MagicMock,
        mock_browser_context: MagicMock,
        mock_page: MagicMock,
    ):
        out_dir = tmp_path / "does_not_exist_yet"
        _patch_sync_playwright(mocker, mock_browser, mock_browser_context, mock_page)
        mocker.patch("sys.stdin.isatty", return_value=True)
        mocker.patch("builtins.input", return_value="")

        viewport = Viewport(width=800, height=600, scale=1, full_page=True)
        login_manual(base_url="https://example.com", out_dir=out_dir, viewport=viewport)

        assert out_dir.exists()


class TestLoginManualNonTty:
    def test_pauses_page_when_not_tty(
        self,
        mocker,
        tmp_out_dir: pathlib.Path,
        mock_browser: MagicMock,
        mock_browser_context: MagicMock,
        mock_page: MagicMock,
    ):
        _patch_sync_playwright(mocker, mock_browser, mock_browser_context, mock_page)
        mocker.patch("sys.stdin.isatty", return_value=False)

        viewport = Viewport(width=1024, height=768, scale=2, full_page=True)
        login_manual(base_url="https://example.com", out_dir=tmp_out_dir, viewport=viewport)

        mock_page.pause.assert_called_once()
