"""Tests for shots.config module."""

from __future__ import annotations

import json
from typing import Any

import pytest

from shots.config import (
    RunConfig,
    ShotSpec,
    _require_str,
    load_config,
)


class TestRequireStr:
    def test_returns_valid_string(self):
        result = _require_str({"key": "value"}, "key")
        assert result == "value"

    def test_strips_whitespace(self):
        result = _require_str({"key": "  value  "}, "key")
        assert result == "value"

    def test_raises_on_missing_key(self):
        with pytest.raises(ValueError, match="Missing/invalid required string"):
            _require_str({}, "key")

    def test_raises_on_non_string(self):
        with pytest.raises(ValueError, match="Missing/invalid required string"):
            _require_str({"key": 123}, "key")

    def test_raises_on_empty_string(self):
        with pytest.raises(ValueError, match="Missing/invalid required string"):
            _require_str({"key": "   "}, "key")

    def test_raises_on_none_value(self):
        with pytest.raises(ValueError, match="Missing/invalid required string"):
            _require_str({"key": None}, "key")


class TestLoadConfigJson:
    def test_loads_valid_json(self, valid_config_json):
        cfg = load_config(str(valid_config_json))
        assert isinstance(cfg, RunConfig)
        assert cfg.base_url == "https://example.com"
        assert cfg.start == "/app"
        assert len(cfg.shots) == 2

    def test_shot_specs_parsed_correctly(self, valid_config_json):
        cfg = load_config(str(valid_config_json))
        shot = cfg.shots[0]
        assert shot.id == "dashboard"
        assert shot.description == "Capture the main dashboard"
        assert shot.url == "/app/dashboard"

    def test_defaults_parsed(self, valid_config_json):
        cfg = load_config(str(valid_config_json))
        assert cfg.defaults["viewport_preset"] == "desktop"
        assert cfg.defaults["full_page"] is True


class TestLoadConfigYaml:
    def test_loads_valid_yaml(self, valid_config_yaml):
        cfg = load_config(str(valid_config_yaml))
        assert cfg.base_url == "https://example.com"
        assert len(cfg.shots) == 2


class TestLoadConfigValidation:
    def test_raises_on_missing_base_url(self, tmp_path):
        config: dict[str, Any] = {"shots": [{"id": "test", "description": "test"}]}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match="base_url"):
            load_config(str(path))

    def test_raises_on_empty_shots(self, tmp_path):
        config: dict[str, Any] = {"base_url": "https://example.com", "shots": []}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match="non-empty list"):
            load_config(str(path))

    def test_raises_on_shot_missing_id(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [{"description": "test"}],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match="id"):
            load_config(str(path))

    def test_raises_on_shot_missing_description(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [{"id": "test"}],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match="description"):
            load_config(str(path))

    def test_raises_on_non_object_config(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps([1, 2, 3]))
        with pytest.raises(ValueError, match="object at the top level"):
            load_config(str(path))

    def test_raises_on_non_object_shot(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": ["invalid"],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match="must be an object"):
            load_config(str(path))

    def test_raises_on_non_object_defaults(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "defaults": "invalid",
            "shots": [{"id": "test", "description": "test"}],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match="defaults must be an object"):
            load_config(str(path))


class TestShotSpecViewport:
    def test_viewport_dict_converted_to_int(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [
                {
                    "id": "test",
                    "description": "test",
                    "viewport": {"width": 1920, "height": 1080, "scale": 2},
                }
            ],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        cfg = load_config(str(path))
        assert cfg.shots[0].viewport == {"width": 1920, "height": 1080, "scale": 2}

    def test_viewport_preset_parsed(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [
                {
                    "id": "test",
                    "description": "test",
                    "viewport_preset": "mobile",
                }
            ],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        cfg = load_config(str(path))
        assert cfg.shots[0].viewport_preset == "mobile"

    def test_full_page_parsed(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [
                {
                    "id": "test",
                    "description": "test",
                    "full_page": False,
                }
            ],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        cfg = load_config(str(path))
        assert cfg.shots[0].full_page is False


class TestShotSpec:
    def test_shot_spec_defaults(self):
        shot = ShotSpec(id="test", description="Test shot")
        assert shot.url is None
        assert shot.viewport_preset is None
        assert shot.viewport is None
        assert shot.full_page is None
        assert shot.overwrite is None

    def test_shot_spec_with_all_fields(self):
        shot = ShotSpec(
            id="test",
            description="Test shot",
            url="/page",
            viewport_preset="desktop",
            viewport={"width": 1920, "height": 1080, "scale": 2},
            full_page=True,
        )
        assert shot.id == "test"
        assert shot.url == "/page"
        assert shot.viewport_preset == "desktop"


class TestRunConfig:
    def test_run_config_creation(self):
        shots = [ShotSpec(id="test", description="Test")]
        config = RunConfig(
            base_url="https://example.com",
            start="/app",
            defaults={"viewport_preset": "desktop"},
            shots=shots,
        )
        assert config.base_url == "https://example.com"
        assert config.start == "/app"
        assert len(config.shots) == 1


class TestLoadConfigDefaults:
    def test_default_start_is_root(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [{"id": "test", "description": "test"}],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        cfg = load_config(str(path))
        assert cfg.start == "/"

    def test_default_defaults_is_empty_dict(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [{"id": "test", "description": "test"}],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        cfg = load_config(str(path))
        assert cfg.defaults == {}

    def test_base_url_trailing_slash_stripped(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com/",
            "shots": [{"id": "test", "description": "test"}],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        cfg = load_config(str(path))
        assert cfg.base_url == "https://example.com"


class TestShotSpecOverwrite:
    def test_overwrite_true_parsed(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [{"id": "test", "description": "test", "overwrite": True}],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        cfg = load_config(str(path))
        assert cfg.groups[0].shots[0].overwrite is True

    def test_overwrite_false_parsed(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [{"id": "test", "description": "test", "overwrite": False}],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        cfg = load_config(str(path))
        assert cfg.groups[0].shots[0].overwrite is False

    def test_overwrite_absent_defaults_to_none(self, tmp_path):
        config: dict[str, Any] = {
            "base_url": "https://example.com",
            "shots": [{"id": "test", "description": "test"}],
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))
        cfg = load_config(str(path))
        assert cfg.groups[0].shots[0].overwrite is None
