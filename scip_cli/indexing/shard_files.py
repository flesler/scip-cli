"""Per-file reindex scope for incremental shard updates (git delta)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..exclude import filter_excluded_paths
from ..queries import get_file_symbols, get_importer_paths
from ..tsconfig import tsconfig_for_project
from .git_delta import GitIndexDelta, shard_dirty_paths
from .shards import tsconfig_chain_digest
from .source_discovery import list_project_source_files


@dataclass(frozen=True)
class PartialReindexPlan:
    """Scoped paths to re-index and paths to drop from the index."""

    index_paths: tuple[str, ...]
    remove_paths: frozenset[str]


def shard_relative_paths(root: Path, project: Path) -> frozenset[str]:
    """Repo-relative paths indexed for one tsconfig shard."""
    root = Path(root).resolve()
    out: set[str] = set()
    for path in list_project_source_files(root, project):
        try:
            out.add(path.relative_to(root).as_posix())
        except ValueError:
            out.add(path.as_posix())
    return frozenset(out)


def expand_reindex_paths(
    index_db: Path,
    *,
    dirty_paths: tuple[str, ...],
    shard_paths: frozenset[str],
) -> tuple[str, ...]:
    """Dirty paths plus production files that import symbols defined in them."""
    if not dirty_paths:
        return ()

    conn = sqlite3.connect(f"file:{index_db}?mode=ro", uri=True)
    try:
        expanded: set[str] = set(dirty_paths)
        for path in dirty_paths:
            symbol_ids = [int(row[0]) for row in get_file_symbols(conn, path)]
            for importer in get_importer_paths(conn, symbol_ids, path):
                if importer in shard_paths:
                    expanded.add(importer)
        return tuple(sorted(expanded))
    finally:
        conn.close()


def resolve_partial_reindex_plan(
    root: Path,
    project: Path,
    entry: dict[str, object] | None,
    index_db: Path,
    delta: GitIndexDelta,
    *,
    exclude_globs: tuple[str, ...] = (),
) -> PartialReindexPlan | None:
    """Return partial file scope from git delta; None triggers full-shard reindex."""
    if not index_db.is_file():
        return None

    tsconfig = tsconfig_for_project(root, project)
    current_digest = tsconfig_chain_digest(project, tsconfig)
    if entry is None or entry.get("tsconfig_digest") != current_digest:
        return None

    modified, removed = shard_dirty_paths(root, project, delta, exclude_globs=exclude_globs)
    if not modified and not removed:
        if exclude_globs:
            unfiltered_modified, _ = shard_dirty_paths(root, project, delta, exclude_globs=())
            if unfiltered_modified:
                return PartialReindexPlan(index_paths=(), remove_paths=frozenset())
        return None

    shard_paths = shard_relative_paths(root, project)
    index_paths: tuple[str, ...] = ()
    if modified:
        index_paths = expand_reindex_paths(
            index_db,
            dirty_paths=tuple(sorted(modified)),
            shard_paths=shard_paths,
        )
        index_paths = filter_excluded_paths(index_paths, exclude_globs)
    remove_paths = frozenset(removed)
    if not index_paths and not remove_paths:
        return PartialReindexPlan(index_paths=(), remove_paths=frozenset())
    return PartialReindexPlan(index_paths=index_paths, remove_paths=remove_paths)
