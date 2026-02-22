from __future__ import annotations

import argparse
import pathlib
import sys

from .config import load_config
from .runner import login_manual, run_config
from .viewport import VIEWPORT_PRESETS, viewport_from_values


def _add_common_run_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out-dir", default=None, help="Output directory (overrides config out_dir, default: shots_out).")
    p.add_argument("--headed", action="store_true", help="Show the browser (debug).")
    p.add_argument("--timeout-ms", type=int, default=10_000, help="Page-load/navigation timeout.")
    p.add_argument("--action-timeout-ms", type=int, default=5_000, help="Timeout for clicks/typing (fail fast).")

    p.add_argument("--use-llm", action="store_true", help="Enable LLM multi-step navigation to acquire each shot.")
    p.add_argument("--model", default="gpt-5.2")
    p.add_argument("--use-llm-crop", action="store_true", help="Use LLM to choose a crop box.")
    p.add_argument("--max-crop-retries", type=int, default=2, help="Max crop validation retries (default: 2).")
    p.add_argument("--save-source", action="store_true", help="Save uncropped source images too.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shots", description="LLM-assisted marketing screenshots (generic login).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # login
    p_login = sub.add_parser("login", help="Open browser for manual login; saves storage_state.json")
    p_login.add_argument("--base-url", required=True)
    p_login.add_argument("--out-dir", default="shots_out")

    p_login.add_argument("--viewport", choices=VIEWPORT_PRESETS.keys(), default="laptop")
    p_login.add_argument("--viewport-w", type=int)
    p_login.add_argument("--viewport-h", type=int)
    p_login.add_argument("--scale", type=int)
    p_login.add_argument("--full-page", action="store_true", help="(Ignored for login; kept for consistency)")
    p_login.set_defaults(func=cmd_login)

    # run-config
    p_cfg = sub.add_parser("run-config", help="Run required screenshots from a config file (YAML/JSON).")
    p_cfg.add_argument("--config", required=True)
    _add_common_run_flags(p_cfg)

    p_cfg.add_argument(
        "--viewport", choices=VIEWPORT_PRESETS.keys(), default="desktop", help="Fallback viewport if not set in config."
    )
    p_cfg.add_argument("--viewport-w", type=int)
    p_cfg.add_argument("--viewport-h", type=int)
    p_cfg.add_argument("--scale", type=int)
    p_cfg.add_argument("--full-page", action="store_true", help="Fallback full-page if not set in config.")
    p_cfg.set_defaults(func=cmd_run_config)

    return parser


def _resolve_cli_viewport(args) -> tuple[int, int, int, bool]:
    # If explicit width/height/scale provided, prefer that; else preset.
    if args.viewport_w and args.viewport_h:
        scale = args.scale if args.scale else VIEWPORT_PRESETS.get(args.viewport, {}).get("scale", 2)
        full_page = bool(args.full_page) if hasattr(args, "full_page") else True
        return int(args.viewport_w), int(args.viewport_h), int(scale), full_page

    vp = VIEWPORT_PRESETS.get(args.viewport, VIEWPORT_PRESETS["desktop"])
    full_page = bool(args.full_page) if hasattr(args, "full_page") else bool(vp["full_page"])
    return int(vp["width"]), int(vp["height"]), int(vp["scale"]), full_page


def cmd_login(args) -> None:
    out_dir = pathlib.Path(args.out_dir).resolve()
    base_url = args.base_url.rstrip("/")

    w, h, scale, _full_page = _resolve_cli_viewport(args)
    vp = viewport_from_values(w, h, scale, full_page=True)

    login_manual(base_url=base_url, out_dir=out_dir, viewport=vp)


def cmd_run_config(args) -> None:
    cfg = load_config(args.config)
    # CLI --out-dir overrides config out_dir
    out_dir_str = args.out_dir if args.out_dir is not None else cfg.out_dir
    out_dir = pathlib.Path(out_dir_str).resolve()

    w, h, scale, full_page = _resolve_cli_viewport(args)
    fallback = viewport_from_values(w, h, scale, full_page=full_page)

    report_path = run_config(
        cfg=cfg,
        out_dir=out_dir,
        timeout_ms=args.timeout_ms,
        action_timeout_ms=args.action_timeout_ms,
        headed=args.headed,
        use_llm=args.use_llm,
        model=args.model,
        use_llm_crop=args.use_llm_crop,
        max_crop_retries=args.max_crop_retries,
        save_source=args.save_source,
        cli_fallback_viewport=fallback,
    )
    print(f"Report: {report_path}")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
