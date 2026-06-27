"""Persisted index scope for scoped reindex without editing .scip-cli.json."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

SCOPE_FILENAME = "index-scope.json"
ROOT_HASH_LEN = 12


@dataclass(frozen=True)
class IndexScope:
    """Directory prefixes limiting which tsconfig projects are indexed."""

    paths: tuple[str, ...]


def project_root_hash(project_root: Path) -> str:
    return hashlib.sha256(str(Path(project_root).resolve()).encode()).hexdigest()[:ROOT_HASH_LEN]


def _scope_path(project_root: Path) -> Path:
    from .cache import get_cache_dir

    return get_cache_dir(project_root) / SCOPE_FILENAME


def load_index_scope(project_root: Path) -> IndexScope | None:
    """Load the last reindex scope for a project, if any."""
    path = _scope_path(project_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    raw_paths = data.get("paths")
    if not raw_paths:
        return None
    if not isinstance(raw_paths, list) or not all(isinstance(p, str) for p in raw_paths):
        return None
    return IndexScope(paths=tuple(raw_paths))


def save_index_scope(project_root: Path, paths: list[str] | None) -> None:
    """Persist or clear the index scope for a project."""
    path = _scope_path(project_root)
    if not paths:
        if path.is_file():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"paths": paths}, indent=2) + "\n",
        encoding="utf-8",
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
