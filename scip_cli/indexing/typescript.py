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
from .constants import PROGRESS_LOG_MIN_PROJECTS
from .convert import convert_scip_to_db
from .orchestrate import (
    batch_projects,
    finalize_part_dbs,
    index_workers,
    project_batch_label,
    ts_batch_limit_display,
    ts_index_batch_size,
)
from .runners import run_indexer_with_fallback


def typescript_projects(root: Path) -> list[Path]:
    """Resolve the TypeScript project list for a repository."""
    settings = load_project_config(root)
    scope = load_index_scope(root)

    if scope is not None:
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


def _typescript_index_args(root, output_scip, projects):
    args = ["index", "--output", str(output_scip)]
    root = Path(root)
    if not (root / "tsconfig.json").exists():
        args.insert(1, "--infer-tsconfig")
    args.extend(str(project) for project in projects)
    return args


def index_ts_projects(root, projects, work_dir, env, *, output_db: Path | None = None):
    """Index one or more TypeScript projects into work_dir/index.db (or output_db when set)."""
    root = Path(root)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = project_batch_label(projects)
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    index_args = _typescript_index_args(root, part_scip, projects)
    result = run_indexer_with_fallback(
        "scip-typescript",
        index_args,
        str(root),
        env=env,
        npx_package="@sourcegraph/scip-typescript",
    )
    if result.returncode != 0:
        return label, None, result.stderr.strip() or "indexing failed"
    try:
        convert_scip_to_db(part_scip, db_path)
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None


def index_typescript(root, cache_dir, projects, env, *, replace=False):
    """Index one or more TypeScript projects and write the merged index.db."""
    root = Path(root)
    cache_dir = Path(cache_dir)
    output_db = index_db_path(cache_dir, replace=replace)
    workers = index_workers()
    batches = batch_projects(projects, ts_index_batch_size())
    use_parallel = len(batches) > 1 and workers > 1

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        part_dbs: list[Path] = []
        skipped = 0
        total = len(projects)
        show_progress = total > PROGRESS_LOG_MIN_PROJECTS

        if show_progress and use_parallel:
            batch_size = ts_index_batch_size()
            batch_desc = ts_batch_limit_display(batch_size, total)
            print(
                f"Indexing {total} TypeScript projects ({workers} workers, {batch_desc}; merge is serial)...",
                file=sys.stderr,
            )

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
                )
                indexed += len(batch)
                if db_path is None:
                    skipped += len(batch)
                    print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                    continue
                part_dbs.append(db_path)

        if not part_dbs:
            raise RuntimeError("Failed to index project")

        finalize_part_dbs(part_dbs, output_db)

        return output_db, len(part_dbs), skipped, total
