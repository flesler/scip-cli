"""Incremental TypeScript reindex via git manifest and in-place index.db upsert."""

from __future__ import annotations

import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from ..cache import index_db_path
from ..debug import debug_log
from .document_upsert import document_paths_in_db, remove_documents_by_paths, upsert_shard_documents
from .git_delta import (
    GitIndexDelta,
    clear_git_delta_cache,
    git_index_delta,
    git_is_ancestor,
    shard_dirty_paths,
)
from .orchestrate import batch_projects, finalize_part_dbs, index_workers, project_batch_label
from .performance import flush_summary, metric, phase
from .shard_files import PartialReindexPlan, resolve_partial_reindex_plan, shard_relative_paths
from .shards import (
    load_manifest_data,
    save_shard_manifest,
    shard_entry_for_project,
    shard_is_clean,
    shard_key,
)


@dataclass(frozen=True)
class ShardUpdate:
    upsert_paths: frozenset[str]
    remove_paths: frozenset[str]
    part_db: Path | None


def apply_shard_update(output_db: Path, update: ShardUpdate) -> None:
    if update.part_db is not None and update.upsert_paths:
        with phase("upsert_paths"):
            upsert_shard_documents(output_db, update.part_db, update.upsert_paths)
    if update.remove_paths:
        with phase("remove_paths"):
            remove_documents_by_paths(output_db, update.remove_paths)


def apply_shard_updates(output_db: Path, updates: list[ShardUpdate]) -> None:
    for update in updates:
        apply_shard_update(output_db, update)


def _full_shard_remove_paths(
    root: Path,
    project: Path,
    index_db: Path,
    part_db: Path,
    delta: GitIndexDelta | None,
    partial: PartialReindexPlan | None,
) -> frozenset[str]:
    """Paths to drop after a full-shard reindex (git deletions + stale live rows)."""
    out: set[str] = set()
    if partial is not None:
        out.update(partial.remove_paths)
    if delta is not None:
        _, removed = shard_dirty_paths(root, project, delta)
        out.update(removed)
    shard_paths = shard_relative_paths(root, project)
    if index_db.is_file():
        live = document_paths_in_db(index_db) & shard_paths
        new = document_paths_in_db(part_db)
        out.update(live - new)
    return frozenset(out)


def _index_dirty_shard(
    root: Path,
    batch: list[Path],
    work_dir: Path,
    env,
    *,
    exclude_globs: tuple[str, ...],
    manifest_entry: dict[str, object] | None,
    index_db: Path,
    delta: GitIndexDelta | None,
) -> tuple[str, ShardUpdate | None, str | None]:
    project = batch[0]
    partial: PartialReindexPlan | None = None
    if delta is not None:
        partial = resolve_partial_reindex_plan(
            root,
            project,
            manifest_entry,
            index_db,
            delta,
            exclude_globs=exclude_globs,
        )

    if partial is not None and not partial.index_paths and not partial.remove_paths:
        return (
            project_batch_label(batch),
            ShardUpdate(upsert_paths=frozenset(), remove_paths=frozenset(), part_db=None),
            None,
        )

    if partial is not None and not partial.index_paths and partial.remove_paths:
        return (
            project_batch_label(batch),
            ShardUpdate(upsert_paths=frozenset(), remove_paths=partial.remove_paths, part_db=None),
            None,
        )

    from .ts_projects import index_ts_projects

    with phase("parallel_index_shard"):
        label, db_path, error = index_ts_projects(
            root,
            batch,
            work_dir,
            env,
            exclude_globs=exclude_globs,
            index_files=partial.index_paths if partial and partial.index_paths else None,
        )
    if db_path is None:
        return label, None, error

    if partial is not None and partial.index_paths:
        return (
            label,
            ShardUpdate(
                upsert_paths=frozenset(partial.index_paths),
                remove_paths=partial.remove_paths,
                part_db=db_path,
            ),
            None,
        )

    return (
        label,
        ShardUpdate(
            upsert_paths=document_paths_in_db(db_path),
            remove_paths=_full_shard_remove_paths(root, project, index_db, db_path, delta, partial),
            part_db=db_path,
        ),
        None,
    )


