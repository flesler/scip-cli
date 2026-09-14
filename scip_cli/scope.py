"""Persisted index scope for scoped reindex without editing .scip-cli.json."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .metadata import IndexMetadata, load_metadata, save_metadata


@dataclass(frozen=True)
class IndexScope:
    """Directory prefixes or explicit tsconfig*.json paths limiting the index."""

    paths: tuple[str, ...]


def load_index_scope(project_root: Path) -> IndexScope | None:
    """Load the last reindex scope for a project, if any."""
    metadata = load_metadata(project_root)
    if not metadata.scope_paths:
        return None
    return IndexScope(paths=metadata.scope_paths)


def save_index_scope(project_root: Path, paths: list[str] | None) -> None:
    """Persist or clear the index scope for a project."""
    current = load_metadata(project_root)
    save_metadata(
        project_root,
        IndexMetadata(
            scope_paths=tuple(paths) if paths else None,
            exclude_globs=current.exclude_globs,
        ),
    )


def project_in_scope(project: Path, scope_paths: tuple[str, ...]) -> bool:
    """Return True when a discovered project root lies under a scope prefix."""
    proj = project.as_posix()
    for prefix in scope_paths:
        p = prefix.rstrip("/")
        if proj == p or proj.startswith(p + "/"):
            return True
    return False


def projects_matching_scope(projects: list[Path], scope_paths: tuple[str, ...]) -> list[Path]:
    return [project for project in projects if project_in_scope(project, scope_paths)]
