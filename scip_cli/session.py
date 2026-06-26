"""Command session setup and single-match resolution helpers."""
import sys
from pathlib import Path

from .config import load_project_config
from .indexing import get_db
from .output import warn_ambiguous
from .project import find_project_root
from .queries import resolve_file, resolve_symbol


def setup():
    """Find project root and return an open index database connection."""
    project_root = find_project_root()
    if not project_root:
        print("Error: Could not find project root", file=sys.stderr)
        sys.exit(1)
    try:
        load_project_config(Path(project_root))
        db = get_db(project_root)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    return db, project_root


def resolve_one_symbol(db, name, kind_filter=None, path_scope=None):
    """Resolve a symbol name to a single symbol, warning if ambiguous."""
    symbols = resolve_symbol(db, name, kind_filter, path_scope=path_scope)
    if not symbols:
        print(f"Symbol '{name}' not found", file=sys.stderr)
        sys.exit(1)

    warn_ambiguous(name, symbols, "symbol")
    return symbols[0]


def resolve_one_file(db, pattern, path_scope=None):
    """Resolve a file pattern to a single path, warning if ambiguous."""
    files = resolve_file(db, pattern, path_scope=path_scope)
    if not files:
        print(f"File '{pattern}' not found", file=sys.stderr)
        sys.exit(1)

    warn_ambiguous(pattern, files, "file")
    return files[0]