def index_typescript_incremental(
    root: Path,
    cache_dir: Path,
    projects: list[Path],
    env,
    *,
    replace: bool = False,
    exclude_globs: tuple[str, ...] = (),
) -> tuple[Path, int, int, int, bool]:
    """Git delta shard skip, partial --files reindex, and in-place index.db upsert."""
    from .constants import PROGRESS_LOG_MIN_PROJECTS

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_db = index_db_path(cache_dir, replace=replace)
    live_db = index_db_path(cache_dir, replace=False)
    workers = index_workers()
    batches = batch_projects(projects, 1)
    use_parallel = len(batches) > 1 and workers > 1
    clear_git_delta_cache()
    manifest, manifest_git_commit = load_manifest_data(cache_dir)
    delta: GitIndexDelta | None = None
    if manifest_git_commit and git_is_ancestor(root, manifest_git_commit):
        delta = git_index_delta(root, manifest_git_commit)

    updated_shards: dict[str, dict[str, object]] = {}
    reused = 0
    skipped = 0
    total = len(projects)
    show_progress = total > PROGRESS_LOG_MIN_PROJECTS

    dirty_batches: list[tuple[int, list[Path], dict[str, object] | None]] = []
    with phase("git_delta_scan"):
        for index, batch in enumerate(batches, start=1):
            project = batch[0]
            key = shard_key(project)
            entry = manifest.get(key)
            if live_db.is_file() and shard_is_clean(
                root,
                project,
                entry,
                manifest_git_commit,
                delta,
                exclude_globs=exclude_globs,
            ):
                reused += 1
                if isinstance(entry, dict):
                    updated_shards[key] = dict(entry)
                if show_progress:
                    print(f"Reused shard: {key}", file=sys.stderr)
                continue
            dirty_batches.append((index, batch, entry if isinstance(entry, dict) else None))

    metric("shards_reused", reused)
    metric("shards_dirty", len(dirty_batches))

    if not dirty_batches and live_db.is_file():
        save_shard_manifest(cache_dir, updated_shards, project_root=root)
        print(f"Incremental: {reused} shard(s) reused, 0 reindexed", file=sys.stderr)
        flush_summary()
        return live_db, 0, skipped, total, False

    if delta is None and manifest_git_commit:
        delta = git_index_delta(root, manifest_git_commit)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        ordered_updates: list[tuple[int, ShardUpdate]] = []

        if dirty_batches:

            def _log_scope(project: Path, manifest_entry: dict[str, object] | None) -> None:
                if delta is None:
                    return
                partial = resolve_partial_reindex_plan(
                    root,
                    project,
                    manifest_entry,
                    live_db,
                    delta,
                    exclude_globs=exclude_globs,
                )
                if partial is None:
                    return
                message = f"Incremental file scope for {shard_key(project)}: {len(partial.index_paths)} to index"
                if partial.remove_paths:
                    message += f", {len(partial.remove_paths)} to remove"
                debug_log(message)

            if use_parallel and len(dirty_batches) > 1:
                with phase("parallel_index"), ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = {
                        pool.submit(
                            _index_dirty_shard,
                            root,
                            batch,
                            tmpdir_path / f"part-{index}",
                            env,
                            exclude_globs=exclude_globs,
                            manifest_entry=manifest_entry,
                            index_db=live_db,
                            delta=delta,
                        ): (index, batch, manifest_entry)
                        for index, batch, manifest_entry in dirty_batches
                    }
                    for _index, batch, manifest_entry in dirty_batches:
                        _log_scope(batch[0], manifest_entry)
                    for future in as_completed(futures):
                        batch_index, batch, manifest_entry = futures[future]
                        label, update, error = future.result()
                        if update is None:
                            skipped += len(batch)
                            print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                            continue
                        updated_shards[shard_key(batch[0])] = shard_entry_for_project(root, batch[0])
                        ordered_updates.append((batch_index, update))
                        if show_progress:
                            print(f"Indexed shard: {shard_key(batch[0])}", file=sys.stderr)
            else:
                with phase("parallel_index"):
                    for index, batch, manifest_entry in dirty_batches:
                        project = batch[0]
                        _log_scope(project, manifest_entry)
                        if show_progress:
                            print(f"Indexing shard: {shard_key(project)}", file=sys.stderr)
                        label, update, error = _index_dirty_shard(
                            root,
                            batch,
                            tmpdir_path / f"part-{index}",
                            env,
                            exclude_globs=exclude_globs,
                            manifest_entry=manifest_entry,
                            index_db=live_db,
                            delta=delta,
                        )
                        if update is None:
                            skipped += len(batch)
                            print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                            continue
                        updated_shards[shard_key(project)] = shard_entry_for_project(root, project)
                        ordered_updates.append((index, update))
                        if show_progress:
                            print(f"Indexed shard: {shard_key(project)}", file=sys.stderr)

        if dirty_batches and not ordered_updates:
            raise RuntimeError("Failed to index project")

        if ordered_updates:
            sorted_updates = [update for _, update in sorted(ordered_updates, key=lambda item: item[0])]
            part_dbs = [update.part_db for update in sorted_updates if update.part_db is not None]
            output_db.parent.mkdir(parents=True, exist_ok=True)

            if not live_db.is_file():
                if not part_dbs:
                    raise RuntimeError("Failed to index project")
                with phase("cold_merge"):
                    finalize_part_dbs(part_dbs, output_db)
                for update in sorted_updates:
                    if update.remove_paths:
                        remove_documents_by_paths(output_db, update.remove_paths)
                promote = True
                result_db = output_db
            else:
                with phase("apply_updates"):
                    apply_shard_updates(live_db, sorted_updates)
                promote = False
                result_db = live_db
        else:
            promote = False
            result_db = live_db

    save_shard_manifest(cache_dir, updated_shards, project_root=root)
    reindexed = len(ordered_updates)
    print(f"Incremental: {reused} shard(s) reused, {reindexed} reindexed", file=sys.stderr)
    flush_summary()
    return result_db, reindexed, skipped, total, promote
