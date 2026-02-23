from __future__ import annotations

import re
from urllib.parse import urlparse

# UUID pattern: 8-4-4-4-12 hex chars
_UUID_RE = re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
# Numeric ID segments: /123/ or trailing /123
_NUMERIC_RE = re.compile(r"/\d+(?=/|$)")


def desensitize_url(url: str, base_url: str = "") -> str:
    """
    Strip origin, replace UUIDs and numeric IDs with placeholders.
    e.g. http://localhost:4210/brain/accounts/user/edfb2590-.../change/
      -> /brain/accounts/user/{id}/change/
    """
    # Strip origin to get just the path
    if base_url and url.startswith(base_url):
        path = url[len(base_url):]
    else:
        parsed = urlparse(url)
        path = parsed.path

    if not path:
        path = "/"

    # Replace UUIDs first (more specific), then numeric IDs
    path = _UUID_RE.sub("/{id}", path)
    path = _NUMERIC_RE.sub("/{id}", path)

    return path


class _SafeDict(dict):
    """Dict that returns {key} for missing keys instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_label(template: str, variables: dict[str, str]) -> str:
    """
    Render a label template with variables. Unknown {tags} are left as-is.

    Available variables: url, id, title
    """
    return template.format_map(_SafeDict(variables))
