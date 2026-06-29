"""SCIP index building and SQLite database access."""

from __future__ import annotations

from ..merge import merge_sqlite_indexes
from .constants import (
    DEFAULT_MAX_HEAP_MB,
    DEFAULT_TS_INDEX_BATCH_SIZE,
    MAX_TS_INDEX_BATCH_SIZE,
)
from .convert import (
    _convert_scip_to_db,
    _document_path_prefix,
    _prefix_document_paths,
    _resolve_scip_binary,
)

# Import core last so sibling modules finish loading before index entry points.
from .core import format_db_size, get_db, index_project, indexer_env, log_index_complete
from .languages import _index_golang_module, _index_python_project, _index_rust_crate
from .orchestrate import (
    _batch_projects,
    _finalize_part_dbs,
    _index_discovered_projects,
    _index_workers,
    _project_batch_label,
    _project_label,
    ts_index_batch_size,
)
from .postprocess import _postprocess_index
from .runners import (
    _install_via_go_install,
    _install_via_npx,
    _install_via_rustup,
    _run_indexer_command,
    _run_subprocess,
    run_indexer_with_fallback,
)
from .typescript import _index_ts_projects, _index_typescript, typescript_projects

__all__ = [
    "DEFAULT_MAX_HEAP_MB",
    "DEFAULT_TS_INDEX_BATCH_SIZE",
    "MAX_TS_INDEX_BATCH_SIZE",
    "_batch_projects",
    "_convert_scip_to_db",
    "_document_path_prefix",
    "_finalize_part_dbs",
    "_index_discovered_projects",
    "_index_golang_module",
    "_index_python_project",
    "_index_rust_crate",
    "_index_ts_projects",
    "_index_typescript",
    "_index_workers",
    "_install_via_go_install",
    "_install_via_npx",
    "_install_via_rustup",
    "_postprocess_index",
    "_prefix_document_paths",
    "_project_batch_label",
    "_project_label",
    "_resolve_scip_binary",
    "_run_indexer_command",
    "_run_subprocess",
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
