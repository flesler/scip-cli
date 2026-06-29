"""Heuristics for disambiguating file paths vs symbol names in CLI targets."""

from __future__ import annotations

import re

_FILE_TARGET_RE = re.compile(r"\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs)$", re.I)


def looks_like_file_target(target: str) -> bool:
    """Return True when a CLI target is more likely a file path than a symbol.

    Qualified symbols like ``Transcriber.getMatch`` contain dots but are not files.
    """
    if "/" in target or "\\" in target:
        return True
    return bool(_FILE_TARGET_RE.search(target))
