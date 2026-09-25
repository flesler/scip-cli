"""TypeScript project resolution and indexing."""

from __future__ import annotations

import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..cache import index_db_path
from ..config import CONFIG_FILENAME, load_project_config, resolve_index_roots
from ..discover import discover_typescript_projects
from ..scope import load_index_scope, projects_matching_scope
from ..tsconfig import scope_tsconfig_paths
from .constants import PROGRESS_LOG_MIN_PROJECTS
from .orchestrate import (
    batch_projects,
    effective_ts_batch_size,
    finalize_part_dbs,
    index_workers,
    project_batch_label,
)
from .performance import flush_summary, phase
from .ts_projects import index_ts_projects, typescript_index_args


def typescript_projects(root: Path) -> list[Path]:
    """Resolve the TypeScript project list for a repository."""
    settings = load_project_config(root)
    scope = load_index_scope(root)

    if scope is not None:
        tsconfig_files = scope_tsconfig_paths(scope.paths)
        if tsconfig_files is not None:
            return tsconfig_files
        discovered = list(discover_typescript_projects(root))
        filtered = projects_matching_scope(discovered, scope.paths)
        if not filtered:
            joined = ", ".join(scope.paths)
            raise RuntimeError(f"No TypeScript projects found under index scope: {joined}")
        return sorted(filtered, key=str)

    configured = resolve_index_roots(root, settings) if settings.index_roots else []

    if settings.only_index_roots:
        if not configured:
            raise RuntimeError(f"onlyIndexRoots is true but no indexRoots are configured in {CONFIG_FILENAME}")
        return configured

    discovered = list(discover_typescript_projects(root))
    merged = {str(path): path for path in discovered}
    for path in configured:
        merged[str(path)] = path
    return sorted(merged.values(), key=str)


# Re-export for tests and callers that monkeypatch this module.
_typescript_index_args = typescript_index_args


def index_typescript(
    root,
    cache_dir,
    projects,
    env,
    *,
    replace=False,
    exclude_globs: tuple[str, ...] = (),
    incremental: bool = False,
) -> tuple[Path, int, int, int, bool]:
    """Index one or more TypeScript projects and write the merged index.db.

    Returns (output_db, indexed_count, skipped, total, promote_needed).
    """
    root = Path(root)
    cache_dir = Path(cache_dir)
    if incremental:
        from .incremental import index_typescript_incremental

        return index_typescript_incremental(
            root,
            cache_dir,
            projects,
            env,
            replace=replace,
            exclude_globs=exclude_globs,
        )
    output_db = index_db_path(cache_dir, replace=replace)
    workers = index_workers()
    batch_size = effective_ts_batch_size(projects)
    batches = batch_projects(projects, batch_size)
    use_parallel = len(batches) > 1 and workers > 1

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        part_dbs: list[Path] = []
        skipped = 0
        total = len(projects)
        show_progress = total > PROGRESS_LOG_MIN_PROJECTS

        if use_parallel:
            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        index_ts_projects,
                        root,
                        batch,
                        tmpdir_path / f"part-{index}",
                        env,
                        exclude_globs=exclude_globs,
                    ): (index, batch)
                    for index, batch in enumerate(batches, start=1)
                }
                indexed_parts: list[tuple[int, Path]] = []
                for future in as_completed(futures):
                    batch_index, batch = futures[future]
                    label, db_path, error = future.result()
                    completed += len(batch)
                    if db_path is None:
                        skipped += len(batch)
                        print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                    else:
                        indexed_parts.append((batch_index, db_path))
                        if show_progress:
                            print(f"Indexed {completed}/{total}: {label}", file=sys.stderr)
            part_dbs = [db for _, db in sorted(indexed_parts, key=lambda item: item[0])]
        else:
            indexed = 0
            for index, batch in enumerate(batches, start=1):
                label = project_batch_label(batch)
                if show_progress:
                    end = indexed + len(batch)
                    print(f"Indexing {indexed + 1}-{end}/{total}: {label}", file=sys.stderr)
                direct_output = output_db if len(batches) == 1 else None
                label, db_path, error = index_ts_projects(
                    root,
                    batch,
                    cache_dir if direct_output else tmpdir_path / f"part-{index}",
                    env,
                    output_db=direct_output,
                    exclude_globs=exclude_globs,
                )
                indexed += len(batch)
                if db_path is None:
                    skipped += len(batch)
                    print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                    continue
                part_dbs.append(db_path)

        if not part_dbs:
            raise RuntimeError("Failed to index project")

        with phase("merge"):
            finalize_part_dbs(part_dbs, output_db)

        flush_summary()
        return output_db, len(part_dbs), skipped, total, True
