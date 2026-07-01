"""Force re-indexing of the current project."""

import sys

from ..cache import (
    cleanup_in_progress_index,
    get_cache_dir,
    index_build_lock,
    index_db_path,
    promote_next_index,
)
from ..indexing import index_project, log_index_complete
from ..paths import normalize_path_scope
from ..project import Language, find_project_root_and_language
from ..scope import save_index_scope


def main(args):
    root, lang = find_project_root_and_language()
    if not root:
        print("Error: Could not find project root", file=sys.stderr)
        sys.exit(1)

    path_args = getattr(args, "path", None) or []
    if path_args and lang != Language.TYPESCRIPT:
        print("Error: reindex --path is only supported for TypeScript projects", file=sys.stderr)
        sys.exit(1)

    if path_args:
        scope_paths: list[str] = []
        for path in path_args:
            normalized = normalize_path_scope(path, root)
            if normalized is None:
                print(f"Error: invalid or empty --path: {path!r}", file=sys.stderr)
                sys.exit(1)
            scope_paths.append(normalized)
        save_index_scope(root, scope_paths)
        print(f"Index scope: {', '.join(scope_paths)}", file=sys.stderr)
        print(
            (
                "Warning: scoped reindex replaces the cache with only these projects; "
                "run reindex with no --path to restore the full index"
            ),
            file=sys.stderr,
        )
    else:
        save_index_scope(root, None)

    cache_dir = get_cache_dir(root)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if lang is None:
        print(f"Error: No supported project markers found in {root}", file=sys.stderr)
        sys.exit(1)

    with index_build_lock(cache_dir):
        cleanup_in_progress_index(cache_dir)
        try:
            # Pass --with-external flag to indexer via environment
            if getattr(args, "with_external", False):
                import os

                os.environ["SCIP_CLI_KEEP_EXTERNAL"] = "1"

            _output_db, skipped, total = index_project(root, lang, cache_dir, replace=True, log=False)
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
