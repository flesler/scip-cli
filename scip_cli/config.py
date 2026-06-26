"""Project configuration for scip-cli."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = ".scip-cli.json"


@dataclass
class ProjectSettings:
    """Per-repository settings loaded from .scip-cli.json."""

    max_heap_mb: int | None = None
    index_roots: list[str] = field(default_factory=list)
    only_index_roots: bool = False


def load_project_config(project_root: Path) -> ProjectSettings:
    """Load .scip-cli.json from the project root, if present."""
    path = Path(project_root) / CONFIG_FILENAME
    if not path.is_file():
        return ProjectSettings()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid {CONFIG_FILENAME}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid {CONFIG_FILENAME}: expected a JSON object")

    max_heap_mb = data.get("maxHeapMb")
    if max_heap_mb is not None:
        if type(max_heap_mb) is not int or max_heap_mb <= 0:
            raise RuntimeError(f"Invalid {CONFIG_FILENAME}: maxHeapMb must be a positive integer")

    index_roots = data.get("indexRoots", [])
    if not isinstance(index_roots, list) or not all(isinstance(p, str) for p in index_roots):
        raise RuntimeError(f"Invalid {CONFIG_FILENAME}: indexRoots must be a string array")

    only_index_roots = data.get("onlyIndexRoots", False)
    if type(only_index_roots) is not bool:
        raise RuntimeError(f"Invalid {CONFIG_FILENAME}: onlyIndexRoots must be a boolean")

    return ProjectSettings(
        max_heap_mb=max_heap_mb,
        index_roots=index_roots,
        only_index_roots=only_index_roots,
    )


def resolve_index_roots(project_root: Path, settings: ProjectSettings) -> list[Path]:
    """Validate configured index roots relative to the project root."""
    roots: list[Path] = []
    base = Path(project_root).resolve()
    for entry in settings.index_roots:
        candidate = (base / entry).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as exc:
            raise RuntimeError(f"indexRoots entry escapes project root: {entry}") from exc
        if not candidate.is_dir():
            raise RuntimeError(f"indexRoots path does not exist: {entry}")
        roots.append(candidate.relative_to(base))
    return roots
