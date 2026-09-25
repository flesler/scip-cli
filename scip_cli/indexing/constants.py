"""Indexing constants."""

import os

INDEX_TIMEOUT = 300
DEFAULT_MAX_HEAP_MB = 8192
PROGRESS_LOG_MIN_PROJECTS = 10
SCIP_INSTALL_URL = "https://github.com/scip-code/scip/releases"

# Language indexers (npx / go install) use latest on first use.
# The scip expt-convert binary is pinned separately in scip_tool.py (DB schema).
#
# scip-typescript npx fallback (when the binary is not on PATH). Fork adds --files
# for partial document indexing (see docs/benchmarks.md). Pin >= ce6e9c9.
SCIP_TYPESCRIPT_NPX_PACKAGE = "github:flesler/scip-typescript#feat/partial-files"


def file_incremental_enabled() -> bool:
    """Partial reindex via fork --files (default on)."""
    return os.environ.get("SCIP_CLI_FILE_INCREMENTAL", "1").lower() not in {"0", "false", "no"}


# scip-typescript accepts many tsconfig paths per invocation (one .scip, one convert, no merge).
# Split only when SCIP_CLI_TS_INDEX_BATCH_SIZE is set (OOM/timeout tuning).
DEFAULT_TS_INDEX_BATCH_SIZE = None
MAX_TS_INDEX_BATCH_SIZE = 2_147_483_647
