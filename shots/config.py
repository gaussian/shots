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
    continue_from_prev: bool = False  # reuse browser page from previous shot in group
    viewport_preset: str | None = None
    viewport: dict[str, int] | None = None  # width/height/scale
    full_page: bool | None = None
    label: str | None = None  # per-shot label override
    overwrite: bool | None = None  # skip if output exists (default: False via defaults)


@dataclass
class ShotGroup:
    id: str
    shots: list[ShotSpec]
    output: str = "png"  # "png" or "pdf"
    label: str | None = None  # template string applied to all shots
    label_date: bool = False  # add date/time line below the label
    folder: str | None = None  # override subfolder name (defaults to id)


@dataclass
class RunConfig:
    base_url: str
    start: str
    defaults: dict[str, Any]
    groups: list[ShotGroup]
    out_dir: str = "shots_out"


def _require_str(obj: dict[str, Any], key: str) -> str:
    if key not in obj or not isinstance(obj[key], str) or not obj[key].strip():
        raise ValueError(f"Missing/invalid required string: {key}")
    return obj[key].strip()


def _parse_shot(s: dict[str, Any], ctx: str) -> ShotSpec:
    """Parse a single shot dict into a ShotSpec."""
    if not isinstance(s, dict):
        raise ValueError(f"{ctx} must be an object.")
    sid = _require_str(s, "id")
    desc = _require_str(s, "description")

    viewport = s.get("viewport")
    if viewport is not None and not isinstance(viewport, dict):
        raise ValueError(f"{ctx}.viewport must be an object if provided.")

    return ShotSpec(
        id=sid,
        description=desc,
        url=str(s["url"]).strip() if s.get("url") else None,
        continue_from_prev=bool(s.get("continue", False)),
        viewport_preset=str(s["viewport_preset"]).strip() if s.get("viewport_preset") else None,
        viewport={k: int(v) for k, v in viewport.items()} if viewport else None,
        full_page=bool(s["full_page"]) if "full_page" in s else None,
        label=str(s["label"]).strip().replace("\\n", "\n") if s.get("label") else None,
        overwrite=bool(s["overwrite"]) if "overwrite" in s else None,
    )


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
    out_dir = str(data.get("out_dir", "shots_out")).strip() or "shots_out"
    defaults = data.get("defaults", {}) or {}
    if not isinstance(defaults, dict):
        raise ValueError("defaults must be an object.")

    has_groups = "groups" in data
    has_shots = "shots" in data

    if has_groups and has_shots:
        raise ValueError("Config cannot have both 'groups' and 'shots'. Use one or the other.")
    if not has_groups and not has_shots:
        raise ValueError("Config must have either 'groups' or 'shots'.")

    groups: list[ShotGroup] = []

    if has_groups:
        groups_raw = data["groups"]
        if not isinstance(groups_raw, list) or not groups_raw:
            raise ValueError("groups must be a non-empty list.")

        for gi, g in enumerate(groups_raw):
            if not isinstance(g, dict):
                raise ValueError(f"groups[{gi}] must be an object.")
            gid = _require_str(g, "id")
            output = str(g.get("output", "png")).strip().lower()
            if output not in ("png", "pdf"):
                raise ValueError(f"groups[{gi}].output must be 'png' or 'pdf', got '{output}'.")

            shots_raw = g.get("shots", [])
            if not isinstance(shots_raw, list) or not shots_raw:
                raise ValueError(f"groups[{gi}].shots must be a non-empty list.")

            shots = [_parse_shot(s, f"groups[{gi}].shots[{si}]") for si, s in enumerate(shots_raw)]

            for si, sh in enumerate(shots):
                if sh.continue_from_prev:
                    if si == 0:
                        raise ValueError(
                            f"groups[{gi}].shots[{si}] ('{sh.id}'): continue cannot be the first shot in a group."
                        )
                    if sh.url is not None:
                        raise ValueError(
                            f"groups[{gi}].shots[{si}] ('{sh.id}'): continue and url are mutually exclusive."
                        )
                    if sh.viewport or sh.viewport_preset:
                        raise ValueError(
                            f"groups[{gi}].shots[{si}] ('{sh.id}'): continue shots "
                            f"cannot override viewport (they inherit from the chain's "
                            f"starting shot)."
                        )

            if output == "png" and len(shots) > 1:
                raise ValueError(
                    f"groups[{gi}] ('{gid}'): output='png' requires exactly 1 shot, got {len(shots)}. "
                    "Use output='pdf' for multi-shot groups."
                )

            groups.append(
                ShotGroup(
                    id=gid,
                    shots=shots,
                    output=output,
                    label=str(g["label"]).strip().replace("\\n", "\n") if g.get("label") else None,
                    label_date=bool(g.get("label_date", False)),
                    folder=str(g["folder"]).strip() if g.get("folder") else None,
                )
            )

    else:
        # Flat shots list — auto-wrap each into its own group
        shots_raw = data["shots"]
        if not isinstance(shots_raw, list) or not shots_raw:
            raise ValueError("shots must be a non-empty list.")

        for si, s in enumerate(shots_raw):
            shot = _parse_shot(s, f"shots[{si}]")
            if shot.continue_from_prev:
                raise ValueError(
                    f"shots[{si}] ('{shot.id}'): continue is only valid inside "
                    f"a multi-shot group (use 'groups' with output='pdf')."
                )
            groups.append(ShotGroup(id=shot.id, shots=[shot]))

    return RunConfig(base_url=base_url, start=start, defaults=defaults, groups=groups, out_dir=out_dir)
