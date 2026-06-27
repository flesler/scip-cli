"""Shared constants for scip-cli."""

import os

INDEX_TIMEOUT = 300
DEFAULT_MAX_HEAP_MB = 8192
DEFAULT_MAX_DEF_LINES = 80
DEFAULT_MAX_DEF_CHARS = 32_000
SCIP_INSTALL_URL = "https://github.com/scip-code/scip/releases"
INDEX_STALE_WARN_SECONDS = 7 * 24 * 60 * 60


def default_index_workers() -> int:
    """Default parallel TypeScript project indexers (merge stays single-threaded)."""
    return min(8, os.cpu_count() or 4)
