"""Path scope helpers for --path filtering."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .sql import debug_execute, escape_like


def normalize_path_scope(path_arg: str | None, project_root: Path) -> str | None:
    """Resolve --path to a repo-relative POSIX path."""
    if not path_arg:
        return None
    root = Path(project_root).resolve()
    candidate = Path(path_arg)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"--path escapes project root: {path_arg}") from exc
    text = rel.as_posix()
    return text or "."


def path_in_scope(relative_path: str, scope: str | None) -> bool:
    """Return True when relative_path is the scope path or inside a scope directory."""
    if not scope:
        return True
    if relative_path == scope:
        return True
    return relative_path.startswith(scope.rstrip("/") + "/")


def path_filter_sql(db: sqlite3.Connection, scope: str | None, doc_alias: str = "d") -> tuple[str, list[str]]:
    """Build a SQL AND-clause that restricts rows to a file or directory scope."""
    if not scope:
        return "", []

    col = f"{doc_alias}.relative_path"
    is_file = (
        debug_execute(db, "SELECT 1 FROM documents WHERE relative_path = ? LIMIT 1", (scope,)).fetchone() is not None
    )
    if is_file:
        return f" AND {col} = ?", [scope]

    escaped = escape_like(scope.rstrip("/"))
    return f" AND ({col} = ? OR {col} LIKE ? ESCAPE '\\')", [scope, f"{escaped}/%"]


def path_filter_sql_any(db: sqlite3.Connection, scope: str | None, *doc_aliases: str) -> tuple[str, list[str]]:
    """AND-clause: row matches when any document alias column falls in scope."""
    if not scope:
        return "", []

    parts: list[str] = []
    params: list[str] = []
    for alias in doc_aliases:
        clause, clause_params = path_filter_sql(db, scope, doc_alias=alias)
        if not clause:
            continue
        parts.append(clause.removeprefix(" AND ").strip())
        params.extend(clause_params)
    if not parts:
        return "", []
    if len(parts) == 1:
        return f" AND {parts[0]}", params
    return " AND (" + " OR ".join(parts) + ")", params


def list_indexed_paths_in_scope(db: sqlite3.Connection, scope: str) -> list[str]:
    """Repo-relative document paths under scope (file or directory), sorted."""
    clause, params = path_filter_sql(db, scope, doc_alias="d")
    if not clause:
        return []
    rows = debug_execute(
        db,
        f"SELECT d.relative_path FROM documents d WHERE 1=1{clause} ORDER BY d.relative_path",
        params,
    ).fetchall()
    return [row[0] for row in rows]
