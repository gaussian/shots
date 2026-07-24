"""Tests for shots.cli: argument parsing and command dispatch."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

import pytest

from shots.cli import (
    _resolve_cli_viewport,
    build_parser,
    cmd_login,
    cmd_run_config,
    main,
)
from shots.config import RunConfig


class TestBuildParserLogin:
    def test_login_requires_base_url(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["login"])

    def test_login_parses_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["login", "--base-url", "https://example.com"])
        assert args.cmd == "login"
        assert args.base_url == "https://example.com"
        assert args.out_dir == "shots_out"
        assert args.viewport == "laptop"
        assert args.func is cmd_login

    def test_login_custom_viewport(self):
        parser = build_parser()
        args = parser.parse_args(
            ["login", "--base-url", "https://example.com", "--viewport", "mobile", "--out-dir", "custom"]
        )
        assert args.viewport == "mobile"
        assert args.out_dir == "custom"

    def test_login_rejects_unknown_viewport(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["login", "--base-url", "https://example.com", "--viewport", "bogus"])


class TestBuildParserRunConfig:
    def test_run_config_requires_config(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["run-config"])

    def test_run_config_parses_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["run-config", "--config", "shots.yaml"])
        assert args.cmd == "run-config"
        assert args.config == "shots.yaml"
        assert args.out_dir is None
        assert args.headed is False
        assert args.timeout_ms == 10_000
        assert args.action_timeout_ms == 5_000
        assert args.use_llm is False
        assert args.model == "gpt-5.2"
        assert args.use_llm_crop is False
        assert args.max_crop_retries == 2
        assert args.save_source is False
        assert args.overwrite is False
        assert args.viewport == "desktop"
        assert args.func is cmd_run_config

    def test_run_config_flags_enabled(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "run-config",
                "--config",
                "shots.yaml",
                "--use-llm",
                "--use-llm-crop",
                "--headed",
                "--overwrite",
                "--save-source",
                "--model",
                "gpt-x",
                "--max-crop-retries",
                "5",
            ]
        )
        assert args.use_llm is True
        assert args.use_llm_crop is True
        assert args.headed is True
        assert args.overwrite is True
        assert args.save_source is True
        assert args.model == "gpt-x"
        assert args.max_crop_retries == 5

    def test_no_command_raises(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestResolveCliViewport:
    def test_explicit_width_height_uses_preset_scale(self):
        parser = build_parser()
        args = parser.parse_args(
            ["run-config", "--config", "x.yaml", "--viewport-w", "1000", "--viewport-h", "700", "--viewport", "mobile"]
        )
        w, h, scale, full_page = _resolve_cli_viewport(args)
        assert (w, h) == (1000, 700)
        assert scale == 3  # mobile preset scale
        assert full_page is False  # full_page defaults to False when not passed via --full-page

    def test_explicit_width_height_and_scale(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "run-config",
                "--config",
                "x.yaml",
                "--viewport-w",
                "1000",
                "--viewport-h",
                "700",
                "--scale",
                "1",
                "--full-page",
            ]
        )
        w, h, scale, full_page = _resolve_cli_viewport(args)
        assert (w, h, scale) == (1000, 700, 1)
        assert full_page is True

    def test_preset_used_when_no_explicit_dims(self):
        parser = build_parser()
        args = parser.parse_args(["run-config", "--config", "x.yaml", "--viewport", "tablet"])
        w, h, scale, full_page = _resolve_cli_viewport(args)
        assert (w, h, scale) == (834, 1112, 2)
        # --full-page wasn't passed, so the store_true default (False) wins over
        # the preset's own full_page=True default.
        assert full_page is False

    def test_preset_full_page_overridden_by_flag(self):
        parser = build_parser()
        args = parser.parse_args(["run-config", "--config", "x.yaml", "--viewport", "desktop", "--full-page"])
        _, _, _, full_page = _resolve_cli_viewport(args)
        assert full_page is True

    def test_login_uses_default_desktop_fallback_for_unknown_viewport_arg(self):
        # login's viewport default is "laptop"; verify preset lookup path works too.
        parser = build_parser()
        args = parser.parse_args(["login", "--base-url", "https://example.com", "--viewport", "desktop"])
        w, h, scale, _ = _resolve_cli_viewport(args)
        assert (w, h, scale) == (1920, 1080, 2)


class TestCmdLogin:
    def test_cmd_login_calls_login_manual(self, mocker, tmp_path: pathlib.Path):
        mock_login_manual = mocker.patch("shots.cli.login_manual")
        parser = build_parser()
        args = parser.parse_args(["login", "--base-url", "https://example.com/", "--out-dir", str(tmp_path / "out")])
        cmd_login(args)

        mock_login_manual.assert_called_once()
        _, kwargs = mock_login_manual.call_args
        assert kwargs["base_url"] == "https://example.com"  # trailing slash stripped
        assert kwargs["out_dir"] == (tmp_path / "out").resolve()
        assert kwargs["viewport"].full_page is True


class TestCmdRunConfig:
    def test_cmd_run_config_calls_run_config_and_prints_report(self, mocker, tmp_path: pathlib.Path, capsys):
        cfg = RunConfig(base_url="https://example.com", start="/", defaults={}, groups=[], out_dir="shots_out")
        mocker.patch("shots.cli.load_config", return_value=cfg)
        report_path = tmp_path / "report.json"
        mock_run_config = mocker.patch("shots.cli.run_config", return_value=report_path)

        parser = build_parser()
        args = parser.parse_args(["run-config", "--config", "shots.yaml"])
        cmd_run_config(args)

        mock_run_config.assert_called_once()
        _, kwargs = mock_run_config.call_args
        assert kwargs["cfg"] is cfg
        assert kwargs["use_llm"] is False
        captured = capsys.readouterr()
        assert f"Report: {report_path}" in captured.out

    def test_cli_out_dir_overrides_config_out_dir(self, mocker, tmp_path: pathlib.Path):
        cfg = RunConfig(base_url="https://example.com", start="/", defaults={}, groups=[], out_dir="cfg_out_dir")
        mocker.patch("shots.cli.load_config", return_value=cfg)
        mock_run_config = mocker.patch("shots.cli.run_config", return_value=tmp_path / "report.json")

        parser = build_parser()
        args = parser.parse_args(["run-config", "--config", "shots.yaml", "--out-dir", str(tmp_path / "cli_out")])
        cmd_run_config(args)

        _, kwargs = mock_run_config.call_args
        assert kwargs["out_dir"] == (tmp_path / "cli_out").resolve()

    def test_config_out_dir_used_when_no_cli_override(self, mocker, tmp_path: pathlib.Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = RunConfig(base_url="https://example.com", start="/", defaults={}, groups=[], out_dir="cfg_out_dir")
        mocker.patch("shots.cli.load_config", return_value=cfg)
        mock_run_config = mocker.patch("shots.cli.run_config", return_value=tmp_path / "report.json")

        parser = build_parser()
        args = parser.parse_args(["run-config", "--config", "shots.yaml"])
        cmd_run_config(args)

        _, kwargs = mock_run_config.call_args
        assert kwargs["out_dir"] == (tmp_path / "cfg_out_dir").resolve()


class TestMain:
    def test_main_dispatches_to_func(self, mocker):
        fake_args = MagicMock()
        mocker.patch("shots.cli.build_parser").return_value.parse_args.return_value = fake_args
        main(["login", "--base-url", "https://example.com"])
        fake_args.func.assert_called_once_with(fake_args)

    def test_main_handles_keyboard_interrupt(self, mocker, capsys):
        fake_args = MagicMock()
        fake_args.func.side_effect = KeyboardInterrupt()
        mocker.patch("shots.cli.build_parser").return_value.parse_args.return_value = fake_args

        with pytest.raises(SystemExit) as exc_info:
            main(["login", "--base-url", "https://example.com"])

        assert exc_info.value.code == 130
        captured = capsys.readouterr()
        assert "Interrupted" in captured.out

    def test_main_end_to_end_login(self, mocker, tmp_path: pathlib.Path):
        mock_login_manual = mocker.patch("shots.cli.login_manual")
        main(["login", "--base-url", "https://example.com", "--out-dir", str(tmp_path)])
        mock_login_manual.assert_called_once()
