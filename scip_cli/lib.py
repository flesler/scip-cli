"""Backward-compatible re-exports. Prefer importing from domain modules directly."""
from .cache import find_db, get_cache_dir
from .constants import DEFAULT_MAX_DEF_LINES, DEFAULT_MAX_HEAP_MB
from .indexing import get_db, indexer_env as _indexer_env, typescript_projects as _typescript_projects
from .output import (
    format_def_body,
    format_line_range,
    limit_and_warn,
    print_def_truncation_notice,
    resolve_max_def_lines,
    warn_ambiguous,
)
from .paths import normalize_path_scope, path_filter_sql, path_in_scope
from .project import detect_language, find_project_root
from .queries import (
    get_def_location,
    get_file_symbols,
    get_members,
    get_refs_for_symbols,
    resolve_document_path,
    resolve_file,
    resolve_symbol,
)
from .session import resolve_one_file, resolve_one_symbol, setup
from .source import fallback_def_location, read_source_lines
from .sql import escape_like
from .symbols import SymbolKind, extract_leaf_name, infer_kind

__all__ = [
    "DEFAULT_MAX_DEF_LINES",
    "DEFAULT_MAX_HEAP_MB",
    "SymbolKind",
    "_indexer_env",
    "_typescript_projects",
    "detect_language",
    "escape_like",
    "extract_leaf_name",
    "fallback_def_location",
    "find_db",
    "find_project_root",
    "format_def_body",
    "format_line_range",
    "get_cache_dir",
    "get_db",
    "get_def_location",
    "get_file_symbols",
    "get_members",
    "get_refs_for_symbols",
    "infer_kind",
    "limit_and_warn",
    "normalize_path_scope",
    "path_filter_sql",
    "path_in_scope",
    "print_def_truncation_notice",
    "read_source_lines",
    "resolve_document_path",
    "resolve_file",
    "resolve_max_def_lines",
    "resolve_one_file",
    "resolve_one_symbol",
    "resolve_symbol",
    "setup",
    "warn_ambiguous",
]
