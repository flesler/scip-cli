"""Persisted index scope for scoped reindex without editing .scip-cli.json."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .metadata import IndexMetadata, load_metadata, save_metadata
from .tsconfig import resolve_tsconfig_for_path_scope, resolved_include_or_files


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


def _pattern_covers_scope_dir(pattern: str, rel_dir: str) -> bool:
    """Whether an include/files pattern covers sources under rel_dir (relative to tsconfig dir)."""
    if not rel_dir or rel_dir == ".":
        return True
    norm = pattern.replace("\\", "/").lstrip("./")
    if norm == rel_dir or norm.startswith(f"{rel_dir}/"):
        return True
    head = norm.split("/")[0]
    return head == rel_dir or head == "**"


def tsconfig_covers_scope_prefix(
    tsconfig_path: Path,
    project_dir: Path,
    repo_root: Path,
    scope_prefix: str,
) -> bool:
    """True when a tsconfig includes files under scope_prefix (repo-relative)."""
    prefix = scope_prefix.rstrip("/")
    if not prefix:
        return False
    scope_path = (repo_root / prefix).resolve()
    project_resolved = project_dir.resolve()
    try:
        rel_scope = scope_path.relative_to(project_resolved).as_posix()
    except ValueError:
        return False

    include, files = resolved_include_or_files(tsconfig_path)
    patterns = list(include or []) + list(files or [])
    if not patterns:
        return True

    return any(_pattern_covers_scope_dir(pattern, rel_scope) for pattern in patterns)


def project_covers_scope_prefix(repo_root: Path, project: Path, scope_prefix: str) -> bool:
    """True when a discovered project indexes sources under a directory scope prefix."""
    project_dir = repo_root if project == Path(".") else (repo_root / project)
    if not project_dir.is_dir():
        return False
    display = project.as_posix() if project != Path(".") else "."
    tsconfig = resolve_tsconfig_for_path_scope(project_dir, display_path=display)
    if tsconfig is None:
        return False
    return tsconfig_covers_scope_prefix(tsconfig, project_dir, repo_root, scope_prefix)


def project_matches_scope(repo_root: Path, project: Path, scope_paths: tuple[str, ...]) -> bool:
    if project_in_scope(project, scope_paths):
        return True
    return any(project_covers_scope_prefix(repo_root, project, prefix) for prefix in scope_paths)


def projects_matching_scope(
    projects: list[Path],
    scope_paths: tuple[str, ...],
    *,
    repo_root: Path | None = None,
) -> list[Path]:
    if repo_root is None:
        return [project for project in projects if project_in_scope(project, scope_paths)]
    return [project for project in projects if project_matches_scope(repo_root, project, scope_paths)]
