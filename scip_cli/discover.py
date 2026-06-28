"""Discover TypeScript project roots in a repository."""

from __future__ import annotations

import json
import os
from pathlib import Path

_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        "coverage",
        ".cache",
        "vendor",
        ".turbo",
        ".nx",
        "tmp",
    }
)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _tsconfig_project_root(path: Path) -> bool:
    """Return True when a tsconfig likely describes an indexable project."""
    data = _read_json(path)
    if not data:
        return False
    name = path.name
    if (
        name.startswith("tsconfig.")
        and name not in {"tsconfig.json"}
        and "include" not in data
        and "files" not in data
        and "references" not in data
    ):
        return False
    return "include" in data or "files" in data or "references" in data or name == "tsconfig.json"


def _tsconfig_covers_subdirectories(tsconfig_path: Path) -> bool:
    data = _read_json(tsconfig_path)
    if not data:
        return False
    include = data.get("include")
    if not isinstance(include, list) or not include:
        return False
    return any(isinstance(pattern, str) and ("**" in pattern or "/" in pattern) for pattern in include)


def _walk_tsconfig_projects(root: Path) -> list[Path]:
    """Find indexable TypeScript project directories under the repository root."""
    root = root.resolve()
    projects: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIR_NAMES and not name.startswith(".")]
        for name in sorted(filenames):
            if not name.startswith("tsconfig") or not name.endswith(".json"):
                continue
            tsconfig = Path(dirpath) / name
            if not _tsconfig_project_root(tsconfig):
                continue
            project_dir = tsconfig.parent.resolve()
            try:
                project_dir.relative_to(root)
            except ValueError:
                continue
            projects.append(project_dir)

    return projects


def _dedupe_nested(projects: list[Path]) -> list[Path]:
    """Drop ancestor projects when a more specific descendant is also indexed."""
    if len(projects) <= 1:
        return projects
    resolved = sorted({p.resolve() for p in projects})
    kept: list[Path] = []
    for candidate in resolved:
        if any(other != candidate and candidate in other.parents for other in resolved):
            continue
        kept.append(candidate)
    return kept


def discover_typescript_projects(root: Path) -> list[Path]:
    """Return TypeScript project directories to pass to scip-typescript.

    Walks the repository for tsconfig*.json files, keeps indexable project roots,
    and drops nested ancestors when a more specific project is also present.
    """
    root = root.resolve()
    discovered = _dedupe_nested(_walk_tsconfig_projects(root))

    if discovered:
        relative = sorted({p.relative_to(root) for p in discovered}, key=str)
        if should_index_root_alongside_projects(root, relative) and Path(".") not in relative:
            relative = [Path("."), *relative]
        return relative

    return [Path(".")]


def should_index_root_alongside_projects(root: Path, projects: list[Path]) -> bool:
    """Whether the repository root should be indexed in addition to discovered projects."""
    if not projects or projects == [Path(".")]:
        return False
    root_tsconfig = root / "tsconfig.json"
    if not root_tsconfig.is_file():
        return False
    return _tsconfig_covers_subdirectories(root_tsconfig)
