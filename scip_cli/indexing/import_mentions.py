"""Synthesize SCIP Import (role=2) mentions from TypeScript/JavaScript import syntax.

scip-typescript often records only Definition/Reference roles. unused_imports and
single_use_imports expect Import (role=2) bindings per the SCIP spec.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path, PurePosixPath

_TS_JS_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

_DEFAULT_IMPORT = re.compile(
    r"""^\s*import\s+(?:type\s+)?(?P<name>[\w$]+)\s+from\s+['"](?P<spec>[^'"]+)['"]\s*;?\s*$"""
)
_NAMESPACE_IMPORT = re.compile(
    r"""^\s*import\s+\*\s+as\s+(?P<name>[\w$]+)\s+from\s+['"](?P<spec>[^'"]+)['"]\s*;?\s*$"""
)
_NAMED_IMPORT = re.compile(
    r"""^\s*import\s+(?:type\s+)?\{(?P<names>[^}]+)\}\s+from\s+['"](?P<spec>[^'"]+)['"]\s*;?\s*$"""
)
_SIDE_EFFECT = re.compile(r"""^\s*import\s+['"][^'"]+['"]\s*;?\s*$""")


def _split_named_bindings(names_blob: str) -> list[str]:
    out: list[str] = []
    for part in names_blob.split(","):
        piece = part.strip()
        if not piece:
            continue
        piece = re.sub(r"^type\s+", "", piece)
        if " as " in piece:
            piece = piece.split(" as ", 1)[1].strip()
        out.append(piece)
    return out


def _posix_norm(path: str) -> str:
    parts: list[str] = []
    for segment in path.split("/"):
        if segment == "..":
            if parts:
                parts.pop()
        elif segment and segment != ".":
            parts.append(segment)
    return "/".join(parts)


def _resolve_spec(importer_path: str, spec: str, known_paths: set[str]) -> str | None:
    if not spec.startswith("."):
        return None
    raw = spec.split("?", 1)[0]
    joined = _posix_norm(f"{PurePosixPath(importer_path).parent.as_posix()}/{raw}")
    candidates: list[str] = []
    s = joined
    candidates.append(s)
    if not any(s.endswith(ext) for ext in _TS_JS_SUFFIXES):
        for ext in _TS_JS_SUFFIXES:
            candidates.append(s + ext)
        for ext in (".ts", ".tsx", ".mts"):
            candidates.append(str(PurePosixPath(s) / ("index" + ext)))
    for path in candidates:
        if path in known_paths:
            return path
        norm = path.lstrip("./")
        if norm in known_paths:
            return norm
    return None


def _chunk_for_line(conn: sqlite3.Connection, doc_id: int, line: int) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM chunks
        WHERE document_id = ? AND start_line <= ? AND end_line >= ?
        ORDER BY start_line
        LIMIT 1
        """,
        (doc_id, line, line),
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "SELECT id FROM chunks WHERE document_id = ? ORDER BY start_line LIMIT 1",
        (doc_id,),
    ).fetchone()
    return row[0] if row else None


def _symbol_ids_for_binding(
    conn: sqlite3.Connection,
    def_path: str,
    binding: str,
    *,
    namespace: bool = False,
) -> list[int]:
    file_label = PurePosixPath(def_path).name
    if namespace:
        row = conn.execute(
            """
            SELECT gs.id
            FROM global_symbols gs
            JOIN defn_enclosing_ranges der ON der.symbol_id = gs.id
            JOIN documents d ON der.document_id = d.id
            WHERE d.relative_path = ?
              AND (gs.symbol LIKE '%/' || ? || '/' OR gs.symbol LIKE '%`' || ? || '`/')
            LIMIT 1
            """,
            (def_path, file_label, file_label),
        ).fetchone()
        return [row[0]] if row else []

    rows = conn.execute(
        """
        SELECT gs.id
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON der.symbol_id = gs.id
        JOIN documents d ON der.document_id = d.id
        WHERE d.relative_path = ?
          AND (
              gs.display_name = ?
              OR gs.symbol LIKE '%/`' || ? || '`/' || ? || '().'
              OR gs.symbol LIKE '%/`' || ? || '`/' || ? || '#'
          )
        """,
        (def_path, binding, file_label, binding, file_label, binding),
    ).fetchall()
    if rows:
        return [row[0] for row in rows]
    row = conn.execute(
        """
        SELECT gs.id
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON der.symbol_id = gs.id
        JOIN documents d ON der.document_id = d.id
        WHERE d.relative_path = ? AND gs.symbol LIKE '%().'
        ORDER BY der.start_line
        LIMIT 1
        """,
        (def_path,),
    ).fetchone()
    return [row[0]] if row else []


def _parse_import_lines(source: str) -> list[tuple[int, str, str, bool]]:
    """(line_number, binding, resolved_spec, is_namespace) — spec unresolved."""
    bindings: list[tuple[int, str, str, bool]] = []
    for index, line in enumerate(source.splitlines()):
        if _SIDE_EFFECT.match(line):
            continue
        m = _NAMESPACE_IMPORT.match(line)
        if m:
            bindings.append((index, m.group("name"), m.group("spec"), True))
            continue
        m = _DEFAULT_IMPORT.match(line)
        if m:
            bindings.append((index, m.group("name"), m.group("spec"), False))
            continue
        m = _NAMED_IMPORT.match(line)
        if m:
            for name in _split_named_bindings(m.group("names")):
                bindings.append((index, name, m.group("spec"), False))
    return bindings


def synthesize_import_mentions(conn: sqlite3.Connection, project_root: Path) -> int:
    """Insert role=2 rows for local import bindings. Returns rows inserted."""
    project_root = project_root.resolve()
    doc_rows = conn.execute("SELECT id, relative_path FROM documents").fetchall()
    known_paths = {row[1] for row in doc_rows}
    inserted = 0
    for doc_id, rel_path in doc_rows:
        if not rel_path.endswith(_TS_JS_SUFFIXES):
            continue
        source_path = project_root / rel_path
        if not source_path.is_file():
            continue
        try:
            source = source_path.read_text(encoding="utf-8")
        except OSError:
            continue
        chunk_cache: dict[int, int | None] = {}
        for line_no, binding, spec, is_namespace in _parse_import_lines(source):
            def_path = _resolve_spec(rel_path, spec, known_paths)
            if not def_path:
                continue
            sym_ids = _symbol_ids_for_binding(conn, def_path, binding, namespace=is_namespace)
            if line_no not in chunk_cache:
                chunk_cache[line_no] = _chunk_for_line(conn, doc_id, line_no)
            chunk_id = chunk_cache[line_no]
            if chunk_id is None:
                continue
            for sym_id in sym_ids:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 2)",
                    (chunk_id, sym_id),
                )
                inserted += cur.rowcount
    return inserted
