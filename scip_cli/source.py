"""Filesystem source reading and definition fallbacks."""
import re
from pathlib import Path

from .queries import resolve_document_path
from .symbols import extract_leaf_name


def read_source_lines(project_root, relative_path, start_line=None, end_line=None):
    """Read source lines from filesystem."""
    try:
        root = Path(project_root).resolve()
        try:
            full_path = (root / relative_path).resolve()
            full_path.relative_to(root)
        except (ValueError, RuntimeError):
            return None
        with open(full_path, "r", encoding="utf-8") as f:
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
