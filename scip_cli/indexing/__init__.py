"""SCIP index building and SQLite database access."""

from __future__ import annotations

from ..merge import merge_sqlite_indexes
from .constants import (
    DEFAULT_MAX_HEAP_MB,
    DEFAULT_TS_INDEX_BATCH_SIZE,
    MAX_TS_INDEX_BATCH_SIZE,
)
from .core import format_db_size, get_db, index_project, indexer_env, log_index_complete
from .orchestrate import ts_index_batch_size
from .runners import run_indexer_with_fallback
from .typescript import typescript_projects

__all__ = [
    "DEFAULT_MAX_HEAP_MB",
    "DEFAULT_TS_INDEX_BATCH_SIZE",
    "MAX_TS_INDEX_BATCH_SIZE",
    "format_db_size",
    "get_db",
    "index_project",
    "indexer_env",
    "log_index_complete",
    "merge_sqlite_indexes",
    "run_indexer_with_fallback",
    "ts_index_batch_size",
    "typescript_projects",
]
