"""Tests for shots.runner.run_config with a fully mocked Playwright + OpenAI stack.

These exercise the end-to-end orchestration logic (skip/overwrite handling,
chains, labels, source saving, crop validation loop, pdf/png assembly, error
handling) without ever touching a real browser or network.
"""

from __future__ import annotations

import json
import logging
import pathlib
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from PIL import Image

from shots.config import RunConfig, ShotGroup, ShotSpec
from shots.image_ops import Crop
from shots.llm import CropValidation, NavAction
from shots.runner import run_config
from shots.viewport import Viewport

BASE_URL = "https://example.com"


@pytest.fixture(autouse=True)
def _reset_shots_logger():
    """Prevent FileHandlers opened against tmp dirs from leaking across tests."""
    logger = logging.getLogger("shots")
    original_handlers = list(logger.handlers)
    yield
    for h in logger.handlers:
        if h not in original_handlers:
            h.close()
    logger.handlers = original_handlers


def _make_context_and_page(url: str, screenshot_bytes: bytes) -> tuple[MagicMock, MagicMock]:
    page = MagicMock()
    page.url = url
    page.goto.return_value = None
    page.screenshot.return_value = screenshot_bytes
    page.wait_for_timeout.return_value = None
    page.wait_for_load_state.return_value = None
    page.evaluate.return_value = None
    page.accessibility.snapshot.return_value = None
    page.get_by_role.return_value = MagicMock()
    page.get_by_text.return_value = MagicMock()
    page.locator.return_value = MagicMock()
    page.keyboard = MagicMock()
    page.mouse = MagicMock()

    context = MagicMock()
    context.new_page.return_value = page
    context.storage_state.return_value = None
    context.close.return_value = None
    return context, page


def _patch_playwright(mocker, contexts: list[MagicMock]):
    """Patch shots.runner.sync_playwright so p.chromium.launch(...).new_context(...)
    yields each of `contexts` in order (one per expected chain)."""
    browser = MagicMock()
    browser.new_context.side_effect = contexts
    browser.close.return_value = None

    p = MagicMock()
    p.chromium.launch.return_value = browser

    mock_sync_playwright = mocker.patch("shots.runner.sync_playwright")
    mock_sync_playwright.return_value.__enter__.return_value = p
    mock_sync_playwright.return_value.__exit__.return_value = False
    return browser


def _fallback_viewport() -> Viewport:
    return Viewport(width=1280, height=800, scale=1, full_page=True)


def _run_kwargs(**overrides):
    kwargs = {
        "timeout_ms": 1000,
        "action_timeout_ms": 500,
        "headed": False,
        "use_llm": False,
        "model": "gpt-test",
        "use_llm_crop": False,
        "max_crop_retries": 2,
        "save_source": False,
        "overwrite_all": False,
        "cli_fallback_viewport": _fallback_viewport(),
    }
    kwargs.update(overrides)
    return kwargs


class TestRunConfigMissingStorageState:
    def test_raises_when_storage_state_missing(self, tmp_out_dir: pathlib.Path):
        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="hero", url="/dashboard")])],
        )
        with pytest.raises(RuntimeError, match="Missing"):
            run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs())


class TestRunConfigBasicSuccess:
    def test_single_shot_png_group(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="hero", url="/dashboard")])],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs())

        assert report_path == tmp_out_dir / "report.json"
        report = json.loads(report_path.read_text())
        assert report["groups"][0]["shots"][0]["status"] == "ok"
        output_path = tmp_out_dir / "hero" / "output.png"
        assert output_path.exists()
        page.goto.assert_called_once()


