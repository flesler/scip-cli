"""Merge SCIP SQLite indexes produced from separate TypeScript projects."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path


def merge_sqlite_indexes(part_paths: list[Path], output_path: Path) -> None:
    """Combine partial index databases into a single queryable database."""
    if not part_paths:
        raise ValueError("at least one input is required")

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
    dest.execute("ATTACH DATABASE ? AS src", (str(part_path),))
    try:
        dest.execute("CREATE TEMPORARY TABLE doc_map (old_id INTEGER, new_id INTEGER)")
        dest.execute("CREATE TEMPORARY TABLE symbol_map (old_id INTEGER, new_id INTEGER)")
        dest.execute("CREATE TEMPORARY TABLE chunk_map (old_id INTEGER, new_id INTEGER)")

        dest.execute("BEGIN")

        dest.execute("""
            INSERT OR IGNORE INTO documents (relative_path)
            SELECT relative_path FROM src.documents
        """)
        dest.execute("""
            INSERT INTO doc_map (old_id, new_id)
            SELECT src.id, dest.id
            FROM src.documents src
            JOIN documents dest ON dest.relative_path = src.relative_path
        """)

        dest.execute("""
            INSERT OR IGNORE INTO global_symbols (symbol, display_name, kind)
            SELECT symbol, display_name, kind
            FROM src.global_symbols
        """)
        dest.execute("""
            INSERT INTO symbol_map (old_id, new_id)
            SELECT src.id, dest.id
            FROM src.global_symbols src
            JOIN global_symbols dest ON dest.symbol = src.symbol
        """)

        dest.execute("""
            INSERT OR IGNORE INTO chunks (document_id, chunk_index, start_line, end_line, occurrences)
            SELECT dm.new_id, src.chunk_index, src.start_line, src.end_line, src.occurrences
            FROM src.chunks src
            JOIN doc_map dm ON dm.old_id = src.document_id
            WHERE NOT EXISTS (
                SELECT 1 FROM chunks
                WHERE document_id = dm.new_id
                AND chunk_index = src.chunk_index
            )
        """)
        dest.execute("""
            INSERT INTO chunk_map (old_id, new_id)
            SELECT src.id, dest.id
            FROM src.chunks src
            JOIN doc_map dm ON dm.old_id = src.document_id
            JOIN chunks dest ON dest.document_id = dm.new_id AND dest.chunk_index = src.chunk_index
        """)

        dest.execute("""
            INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role)
            SELECT cm.new_id, sm.new_id, src.role
            FROM src.mentions src
            JOIN chunk_map cm ON cm.old_id = src.chunk_id
            JOIN symbol_map sm ON sm.old_id = src.symbol_id
        """)

        dest.execute("""
            INSERT OR IGNORE INTO defn_enclosing_ranges (
                document_id, symbol_id, start_line, start_char, end_line, end_char
            )
            SELECT dm.new_id, sm.new_id, src.start_line, src.start_char, src.end_line, src.end_char
            FROM src.defn_enclosing_ranges src
            JOIN doc_map dm ON dm.old_id = src.document_id
            JOIN symbol_map sm ON sm.old_id = src.symbol_id
        """)

        dest.execute("COMMIT")

        dest.execute("DROP TABLE doc_map")
        dest.execute("DROP TABLE symbol_map")
        dest.execute("DROP TABLE chunk_map")
    finally:
        dest.execute("DETACH DATABASE src")
