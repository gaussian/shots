from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any

try:
    import yaml  # type: ignore
except Exception:
    yaml = None


@dataclass
class ShotSpec:
    id: str
    description: str
    url: str | None = None  # absolute or relative
    viewport_preset: str | None = None
    viewport: dict[str, int] | None = None  # width/height/scale
    full_page: bool | None = None


@dataclass
class RunConfig:
    base_url: str
    start: str
    defaults: dict[str, Any]
    shots: list[ShotSpec]


def _require_str(obj: dict[str, Any], key: str) -> str:
    if key not in obj or not isinstance(obj[key], str) or not obj[key].strip():
        raise ValueError(f"Missing/invalid required string: {key}")
    return obj[key].strip()


def load_config(path: str) -> RunConfig:
    p = pathlib.Path(path).resolve()
    raw_text = p.read_text(encoding="utf-8")

    if p.suffix.lower() in (".yaml", ".yml"):
        if yaml is None:
            raise RuntimeError("YAML config requires: pip install '.[yaml]' (pyyaml)")
        data = yaml.safe_load(raw_text)
    else:
        data = json.loads(raw_text)

    if not isinstance(data, dict):
        raise ValueError("Config must be an object at the top level.")

    base_url = _require_str(data, "base_url").rstrip("/")
    start = str(data.get("start", "/")).strip() or "/"
    defaults = data.get("defaults", {}) or {}
    if not isinstance(defaults, dict):
        raise ValueError("defaults must be an object.")

    shots_raw = data.get("shots", [])
    if not isinstance(shots_raw, list) or not shots_raw:
        raise ValueError("shots must be a non-empty list.")

    shots: list[ShotSpec] = []
    for idx, s in enumerate(shots_raw):
        if not isinstance(s, dict):
            raise ValueError(f"shots[{idx}] must be an object.")
        sid = _require_str(s, "id")
        desc = _require_str(s, "description")

        viewport = s.get("viewport")
        if viewport is not None and not isinstance(viewport, dict):
            raise ValueError(f"shots[{idx}].viewport must be an object if provided.")

        shots.append(
            ShotSpec(
                id=sid,
                description=desc,
                url=str(s["url"]).strip() if s.get("url") else None,
                viewport_preset=str(s["viewport_preset"]).strip() if s.get("viewport_preset") else None,
                viewport={k: int(v) for k, v in viewport.items()} if viewport else None,
                full_page=bool(s["full_page"]) if "full_page" in s else None,
            )
        )

    return RunConfig(base_url=base_url, start=start, defaults=defaults, shots=shots)
