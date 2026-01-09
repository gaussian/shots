from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urldefrag, urlparse


def now_ts() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def safe_filename(name: str, max_len: int = 120) -> str:
    name = (name or "").strip().lower()
    name = re.sub(r"[^a-z0-9\-_.]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name[:max_len] or "shot"


def normalize_url(url: str) -> str:
    # Drop fragments only; query can matter in SPAs
    u, _ = urldefrag(url)
    return u


def is_http_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in ("http", "https")
    except Exception:
        return False


def same_origin(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def compact_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


@dataclass
class StepOutcome:
    ok: bool
    error: str | None = None
    extra: dict[str, Any] | None = None