class TestRunConfigSkipLogic:
    def test_skips_when_output_already_exists(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        group_dir = tmp_out_dir / "hero"
        group_dir.mkdir(parents=True)
        (group_dir / "hero.png").write_bytes(sample_png_bytes)

        _patch_playwright(mocker, [])  # no context should be needed

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="hero", url="/dashboard")])],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs())
        report = json.loads(report_path.read_text())
        assert report["groups"][0]["shots"][0]["status"] == "skipped"
        assert (group_dir / "output.png").exists()

    def test_overwrite_all_forces_recapture(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        group_dir = tmp_out_dir / "hero"
        group_dir.mkdir(parents=True)
        (group_dir / "hero.png").write_bytes(sample_png_bytes)

        context, page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="hero", url="/dashboard")])],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(overwrite_all=True))
        report = json.loads(report_path.read_text())
        assert report["groups"][0]["shots"][0]["status"] == "ok"
        page.goto.assert_called_once()

    def test_shot_level_overwrite_true_forces_recapture(
        self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes
    ):
        group_dir = tmp_out_dir / "hero"
        group_dir.mkdir(parents=True)
        (group_dir / "hero.png").write_bytes(sample_png_bytes)

        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(
                    id="hero",
                    shots=[ShotSpec(id="hero", description="hero", url="/dashboard", overwrite=True)],
                )
            ],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs())
        report = json.loads(report_path.read_text())
        assert report["groups"][0]["shots"][0]["status"] == "ok"


class TestRunConfigErrorHandling:
    def test_continue_shot_without_llm_errors(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/a", sample_png_bytes)
        _patch_playwright(mocker, [context])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(
                    id="chain",
                    output="pdf",
                    shots=[
                        ShotSpec(id="a", description="first", url="/a"),
                        ShotSpec(id="b", description="second", continue_from_prev=True),
                    ],
                )
            ],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs())
        report = json.loads(report_path.read_text())
        shots_report = report["groups"][0]["shots"]
        assert shots_report[0]["status"] == "ok"
        assert shots_report[1]["status"] == "error"
        assert "output_file" not in report["groups"][0]

    def test_missing_url_without_llm_errors(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/x", sample_png_bytes)
        _patch_playwright(mocker, [context])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[ShotGroup(id="noturl", shots=[ShotSpec(id="noturl", description="no url set")])],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs())
        report = json.loads(report_path.read_text())
        assert report["groups"][0]["shots"][0]["status"] == "error"
        assert "cannot acquire" in report["groups"][0]["shots"][0]["error"]
        assert "output_file" not in report["groups"][0]


class TestRunConfigPdfGroup:
    def test_multi_shot_pdf_group_assembled(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context1, _page1 = _make_context_and_page(f"{BASE_URL}/a", sample_png_bytes)
        context2, _page2 = _make_context_and_page(f"{BASE_URL}/b", sample_png_bytes)
        _patch_playwright(mocker, [context1, context2])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(
                    id="report",
                    output="pdf",
                    shots=[
                        ShotSpec(id="a", description="first page", url="/a"),
                        ShotSpec(id="b", description="second page", url="/b"),
                    ],
                )
            ],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs())
        report = json.loads(report_path.read_text())
        pdf_path = tmp_out_dir / "report" / "output.pdf"
        assert pdf_path.exists()
        assert pdf_path.read_bytes()[:5] == b"%PDF-"
        assert report["groups"][0]["output_file"] == str(pdf_path)


class TestRunConfigLabelsAndSourceSaving:
    def test_label_adds_banner_to_output(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(
                    id="hero",
                    shots=[ShotSpec(id="hero", description="hero", url="/dashboard", label="{title}")],
                )
            ],
        )
        run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs())
        output_path = tmp_out_dir / "hero" / "output.png"
        original = Image.open(BytesIO(sample_png_bytes))
        labeled = Image.open(output_path)
        assert labeled.height > original.height

    def test_group_label_and_label_date_applied(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(
                    id="hero",
                    label="{url}",
                    label_date=True,
                    shots=[ShotSpec(id="hero", description="hero", url="/dashboard")],
                )
            ],
        )
        run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs())
        output_path = tmp_out_dir / "hero" / "output.png"
        original = Image.open(BytesIO(sample_png_bytes))
        labeled = Image.open(output_path)
        assert labeled.height > original.height

    def test_save_source_writes_source_png(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="hero", url="/dashboard")])],
        )
        run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(save_source=True))
        sources_dir = tmp_out_dir / "hero" / "sources"
        assert sources_dir.exists()
        source_files = list(sources_dir.glob("hero-*-source.png"))
        assert len(source_files) == 1


