"""Parallel indexing orchestration and batch helpers."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..cache import index_db_path
from ..merge import merge_sqlite_indexes
from .constants import (
    DEFAULT_TS_INDEX_BATCH_SIZE,
    MAX_TS_INDEX_BATCH_SIZE,
    PROGRESS_LOG_MIN_PROJECTS,
)


def _index_workers():
    """Parallel workers for per-project indexer runs (merge stays serial)."""
    env_val = os.environ.get("SCIP_CLI_INDEX_WORKERS")
    if env_val is not None:
        try:
            return max(1, int(env_val))
        except ValueError:
            raise RuntimeError(f"Invalid SCIP_CLI_INDEX_WORKERS: expected an integer, got {env_val!r}") from None
    return min(8, os.cpu_count() or 4)


def ts_index_batch_size() -> int | None:
    """Max TypeScript projects per scip-typescript invocation (None = all in one run)."""
    env_val = os.environ.get("SCIP_CLI_TS_INDEX_BATCH_SIZE")
    if env_val is not None:
        try:
            parsed = int(env_val)
        except ValueError:
            raise RuntimeError(f"Invalid SCIP_CLI_TS_INDEX_BATCH_SIZE: expected an integer, got {env_val!r}") from None
        if parsed < 1:
            raise RuntimeError(f"Invalid SCIP_CLI_TS_INDEX_BATCH_SIZE: expected a positive integer, got {parsed}")
        if parsed > MAX_TS_INDEX_BATCH_SIZE:
            raise RuntimeError(f"SCIP_CLI_TS_INDEX_BATCH_SIZE={parsed} exceeds max ({MAX_TS_INDEX_BATCH_SIZE})")
        return parsed
    return DEFAULT_TS_INDEX_BATCH_SIZE


def _batch_projects(projects: list[Path], batch_size: int | None) -> list[list[Path]]:
    if not projects:
        return []
    if batch_size is None:
        return [projects]
    return [projects[i : i + batch_size] for i in range(0, len(projects), batch_size)]


def _ts_batch_limit_display(batch_size: int | None, total: int) -> str:
    if batch_size is None or batch_size >= total:
        return "all tsconfigs per run"
    return f"up to {batch_size} tsconfigs per run"


def _project_label(project: Path) -> str:
    return "." if project == Path(".") else str(project)


def _project_batch_label(projects: list[Path]) -> str:
    if len(projects) == 1:
        return _project_label(projects[0])
    first = _project_label(projects[0])
    return f"{first} +{len(projects) - 1} more"


def _finalize_part_dbs(part_dbs: list[Path], output_db: Path) -> None:
    if len(part_dbs) == 1:
        if part_dbs[0] != output_db:
            shutil.move(str(part_dbs[0]), str(output_db))
    else:
        merge_sqlite_indexes(part_dbs, output_db)


def _index_discovered_projects(
    root: Path,
    cache_dir: Path,
    projects: list[Path],
    env,
    *,
    replace: bool,
    progress_noun: str,
    index_one,
) -> tuple[Path, int, int, int]:
    """Index one SCIP unit per project path; merge when multiple part DBs."""
    output_db = index_db_path(cache_dir, replace=replace)
    workers = _index_workers()
    total = len(projects)
    use_parallel = total > 1 and workers > 1
    show_progress = total > PROGRESS_LOG_MIN_PROJECTS

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        part_dbs: list[Path] = []
        skipped = 0

        if show_progress and use_parallel:
            print(
                f"Indexing {total} {progress_noun} ({workers} workers; merge is serial)...",
                file=sys.stderr,
            )

        if use_parallel:
            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        index_one,
                        root,
                        project,
                        tmpdir_path / f"part-{index}",
                        env,
                    ): (index, project)
                    for index, project in enumerate(projects, start=1)
                }
                indexed_parts: list[tuple[int, Path]] = []
                for future in as_completed(futures):
                    part_index, project = futures[future]
                    label, db_path, error = future.result()
                    completed += 1
                    if db_path is None:
                        skipped += 1
                        print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                    else:
                        indexed_parts.append((part_index, db_path))
                        if show_progress:
                            print(f"Indexed {completed}/{total}: {label}", file=sys.stderr)
            part_dbs = [db for _, db in sorted(indexed_parts, key=lambda item: item[0])]
        else:
            for index, project in enumerate(projects, start=1):
                label = _project_label(project)
                if show_progress:
                    print(f"Indexing {index}/{total}: {label}", file=sys.stderr)
                direct_output = output_db if total == 1 else None
                label, db_path, error = index_one(
                    root,
                    project,
                    cache_dir if direct_output else tmpdir_path / f"part-{index}",
                    env,
                    output_db=direct_output,
                )
                if db_path is None:
                    skipped += 1
                    print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                    continue
                part_dbs.append(db_path)

        if not part_dbs:
            raise RuntimeError("Failed to index project")

        _finalize_part_dbs(part_dbs, output_db)
        return output_db, len(part_dbs), skipped, total
