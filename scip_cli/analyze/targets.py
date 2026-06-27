"""Resolve analyze CLI targets to project, directory, file, or symbol."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..paths import list_indexed_paths_in_scope, path_in_scope
from ..queries import resolve_file
from ..sql import debug_execute, escape_like

AnalyzeKind = Literal["dir", "file", "symbol"]
MAX_DIR_FILES = 30


@dataclass(frozen=True)
class AnalyzeTarget:
    kind: AnalyzeKind
    scope: str | None = None
    symbol_name: str | None = None


def _filesystem_dir_scope(target: str, project_root: Path) -> str | None:
    root = project_root.resolve()
    for raw in (target, target.rstrip("/\\")):
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_dir():
            return resolved.relative_to(root).as_posix()
    return None


def _indexed_dir_scope(db, target: str) -> str | None:
    norm = target.replace("\\", "/").strip().rstrip("/")
    if not norm:
        return None
    if debug_execute(
        db,
        "SELECT 1 FROM documents WHERE relative_path = ? LIMIT 1",
        (norm,),
    ).fetchone():
        return None
    escaped = escape_like(norm)
    rows = debug_execute(
        db,
        """
        SELECT relative_path FROM documents
        WHERE relative_path LIKE ? ESCAPE '\\'
        ORDER BY relative_path
        LIMIT 1
        """,
        (f"{escaped}/%",),
    ).fetchall()
    if rows:
        return norm
    return None


def resolve_analyze_target(db, target: str, project_root: Path, path_scope: str | None) -> AnalyzeTarget:
    """Classify target: directory, single file, or symbol name."""
    stripped = target.strip()
    if not stripped:
        raise RuntimeError("analyze target cannot be empty")

    dir_scope = _filesystem_dir_scope(stripped, project_root)
    if dir_scope is None:
        dir_scope = _indexed_dir_scope(db, stripped)
    if dir_scope is not None:
        if path_scope and not path_in_scope(dir_scope, path_scope):
            raise RuntimeError(f"target {target!r} is outside --path {path_scope!r}")
        return AnalyzeTarget("dir", scope=dir_scope)

    files = resolve_file(db, stripped, path_scope=path_scope)
    if len(files) > 1:
        lines = "\n  ".join(files[:10])
        extra = f"\n  ... and {len(files) - 10} more" if len(files) > 10 else ""
        raise RuntimeError(f"ambiguous file {target!r}:\n  {lines}{extra}")
    if len(files) == 1:
        return AnalyzeTarget("file", scope=files[0])

    return AnalyzeTarget("symbol", symbol_name=stripped)


def list_dir_files(db, scope: str, *, include_tests: bool = False) -> list[str]:
    """Indexed files under a directory scope, optionally skipping test paths."""
    from .common import is_test_path

    paths = list_indexed_paths_in_scope(db, scope)
    if not include_tests:
        paths = [path for path in paths if not is_test_path(path)]
    return [path for path in paths if path != scope.rstrip("/")]