class TestRunConfigOutputRename:
    def test_existing_output_png_moved_to_previous(
        self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes
    ):
        group_dir = tmp_out_dir / "hero"
        group_dir.mkdir(parents=True)
        (group_dir / "output.png").write_bytes(b"old-fake-png-bytes")

        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="hero", url="/dashboard")])],
        )
        run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(overwrite_all=True))

        prev_dir = group_dir / "previous"
        assert prev_dir.exists()
        previous_files = list(prev_dir.glob("hero-*.png"))
        assert len(previous_files) == 1
        assert previous_files[0].read_bytes() == b"old-fake-png-bytes"
        assert (group_dir / "output.png").read_bytes() != b"old-fake-png-bytes"


class TestRunConfigLlmDriven:
    def test_llm_done_action_completes_shot(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])
        mocker.patch("shots.llm.make_openai_client", return_value=MagicMock())
        mocker.patch("shots.llm.next_action_for_shot", return_value=NavAction(type="done", reason="acquired"))

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="Capture the hero", url="/dashboard")])
            ],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(use_llm=True))
        report = json.loads(report_path.read_text())
        assert report["groups"][0]["shots"][0]["status"] == "ok"

    def test_llm_fail_action_errors_shot(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])
        mocker.patch("shots.llm.make_openai_client", return_value=MagicMock())
        mocker.patch(
            "shots.llm.next_action_for_shot", return_value=NavAction(type="fail", reason="cannot find element")
        )

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="Capture the hero", url="/dashboard")])
            ],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(use_llm=True))
        report = json.loads(report_path.read_text())
        assert report["groups"][0]["shots"][0]["status"] == "error"
        assert "cannot find element" in report["groups"][0]["shots"][0]["error"]

    def test_llm_exhausts_max_steps(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])
        mocker.patch("shots.llm.make_openai_client", return_value=MagicMock())
        mocker.patch(
            "shots.llm.next_action_for_shot",
            return_value=NavAction(type="wait", ms=10, reason="still looking"),
        )

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={"max_nav_steps": 2},
            groups=[
                ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="Capture the hero", url="/dashboard")])
            ],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(use_llm=True))
        report = json.loads(report_path.read_text())
        assert report["groups"][0]["shots"][0]["status"] == "error"
        assert "Failed to acquire shot" in report["groups"][0]["shots"][0]["error"]

    def test_llm_repeated_failed_action_requeries(
        self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes
    ):
        context, page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])
        mocker.patch("shots.llm.make_openai_client", return_value=MagicMock())

        # First call: a click that will fail (element not found -> get_by_role raises).
        # Second call (re-query after repeated-failure detection): done.
        page.get_by_role.side_effect = Exception("not found")
        responses = [
            NavAction(type="click_role", role="button", name="Missing"),
            NavAction(type="click_role", role="button", name="Missing"),  # repeated -> triggers re-query
            NavAction(type="done"),
        ]
        mocker.patch("shots.llm.next_action_for_shot", side_effect=responses)

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={"max_nav_steps": 5},
            groups=[
                ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="Capture the hero", url="/dashboard")])
            ],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(use_llm=True))
        report = json.loads(report_path.read_text())
        assert report["groups"][0]["shots"][0]["status"] == "ok"


