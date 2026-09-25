"""Persisted index exclude globs and path matching."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from .config import load_project_config
from .metadata import IndexMetadata, load_metadata, save_metadata


def load_persisted_exclude_globs(project_root: Path) -> tuple[str, ...]:
    """Load exclude globs from persisted reindex metadata, if any."""
    metadata = load_metadata(project_root)
    return metadata.exclude_globs or ()


def save_persisted_exclude_globs(project_root: Path, globs: list[str] | None) -> None:
    """Persist or clear reindex exclude globs for a project."""
    current = load_metadata(project_root)
    save_metadata(
        project_root,
        IndexMetadata(
            scope_paths=current.scope_paths,
            exclude_globs=tuple(globs) if globs else None,
        ),
    )


def resolve_exclude_globs(project_root: Path) -> tuple[str, ...]:
    """Merge .scip-cli.json excludeGlobs with persisted reindex exclude globs."""
    settings = load_project_config(project_root)
    merged: list[str] = []
    seen: set[str] = set()
    for glob in (*settings.exclude_globs, *load_persisted_exclude_globs(project_root)):
        if glob and glob not in seen:
            seen.add(glob)
            merged.append(glob)
    return tuple(merged)


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a repo-relative glob to a regex (supports **, *, ?)."""
    normalized = pattern.replace("\\", "/").lstrip("/")
    parts: list[str] = []
    index = 0
    while index < len(normalized):
        char = normalized[index]
        if char == "*":
            if index + 1 < len(normalized) and normalized[index + 1] == "*":
                if index + 2 < len(normalized) and normalized[index + 2] == "/":
                    parts.append("(?:.+/)?")
                    index += 3
                    continue
                parts.append(".*")
                index += 2
                continue
            parts.append("[^/]*")
            index += 1
            continue
        if char == "?":
            parts.append("[^/]")
            index += 1
            continue
        if char in ".^$+{}|()[]":
            parts.append(re.escape(char))
        else:
            parts.append(char)
        index += 1
    return re.compile("^" + "".join(parts) + "$")


def path_matches_glob(relative_path: str, pattern: str) -> bool:
    """Return True when a repo-relative path matches an exclude glob.

    Patterns without '/' match the basename only (e.g. ``*.test.ts``).
    Patterns with '/' match the full posix path (``tests/**``, ``src/*.spec.ts``).
    """
    path = relative_path.replace("\\", "/").lstrip("/")
    glob = pattern.replace("\\", "/").lstrip("/")
    if not glob:
        return False
    target = PurePosixPath(path).name if "/" not in glob else path
    return bool(_glob_to_regex(glob).match(target))


def path_matches_any_glob(relative_path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    if not patterns:
        return False
    return any(path_matches_glob(relative_path, pattern) for pattern in patterns)


def filter_excluded_paths(
    paths: tuple[str, ...] | frozenset[str] | list[str],
    exclude_globs: tuple[str, ...],
) -> tuple[str, ...]:
    """Drop repo-relative paths that match persisted/config exclude globs."""
    if not exclude_globs:
        if isinstance(paths, tuple):
            return paths
        return tuple(sorted(paths))
    return tuple(sorted(path for path in paths if not path_matches_any_glob(path, exclude_globs)))
