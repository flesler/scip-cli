"""Force re-indexing of the current project."""
import sys

from ..cache import (
    cleanup_in_progress_index,
    get_cache_dir,
    index_db_path,
    promote_next_index,
)
from ..indexing import _index_project
from ..paths import normalize_path_scope
from ..project import detect_language, find_project_root
from ..scope import save_index_scope


def main(args):
    root = find_project_root()
    if not root:
        print("Error: Could not find project root", file=sys.stderr)
        sys.exit(1)

    path_args = getattr(args, "path", None) or []
    if path_args:
        scope_paths = [normalize_path_scope(path, root) for path in path_args]
        save_index_scope(root, scope_paths)
        print(f"Index scope: {', '.join(scope_paths)}", file=sys.stderr)
    else:
        save_index_scope(root, None)

    cache_dir = get_cache_dir(root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cleanup_in_progress_index(cache_dir)

    lang = detect_language(root)
    if lang is None:
        print(f"Error: No supported project markers found in {root}", file=sys.stderr)
        sys.exit(1)

    print(f"Re-indexing {root} ({lang})...", file=sys.stderr)
    try:
        _index_project(root, lang, cache_dir, replace=True)
    except RuntimeError as e:
        cleanup_in_progress_index(cache_dir)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    next_db = index_db_path(cache_dir, replace=True)
    if not next_db.is_file():
        cleanup_in_progress_index(cache_dir)
        print("Error: No index.db found after indexing", file=sys.stderr)
        sys.exit(1)

    promote_next_index(cache_dir)
    print(f"Updated {index_db_path(cache_dir, replace=False)}", file=sys.stderr)
    print("Re-indexing complete", file=sys.stderr)
