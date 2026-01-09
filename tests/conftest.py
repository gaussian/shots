"""Shared fixtures for all tests."""

from __future__ import annotations

import json
import pathlib
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock

import pytest
from PIL import Image

# ============================================================================
# Path Fixtures
# ============================================================================


@pytest.fixture
def fixtures_dir() -> pathlib.Path:
    """Return the path to the fixtures directory."""
    return pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_out_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create and return a temporary output directory."""
    out = tmp_path / "shots_out"
    out.mkdir(parents=True)
    return out


# ============================================================================
# Image Fixtures
# ============================================================================


@pytest.fixture
def sample_png_bytes() -> bytes:
    """Create a simple test PNG image (100x100 red square)."""
    img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def large_png_bytes() -> bytes:
    """Create a larger test PNG image (2000x1500) for downscale tests."""
    img = Image.new("RGBA", (2000, 1500), color=(0, 128, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ============================================================================
# Config Fixtures
# ============================================================================


@pytest.fixture
def valid_config_dict() -> dict[str, Any]:
    """Return a valid configuration dictionary."""
    return {
        "base_url": "https://example.com",
        "start": "/app",
        "defaults": {
            "viewport_preset": "desktop",
            "full_page": True,
            "max_nav_steps": 12,
        },
        "shots": [
            {
                "id": "dashboard",
                "description": "Capture the main dashboard",
                "url": "/app/dashboard",
            },
            {
                "id": "settings",
                "description": "Capture settings page",
                "viewport_preset": "laptop",
            },
        ],
    }


@pytest.fixture
def valid_config_json(tmp_path: pathlib.Path, valid_config_dict: dict[str, Any]) -> pathlib.Path:
    """Create a temporary valid JSON config file."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(valid_config_dict), encoding="utf-8")
    return config_path


@pytest.fixture
def valid_config_yaml(tmp_path: pathlib.Path, valid_config_dict: dict[str, Any]) -> pathlib.Path:
    """Create a temporary valid YAML config file."""
    try:
        import yaml

        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump(valid_config_dict), encoding="utf-8")
        return config_path
    except ImportError:
        pytest.skip("PyYAML not installed")


# ============================================================================
# Mock Fixtures for Playwright
# ============================================================================


@pytest.fixture
def mock_page() -> MagicMock:
    """Create a mock Playwright Page object."""
    page = MagicMock()
    page.url = "https://example.com/app"
    page.goto.return_value = None
    page.screenshot.return_value = b"\x89PNG\r\n\x1a\n"
    page.wait_for_timeout.return_value = None
    page.wait_for_load_state.return_value = None
    page.evaluate.return_value = None
    page.get_by_role.return_value = MagicMock()
    page.get_by_text.return_value = MagicMock()
    page.locator.return_value = MagicMock()
    page.keyboard = MagicMock()
    page.mouse = MagicMock()
    return page


@pytest.fixture
def mock_browser_context(mock_page: MagicMock) -> MagicMock:
    """Create a mock Playwright BrowserContext."""
    context = MagicMock()
    context.new_page.return_value = mock_page
    context.storage_state.return_value = None
    context.close.return_value = None
    return context


@pytest.fixture
def mock_browser(mock_browser_context: MagicMock) -> MagicMock:
    """Create a mock Playwright Browser."""
    browser = MagicMock()
    browser.new_context.return_value = mock_browser_context
    browser.close.return_value = None
    return browser


# ============================================================================
# Mock Fixtures for OpenAI
# ============================================================================


@pytest.fixture
def mock_openai_response() -> MagicMock:
    """Create a mock OpenAI response object."""
    response = MagicMock()
    response.output_text = '{"type": "done", "reason": "Screenshot acquired"}'
    return response


@pytest.fixture
def mock_openai_client(mock_openai_response: MagicMock) -> MagicMock:
    """Create a mock OpenAI client."""
    client = MagicMock()
    client.responses.create.return_value = mock_openai_response
    return client


# ============================================================================
# Storage State Fixture
# ============================================================================


@pytest.fixture
def storage_state_file(tmp_out_dir: pathlib.Path) -> pathlib.Path:
    """Create a mock storage_state.json file."""
    state_path = tmp_out_dir / "storage_state.json"
    state_path.write_text(json.dumps({"cookies": [], "origins": []}), encoding="utf-8")
    return state_path
