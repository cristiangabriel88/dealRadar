"""Small helpers shared across source adapters."""

from __future__ import annotations

import re

_TAG_RE = re.compile(r"<[^>]+>")
_MULTISPACE = re.compile(r"\s+")


def strip_html(text: str | None) -> str | None:
    """Flatten an HTML description to plain, whitespace-collapsed text.

    Returns None for empty/None input so the Sleepers scorer can tell "no
    description available" (no signal) from "a genuinely short description"
    (a signal). Tags are replaced with a space so adjacent words don't merge.
    """
    if not text:
        return None
    cleaned = _MULTISPACE.sub(" ", _TAG_RE.sub(" ", text)).strip()
    return cleaned or None
