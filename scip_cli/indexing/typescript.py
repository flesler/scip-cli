"""TypeScript project resolution and indexing."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..cache import index_db_path
from ..config import CONFIG_FILENAME, load_project_config, resolve_index_roots
from ..discover import discover_typescript_projects
from ..scope import load_index_scope, projects_matching_scope
from ..tsconfig import allow_js_overlay, scope_tsconfig_paths, tsconfig_for_project
from .constants import PROGRESS_LOG_MIN_PROJECTS
from .convert import convert_scip_to_db
from .orchestrate import (
    batch_projects,
    effective_ts_batch_size,
    finalize_part_dbs,
    index_workers,
    project_batch_label,
    ts_batch_limit_display,
)
from .runners import run_indexer_with_fallback
from .shards import (
    SHARDS_DIRNAME,
    compute_shard_fingerprint,
    load_shard_manifest,
    resolve_cached_shard_db,
    save_shard_manifest,
    shard_db_filename,
    shard_db_path,
    shard_key,
)


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


def _typescript_index_args(root, output_scip, projects):
    args = ["index", "--output", str(output_scip)]
    root = Path(root)
    if not (root / "tsconfig.json").exists():
        args.insert(1, "--infer-tsconfig")
    args.extend(str(project) for project in projects)
    return args


def _overlay_filename(project: Path, index: int) -> str:
    stem = project.as_posix().replace("/", "__").replace("\\", "__")
    return f"allowjs-{index}-{stem}.json"


def materialize_allow_js_projects(root: Path, projects: list[Path], work_dir: Path) -> list[Path]:
    """Rewrite projects to temp tsconfigs that include JS when allowJs is set."""
    root = Path(root).resolve()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    materialized: list[Path] = []
    for index, project in enumerate(projects):
        tsconfig = tsconfig_for_project(root, project)
        if tsconfig is None:
            materialized.append(project)
            continue
        overlay = allow_js_overlay(tsconfig)
        if overlay is None:
            materialized.append(project)
            continue
        dest = work_dir / _overlay_filename(project, index)
        dest.write_text(json.dumps(overlay, indent=2) + "\n", encoding="utf-8")
        materialized.append(dest)
    return materialized


def index_ts_projects(
    root,
    projects,
    work_dir,
    env,
    *,
    output_db: Path | None = None,
    exclude_globs: tuple[str, ...] = (),
):
    """Index one or more TypeScript projects into work_dir/index.db (or output_db when set)."""
    root = Path(root)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = project_batch_label(projects)
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    index_projects = materialize_allow_js_projects(root, projects, work_dir)
    index_args = _typescript_index_args(root, part_scip, index_projects)
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
        convert_scip_to_db(part_scip, db_path, exclude_globs=exclude_globs)
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None


def _persist_shard_db(cache_dir: Path, project: Path, source_db: Path) -> Path:
    """Copy a part DB into the shard cache for incremental reuse."""
    dest = shard_db_path(cache_dir, project)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_db, dest)
    return dest


def _index_shard_batch(
    root: Path,
    cache_dir: Path,
    batch: list[Path],
    work_dir: Path,
    env,
    *,
    exclude_globs: tuple[str, ...],
    output_db: Path | None,
) -> tuple[str, Path | None, str | None]:
    label, db_path, error = index_ts_projects(
        root,
        batch,
        work_dir,
        env,
        output_db=output_db,
        exclude_globs=exclude_globs,
    )
    if db_path is None:
        return label, None, error
    if len(batch) == 1:
        _persist_shard_db(cache_dir, batch[0], db_path)
    return label, db_path, None


def index_typescript(
    root,
    cache_dir,
    projects,
    env,
    *,
    replace=False,
    exclude_globs: tuple[str, ...] = (),
    incremental: bool = False,
):
    """Index one or more TypeScript projects and write the merged index.db."""
    root = Path(root)
    cache_dir = Path(cache_dir)
    output_db = index_db_path(cache_dir, replace=replace)
    workers = index_workers()
    batch_size = 1 if incremental else effective_ts_batch_size(projects)
    batches = batch_projects(projects, batch_size)
    use_parallel = len(batches) > 1 and workers > 1
    manifest = load_shard_manifest(cache_dir) if incremental else {}
    updated_shards: dict[str, dict[str, str]] = {}
    reused = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        part_dbs: list[Path] = []
        skipped = 0
        total = len(projects)
        show_progress = total > PROGRESS_LOG_MIN_PROJECTS

        if incremental and show_progress:
            print(f"Incremental reindex: {total} project shard(s)...", file=sys.stderr)

        if show_progress and use_parallel and not incremental:
            batch_desc = ts_batch_limit_display(batch_size, total)
            print(
                f"Indexing {total} TypeScript projects ({workers} workers, {batch_desc}; merge is serial)...",
                file=sys.stderr,
            )

        def _record_shard(project: Path, fingerprint: str) -> None:
            relative = shard_db_filename(project)
            updated_shards[shard_key(project)] = {
                "fingerprint": fingerprint,
                "part_db": f"{SHARDS_DIRNAME}/{relative}",
            }

        def _try_reuse_shard(project: Path) -> Path | None:
            nonlocal reused
            fingerprint = compute_shard_fingerprint(root, project, exclude_globs=exclude_globs)
            cached = resolve_cached_shard_db(cache_dir, project, fingerprint, manifest)
            if cached is None:
                return None
            reused += 1
            _record_shard(project, fingerprint)
            if show_progress:
                print(f"Reused shard: {shard_key(project)}", file=sys.stderr)
            return cached

        if incremental:
            ordered_parts: list[tuple[int, Path]] = []
            pending: list[tuple[int, list[Path]]] = []
            for index, batch in enumerate(batches, start=1):
                project = batch[0]
                cached = _try_reuse_shard(project)
                if cached is not None:
                    ordered_parts.append((index, cached))
                    continue
                pending.append((index, batch))

            if pending:
                if use_parallel and len(pending) > 1:
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        futures = {
                            pool.submit(
                                _index_shard_batch,
                                root,
                                cache_dir,
                                batch,
                                tmpdir_path / f"part-{index}",
                                env,
                                exclude_globs=exclude_globs,
                                output_db=None,
                            ): (index, batch)
                            for index, batch in pending
                        }
                        for future in as_completed(futures):
                            batch_index, batch = futures[future]
                            label, db_path, error = future.result()
                            if db_path is None:
                                skipped += len(batch)
                                print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                            else:
                                project = batch[0]
                                fingerprint = compute_shard_fingerprint(root, project, exclude_globs=exclude_globs)
                                _record_shard(project, fingerprint)
                                ordered_parts.append((batch_index, db_path))
                                if show_progress:
                                    print(f"Indexed shard: {shard_key(project)}", file=sys.stderr)
                else:
                    for index, batch in pending:
                        project = batch[0]
                        if show_progress:
                            print(f"Indexing shard: {shard_key(project)}", file=sys.stderr)
                        label, db_path, error = _index_shard_batch(
                            root,
                            cache_dir,
                            batch,
                            tmpdir_path / f"part-{index}",
                            env,
                            exclude_globs=exclude_globs,
                            output_db=None,
                        )
                        if db_path is None:
                            skipped += len(batch)
                            print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                            continue
                        fingerprint = compute_shard_fingerprint(root, project, exclude_globs=exclude_globs)
                        _record_shard(project, fingerprint)
                        ordered_parts.append((index, db_path))

            part_dbs = [db for _, db in sorted(ordered_parts, key=lambda item: item[0])]
        elif use_parallel:
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

        finalize_part_dbs(part_dbs, output_db)

        if incremental:
            save_shard_manifest(cache_dir, updated_shards)
            if show_progress or reused:
                print(
                    f"Incremental: {reused} shard(s) reused, {len(updated_shards) - reused} reindexed",
                    file=sys.stderr,
                )

        return output_db, len(part_dbs), skipped, total
