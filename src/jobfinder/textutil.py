"""HTML normalization shared by the adapters."""
from __future__ import annotations

import html
import re

# Script and style bodies must go entirely, not just their tags, or their
# contents end up in the text the relevance filter reads.
_DROP_BLOCKS = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.I | re.S)
_BLOCK = re.compile(r"</(p|div|li|tr|h[1-6]|ul|ol|br)\s*>|<br\s*/?>", re.I)
# Note: this stops at the first ">", so a literal ">" inside an attribute
# value truncates the match. ATS rich-text editors escape those, so a real
# HTML parser is not worth the dependency here.
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def html_to_text(raw: str | None) -> str:
    """Convert (possibly entity-escaped) HTML into collapsed plain text."""
    if not raw:
        return ""
    # Greenhouse ships entity-escaped markup, so decode before stripping.
    text = html.unescape(raw)
    text = _DROP_BLOCKS.sub(" ", text)
    # Keep block boundaries from fusing words together.
    text = _BLOCK.sub(" ", text)
    text = _TAG.sub("", text)
    # Greenhouse can double-encode, so entities may survive the strip.
    text = html.unescape(text)
    return _WS.sub(" ", text).strip()
