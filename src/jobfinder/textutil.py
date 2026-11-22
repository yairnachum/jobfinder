"""HTML normalization shared by the adapters."""
from __future__ import annotations

import html
import re

_BLOCK = re.compile(r"</(p|div|li|tr|h[1-6]|ul|ol|br)\s*>|<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def html_to_text(raw: str | None) -> str:
    """Convert (possibly entity-escaped) HTML into collapsed plain text."""
    if not raw:
        return ""
    # Greenhouse ships entity-escaped markup, so decode before stripping.
    text = html.unescape(raw)
    # Keep block boundaries from fusing words together.
    text = _BLOCK.sub(" ", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    return _WS.sub(" ", text).strip()
