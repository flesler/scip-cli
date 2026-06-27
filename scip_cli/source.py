"""Filesystem source reading and definition fallbacks."""

import re
from pathlib import Path

from .queries import get_def_location, resolve_document_path
from .symbols import extract_leaf_name

_resolved_source_paths = {}


def _resolve_source_path(project_root, relative_path):
    """Resolve and validate a project-relative source path (cached per process)."""
    cache_key = (str(project_root), relative_path)
    if cache_key in _resolved_source_paths:
        return _resolved_source_paths[cache_key]

    try:
        root = Path(project_root).resolve()
        full_path = (root / relative_path).resolve()
        full_path.relative_to(root)
    except (ValueError, RuntimeError):
        _resolved_source_paths[cache_key] = None
        return None

    _resolved_source_paths[cache_key] = full_path
    return full_path


def read_source_lines(project_root, relative_path, start_line=None, end_line=None):
    """Read source lines from filesystem."""
    full_path = _resolve_source_path(project_root, relative_path)
    if full_path is None:
        return None

    try:
        with open(full_path, encoding="utf-8") as f:
            lines = f.readlines()
            if start_line is not None and end_line is not None:
                return lines[start_line : end_line + 1]
            return lines
    except (FileNotFoundError, PermissionError, UnicodeDecodeError):
        return None


def fallback_def_location(db, project_root, symbol_str):
    """Best-effort definition location when defn_enclosing_ranges is missing."""
    rel_path = resolve_document_path(db, symbol_str)
    if not rel_path:
        return None

    leaf = extract_leaf_name(symbol_str)
    lines = read_source_lines(project_root, rel_path)
    if not lines:
        return None

    patterns = [
        rf"^\s*(?:async\s+)?{re.escape(leaf)}\s*[\(<]",
        rf"^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+)*{re.escape(leaf)}\s*\??\s*[:=(]",
        rf"^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+)*{re.escape(leaf)}\s*\(",
        rf"^\s*{re.escape(leaf)}\s*\([^)]*\)\s*:\s*",
    ]
    for index, line in enumerate(lines):
        if any(re.match(pattern, line) for pattern in patterns):
            return rel_path, index, index
    return None


def resolve_def_location(db, project_root, symbol_id, symbol_str):
    """Index location, then source-file scan when defn_enclosing_ranges is missing."""
    row = get_def_location(db, symbol_id)
    if row:
        return row
    return fallback_def_location(db, project_root, symbol_str)
