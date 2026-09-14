"""Persisted index exclude globs and path matching."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from .config import load_project_config

EXCLUDE_FILENAME = "index-exclude.json"


def _exclude_path(project_root: Path) -> Path:
    from .cache import get_cache_dir

    return get_cache_dir(project_root) / EXCLUDE_FILENAME


def load_persisted_exclude_globs(project_root: Path) -> tuple[str, ...]:
    """Load exclude globs from the last scoped reindex --exclude, if any."""
    path = _exclude_path(project_root)
    if not path.is_file():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(data, dict):
        return ()
    raw = data.get("globs")
    if not raw or not isinstance(raw, list) or not all(isinstance(g, str) for g in raw):
        return ()
    return tuple(raw)


def save_persisted_exclude_globs(project_root: Path, globs: list[str] | None) -> None:
    """Persist or clear reindex --exclude globs for a project."""
    path = _exclude_path(project_root)
    if not globs:
        if path.is_file():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"globs": globs}, indent=2) + "\n", encoding="utf-8")


def resolve_exclude_globs(project_root: Path) -> tuple[str, ...]:
    """Merge .scip-cli.json excludeGlobs with persisted reindex --exclude globs."""
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