class TestRunConfigLlmCrop:
    def test_crop_validated_on_first_attempt(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])
        mocker.patch("shots.llm.make_openai_client", return_value=MagicMock())
        mocker.patch("shots.llm.next_action_for_shot", return_value=NavAction(type="done"))
        mocker.patch(
            "shots.llm.pick_crop",
            return_value=Crop(x=10, y=10, w=50, h=50, rationale="focus"),
        )
        mocker.patch("shots.llm.validate_crop", return_value=CropValidation(ok=True, reason=""))

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="Capture the hero", url="/dashboard")])
            ],
        )
        run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(use_llm=True, use_llm_crop=True))
        output_path = tmp_out_dir / "hero" / "output.png"
        img = Image.open(output_path)
        assert img.size == (50, 50)

    def test_crop_retries_then_succeeds(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])
        mocker.patch("shots.llm.make_openai_client", return_value=MagicMock())
        mocker.patch("shots.llm.next_action_for_shot", return_value=NavAction(type="done"))
        mocker.patch(
            "shots.llm.pick_crop",
            return_value=Crop(x=5, y=5, w=40, h=40, rationale="focus"),
        )
        mocker.patch(
            "shots.llm.validate_crop",
            side_effect=[
                CropValidation(ok=False, reason="cuts off a label"),
                CropValidation(ok=True, reason=""),
            ],
        )

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="Capture the hero", url="/dashboard")])
            ],
        )
        run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(use_llm=True, use_llm_crop=True, max_crop_retries=2))
        output_path = tmp_out_dir / "hero" / "output.png"
        img = Image.open(output_path)
        assert img.size == (40, 40)

    def test_crop_exhausts_retries_uses_last_attempt(
        self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes
    ):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])
        mocker.patch("shots.llm.make_openai_client", return_value=MagicMock())
        mocker.patch("shots.llm.next_action_for_shot", return_value=NavAction(type="done"))
        mocker.patch(
            "shots.llm.pick_crop",
            return_value=Crop(x=5, y=5, w=30, h=30, rationale="focus"),
        )
        mocker.patch(
            "shots.llm.validate_crop",
            return_value=CropValidation(ok=False, reason="always cuts something off"),
        )

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="Capture the hero", url="/dashboard")])
            ],
        )
        run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(use_llm=True, use_llm_crop=True, max_crop_retries=2))
        output_path = tmp_out_dir / "hero" / "output.png"
        img = Image.open(output_path)
        assert img.size == (30, 30)

    def test_crop_none_uses_full_image(self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes):
        context, _page = _make_context_and_page(f"{BASE_URL}/dashboard", sample_png_bytes)
        _patch_playwright(mocker, [context])
        mocker.patch("shots.llm.make_openai_client", return_value=MagicMock())
        mocker.patch("shots.llm.next_action_for_shot", return_value=NavAction(type="done"))
        mocker.patch("shots.llm.pick_crop", return_value=None)

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(id="hero", shots=[ShotSpec(id="hero", description="Capture the hero", url="/dashboard")])
            ],
        )
        run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(use_llm=True, use_llm_crop=True))
        output_path = tmp_out_dir / "hero" / "output.png"
        original = Image.open(BytesIO(sample_png_bytes))
        img = Image.open(output_path)
        assert img.size == original.size


class TestRunConfigContinueChain:
    def test_continue_chain_with_llm_reuses_page(
        self, mocker, storage_state_file, tmp_out_dir, sample_png_bytes: bytes
    ):
        context, page = _make_context_and_page(f"{BASE_URL}/a", sample_png_bytes)
        _patch_playwright(mocker, [context])
        mocker.patch("shots.llm.make_openai_client", return_value=MagicMock())
        mocker.patch("shots.llm.next_action_for_shot", return_value=NavAction(type="done"))

        cfg = RunConfig(
            base_url=BASE_URL,
            start="/",
            defaults={},
            groups=[
                ShotGroup(
                    id="chain",
                    output="pdf",
                    shots=[
                        ShotSpec(id="a", description="first step", url="/a"),
                        ShotSpec(id="b", description="second step", continue_from_prev=True),
                    ],
                )
            ],
        )
        report_path = run_config(cfg=cfg, out_dir=tmp_out_dir, **_run_kwargs(use_llm=True))
        report = json.loads(report_path.read_text())
        shots_report = report["groups"][0]["shots"]
        assert shots_report[0]["status"] == "ok"
        assert shots_report[1]["status"] == "ok"
        # Only one context/page is created for the whole chain.
        assert page.goto.call_count == 1
        assert (tmp_out_dir / "chain" / "output.pdf").exists()
