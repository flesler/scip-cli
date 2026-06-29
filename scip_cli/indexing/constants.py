"""Indexing constants."""

INDEX_TIMEOUT = 300
DEFAULT_MAX_HEAP_MB = 8192
PROGRESS_LOG_MIN_PROJECTS = 10
SCIP_INSTALL_URL = "https://github.com/scip-code/scip/releases"

# Language indexers (npx / go install) use latest on first use.
# The scip expt-convert binary is pinned separately in scip_tool.py (DB schema).
# scip-typescript accepts many tsconfig paths per invocation (one .scip, one convert, no merge).
# Split only when SCIP_CLI_TS_INDEX_BATCH_SIZE is set (OOM/timeout tuning).
DEFAULT_TS_INDEX_BATCH_SIZE = None
MAX_TS_INDEX_BATCH_SIZE = 2_147_483_647
