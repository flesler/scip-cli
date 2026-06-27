"""Merge SCIP SQLite indexes produced from separate TypeScript projects."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path


def merge_sqlite_indexes(part_paths: list[Path], output_path: Path) -> None:
    """Combine partial index databases into a single queryable database."""
    if not part_paths:
        raise ValueError("No partial indexes to merge")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    shutil.copyfile(part_paths[0], output_path)
    dest = sqlite3.connect(output_path)
    try:
        for part_path in part_paths[1:]:
            _merge_one_database(dest, Path(part_path))
        dest.commit()
    finally:
        dest.close()


def _merge_one_database(dest: sqlite3.Connection, part_path: Path) -> None:
    part = sqlite3.connect(part_path)
    part.row_factory = sqlite3.Row
    try:
        document_map = _merge_documents(dest, part)
        symbol_map = _merge_symbols(dest, part)
        chunk_map = _merge_chunks(dest, part, document_map)
        _merge_mentions(dest, part, chunk_map, symbol_map)
        _merge_definitions(dest, part, document_map, symbol_map)
    finally:
        part.close()


def _merge_documents(dest: sqlite3.Connection, part: sqlite3.Connection) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for row in part.execute("SELECT * FROM documents"):
        existing = dest.execute(
            "SELECT id FROM documents WHERE relative_path = ?",
            (row["relative_path"],),
        ).fetchone()
        if existing:
            mapping[row["id"]] = existing[0]
            continue
        cursor = dest.execute(
            """
            INSERT INTO documents (language, relative_path, position_encoding, text)
            VALUES (?, ?, ?, ?)
            """,
            (row["language"], row["relative_path"], row["position_encoding"], row["text"]),
        )
        mapping[row["id"]] = cursor.lastrowid
    return mapping


def _merge_symbols(dest: sqlite3.Connection, part: sqlite3.Connection) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for row in part.execute("SELECT * FROM global_symbols"):
        existing = dest.execute(
            "SELECT id FROM global_symbols WHERE symbol = ?",
            (row["symbol"],),
        ).fetchone()
        if existing:
            mapping[row["id"]] = existing[0]
            continue
        cursor = dest.execute(
            """
            INSERT INTO global_symbols (
                symbol, display_name, kind, documentation, signature,
                enclosing_symbol, relationships
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["symbol"],
                row["display_name"],
                row["kind"],
                row["documentation"],
                row["signature"],
                row["enclosing_symbol"],
                row["relationships"],
            ),
        )
        mapping[row["id"]] = cursor.lastrowid
    return mapping


def _merge_chunks(
    dest: sqlite3.Connection,
    part: sqlite3.Connection,
    document_map: dict[int, int],
) -> dict[int, int]:
    mapping: dict[int, int] = {}
    existing: dict[tuple[int, int], int] = {
        (row[0], row[1]): row[2]
        for row in dest.execute("SELECT document_id, chunk_index, id FROM chunks")
    }
    for row in part.execute("SELECT * FROM chunks"):
        document_id = document_map.get(row["document_id"])
        if document_id is None:
            continue
        key = (document_id, row["chunk_index"])
        if key in existing:
            mapping[row["id"]] = existing[key]
            continue
        cursor = dest.execute(
            """
            INSERT INTO chunks (document_id, chunk_index, start_line, end_line, occurrences)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                document_id,
                row["chunk_index"],
                row["start_line"],
                row["end_line"],
                row["occurrences"],
            ),
        )
        mapping[row["id"]] = cursor.lastrowid
        existing[key] = cursor.lastrowid
    return mapping


def _merge_mentions(
    dest: sqlite3.Connection,
    part: sqlite3.Connection,
    chunk_map: dict[int, int],
    symbol_map: dict[int, int],
) -> None:
    for row in part.execute("SELECT * FROM mentions"):
        chunk_id = chunk_map.get(row["chunk_id"])
        symbol_id = symbol_map.get(row["symbol_id"])
        if chunk_id is None or symbol_id is None:
            continue
        dest.execute(
            """
            INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role)
            VALUES (?, ?, ?)
            """,
            (chunk_id, symbol_id, row["role"]),
        )


def _merge_definitions(
    dest: sqlite3.Connection,
    part: sqlite3.Connection,
    document_map: dict[int, int],
    symbol_map: dict[int, int],
) -> None:
    for row in part.execute("SELECT * FROM defn_enclosing_ranges"):
        document_id = document_map.get(row["document_id"])
        symbol_id = symbol_map.get(row["symbol_id"])
        if document_id is None or symbol_id is None:
            continue
        dest.execute(
            """
            INSERT INTO defn_enclosing_ranges (
                document_id, symbol_id, start_line, start_char, end_line, end_char
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                symbol_id,
                row["start_line"],
                row["start_char"],
                row["end_line"],
                row["end_char"],
            ),
        )
