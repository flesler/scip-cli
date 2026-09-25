"""Force re-indexing of the current project."""

import sys
import time

from ..cache import (
    cleanup_in_progress_index,
    get_cache_dir,
    index_build_lock,
    index_db_path,
    promote_next_index,
)
from ..indexing import index_project, log_index_complete
from ..indexing.shards import clear_shard_cache
from ..indexing.source_discovery import is_versioned_repo
from ..metadata import UNSET, apply_metadata_updates, index_unversioned
from ..paths import normalize_path_scope
from ..project import Language, find_project_root_and_language
from ..sql import finalize_index_db
from ..tsconfig import expand_tsconfig_patterns


def main(args):
    root, lang = find_project_root_and_language()
    if not root:
        print("Error: Could not find project root", file=sys.stderr)
        sys.exit(1)

    path_args = getattr(args, "path", None) or []
    tsconfig_args = getattr(args, "tsconfig", None) or []
    exclude_groups = getattr(args, "exclude", None)
    fresh = getattr(args, "fresh", False)
    incremental = getattr(args, "incremental", False)
    unversioned = getattr(args, "unversioned", False)
    if incremental and fresh:
        print("Error: reindex --incremental and --fresh cannot be combined", file=sys.stderr)
        sys.exit(1)
    if incremental and lang is not None and lang != Language.TYPESCRIPT:
        print("Error: reindex --incremental is only supported for TypeScript projects", file=sys.stderr)
        sys.exit(1)
    if incremental and (index_unversioned(root) or not is_versioned_repo(root)):
        print(
            (
                "Error: reindex --incremental requires a git repository "
                "(use full reindex without --incremental for --unversioned or non-git projects)"
            ),
            file=sys.stderr,
        )
        sys.exit(1)
    if path_args and tsconfig_args:
        print("Error: reindex --path and --tsconfig cannot be combined", file=sys.stderr)
        sys.exit(1)
    if (path_args or tsconfig_args) and lang != Language.TYPESCRIPT:
        flag = "--tsconfig" if tsconfig_args else "--path"
        print(f"Error: reindex {flag} is only supported for TypeScript projects", file=sys.stderr)
        sys.exit(1)

    scope_update: list[str] | object | None = UNSET
    if tsconfig_args:
        try:
            tsconfig_paths = expand_tsconfig_patterns(tsconfig_args, root)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        scope_paths = [path.as_posix() for path in tsconfig_paths]
        scope_update = scope_paths
        if len(scope_paths) == 1:
            print(f"Index scope: {scope_paths[0]}", file=sys.stderr)
        else:
            patterns = ", ".join(tsconfig_args)
            print(f"Index scope: {patterns} ({len(scope_paths)} tsconfigs)", file=sys.stderr)
    elif path_args:
        scope_paths: list[str] = []
        for path in path_args:
            normalized = normalize_path_scope(path, root)
            if normalized is None:
                print(f"Error: invalid or empty --path: {path!r}", file=sys.stderr)
                sys.exit(1)
            scope_paths.append(normalized)
        scope_update = scope_paths
        if len(scope_paths) == 1:
            print(f"Index scope: {scope_paths[0]}", file=sys.stderr)
        else:
            print(f"Index scope: {len(scope_paths)} paths", file=sys.stderr)

    exclude_update: list[str] | object = UNSET
    if exclude_groups is not None:
        exclude_globs = [glob for group in exclude_groups for glob in group]
        exclude_update = exclude_globs
        if exclude_globs:
            print(f"Index exclude: {', '.join(exclude_globs)}", file=sys.stderr)

    cache_dir = get_cache_dir(root)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if lang is None:
        print(f"Error: No supported project markers found in {root}", file=sys.stderr)
        sys.exit(1)

    with index_build_lock(cache_dir):
        apply_metadata_updates(
            root,
            fresh=fresh,
            scope_paths=scope_update,
            exclude_globs=exclude_update,
            unversioned=unversioned if unversioned else UNSET,
        )
        cleanup_in_progress_index(cache_dir)
        if fresh or not incremental:
            clear_shard_cache(cache_dir)
        try:
            # Pass --with-external flag to indexer via environment
            if getattr(args, "with_external", False):
                import os

                os.environ["SCIP_CLI_KEEP_EXTERNAL"] = "1"

            started = time.perf_counter()
            _output_db, skipped, total, promote = index_project(
                root,
                lang,
                cache_dir,
                replace=True,
                log=False,
                incremental=incremental,
            )
            elapsed_seconds = time.perf_counter() - started
        except RuntimeError as e:
            cleanup_in_progress_index(cache_dir)
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        live_db = index_db_path(cache_dir, replace=False)
        from scip_cli.indexing.performance import phase

        if promote:
            next_db = index_db_path(cache_dir, replace=True)
            if not next_db.is_file():
                cleanup_in_progress_index(cache_dir)
                print("Error: No index.db found after indexing", file=sys.stderr)
                sys.exit(1)
            with phase("finalize"):
                finalize_index_db(next_db)
            with phase("promote"):
                promote_next_index(cache_dir)
        elif live_db.is_file():
            with phase("finalize"):
                finalize_index_db(live_db)
        elif not live_db.is_file():
            cleanup_in_progress_index(cache_dir)
            print("Error: No index.db found after indexing", file=sys.stderr)
            sys.exit(1)
        log_index_complete(
            index_db_path(cache_dir, replace=False),
            lang.value,
            projects=total if total > 1 else None,
            skipped=skipped,
            elapsed_seconds=elapsed_seconds,
        )
