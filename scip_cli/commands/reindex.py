"""Force re-indexing of the current project."""

import sys

from ..cache import (
    cleanup_in_progress_index,
    get_cache_dir,
    index_db_path,
    promote_next_index,
)
from ..indexing import _index_project, log_index_complete
from ..paths import normalize_path_scope
from ..project import find_project_root_and_language
from ..scope import save_index_scope


def main(args):
    root, lang = find_project_root_and_language()
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

    if lang is None:
        print(f"Error: No supported project markers found in {root}", file=sys.stderr)
        sys.exit(1)

    try:
        _output_db, skipped, total = _index_project(root, lang, cache_dir, replace=True, log=False)
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
    log_index_complete(
        index_db_path(cache_dir, replace=False),
        lang.value,
        projects=total if total > 1 else None,
        skipped=skipped,
    )
