"""Unified reindex metadata persisted next to index.db."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

METADATA_FILENAME = "metadata.json"


class _UnsetType:
    pass


UNSET = _UnsetType()


@dataclass(frozen=True)
class IndexMetadata:
    """Persisted defaults for scoped reindex and exclude globs."""

    scope_paths: tuple[str, ...] | None = None
    exclude_globs: tuple[str, ...] | None = None
    unversioned: bool = False


def metadata_path(project_root: Path) -> Path:
    from .cache import get_cache_dir

    return get_cache_dir(project_root) / METADATA_FILENAME


def load_metadata(project_root: Path) -> IndexMetadata:
    path = metadata_path(project_root)
    if not path.is_file():
        return IndexMetadata()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return IndexMetadata()
    if not isinstance(data, dict):
        return IndexMetadata()

    scope_paths = _read_string_list(data.get("scope"), "paths")
    exclude_globs = _read_string_list(data.get("exclude"), "globs")
    unversioned = data.get("unversioned") is True
    return IndexMetadata(scope_paths=scope_paths, exclude_globs=exclude_globs, unversioned=unversioned)


def save_metadata(project_root: Path, metadata: IndexMetadata) -> None:
    path = metadata_path(project_root)
    if not metadata.scope_paths and not metadata.exclude_globs and not metadata.unversioned:
        if path.is_file():
            path.unlink()
        return

    payload: dict[str, object] = {}
    if metadata.scope_paths:
        payload["scope"] = {"paths": list(metadata.scope_paths)}
    if metadata.exclude_globs:
        payload["exclude"] = {"globs": list(metadata.exclude_globs)}
    if metadata.unversioned:
        payload["unversioned"] = True

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_string_list(section: object, key: str) -> tuple[str, ...] | None:
    if not isinstance(section, dict):
        return None
    raw = section.get(key)
    if not raw or not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return None
    return tuple(raw)


def index_unversioned(project_root: Path) -> bool:
    """True when reindex should use on-disk glob discovery instead of git anchoring."""
    return load_metadata(project_root).unversioned


def apply_metadata_updates(
    project_root: Path,
    *,
    fresh: bool = False,
    scope_paths: list[str] | _UnsetType | None = UNSET,
    exclude_globs: list[str] | _UnsetType | None = UNSET,
    unversioned: bool | _UnsetType = UNSET,
) -> IndexMetadata:
    """Apply reindex metadata rules and persist when flags request a change."""
    if fresh:
        scope: tuple[str, ...] | None = None
        exclude: tuple[str, ...] | None = None
        is_unversioned = False
    else:
        current = load_metadata(project_root)
        scope = current.scope_paths
        exclude = current.exclude_globs
        is_unversioned = current.unversioned

    changed = fresh
    if scope_paths is not UNSET:
        changed = True
        paths = cast(list[str] | None, scope_paths)
        scope = tuple(paths) if paths else None
    if exclude_globs is not UNSET:
        changed = True
        globs = cast(list[str] | None, exclude_globs)
        exclude = tuple(globs) if globs else None
    if unversioned is not UNSET:
        changed = True
        is_unversioned = cast(bool, unversioned)

    result = IndexMetadata(scope_paths=scope, exclude_globs=exclude, unversioned=is_unversioned)
    if changed:
        save_metadata(project_root, result)
    return result
