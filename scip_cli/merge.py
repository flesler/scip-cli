"""Merge SCIP SQLite indexes produced from separate TypeScript projects."""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from .sql import configure_bulk_write_connection
from .symbols import sql_exclude_variable_symbols

# SQLite allows SQLITE_MAX_ATTACHED (10) including the primary DB.
MAX_MERGE_BATCH_SIZE = 9
DEFAULT_MERGE_BATCH_SIZE = MAX_MERGE_BATCH_SIZE


def merge_batch_size() -> int:
    env_val = os.environ.get("SCIP_CLI_MERGE_BATCH_SIZE")
    if env_val is not None:
        try:
            parsed = int(env_val)
        except ValueError:
            raise RuntimeError(f"Invalid SCIP_CLI_MERGE_BATCH_SIZE: expected an integer, got {env_val!r}") from None
        if parsed < 1:
            raise RuntimeError(f"Invalid SCIP_CLI_MERGE_BATCH_SIZE: expected a positive integer, got {parsed}")
        if parsed > MAX_MERGE_BATCH_SIZE:
            raise RuntimeError(
                f"SCIP_CLI_MERGE_BATCH_SIZE={parsed} exceeds SQLite limit ({MAX_MERGE_BATCH_SIZE} attached "
                "source DBs per merge batch). Lower the value or raise scip-typescript batch size so fewer "
                "part DBs need merging."
            )
        return parsed
    return DEFAULT_MERGE_BATCH_SIZE


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
        configure_bulk_write_connection(dest)
        batch_size = merge_batch_size()
        remaining = [Path(p) for p in part_paths[1:]]
        while remaining:
            batch = remaining[:batch_size]
            remaining = remaining[batch_size:]
            _merge_attached_sources(dest, batch)
        dest.commit()
    finally:
        dest.close()


def _merge_attached_sources(dest: sqlite3.Connection, part_paths: list[Path]) -> None:
    """Merge multiple attached part DBs in one ATTACH cycle."""
    aliases: list[str] = []
    for index, part_path in enumerate(part_paths):
        alias = f"src{index}"
        dest.execute(f"ATTACH DATABASE ? AS {alias}", (str(part_path),))
        aliases.append(alias)
    try:
        for alias in aliases:
            _merge_one_attached(dest, alias)
    finally:
        for alias in aliases:
            dest.execute(f"DETACH DATABASE {alias}")


def _create_merge_maps(dest: sqlite3.Connection) -> None:
    dest.executescript("""
        CREATE TEMPORARY TABLE doc_map (old_id INTEGER NOT NULL, new_id INTEGER NOT NULL);
        CREATE TEMPORARY TABLE symbol_map (old_id INTEGER NOT NULL, new_id INTEGER NOT NULL);
        CREATE TEMPORARY TABLE chunk_map (old_id INTEGER NOT NULL, new_id INTEGER NOT NULL);
        CREATE INDEX doc_map_old_id ON doc_map(old_id);
        CREATE INDEX symbol_map_old_id ON symbol_map(old_id);
        CREATE INDEX chunk_map_old_id ON chunk_map(old_id);
    """)


def _drop_merge_maps(dest: sqlite3.Connection) -> None:
    dest.executescript("""
        DROP TABLE IF EXISTS doc_map;
        DROP TABLE IF EXISTS symbol_map;
        DROP TABLE IF EXISTS chunk_map;
    """)


def _merge_one_attached(dest: sqlite3.Connection, alias: str) -> None:
    src = alias
    _create_merge_maps(dest)

    dest.execute("BEGIN")
    try:
        dest.execute(f"""
            INSERT OR IGNORE INTO documents (relative_path)
            SELECT relative_path FROM {src}.documents
        """)
        dest.execute(f"""
            INSERT INTO doc_map (old_id, new_id)
            SELECT src.id, main_doc.id
            FROM {src}.documents src
            JOIN documents main_doc ON main_doc.relative_path = src.relative_path
        """)

        exclude = sql_exclude_variable_symbols("symbol")
        dest.execute(f"""
            INSERT OR IGNORE INTO global_symbols (symbol, display_name, kind)
            SELECT symbol, display_name, kind
            FROM {src}.global_symbols
            WHERE {exclude}
        """)
        dest.execute(f"""
            INSERT INTO symbol_map (old_id, new_id)
            SELECT src.id, main_sym.id
            FROM {src}.global_symbols src
            JOIN global_symbols main_sym ON main_sym.symbol = src.symbol
        """)

        dest.execute(f"""
            INSERT OR IGNORE INTO chunks (document_id, chunk_index, start_line, end_line, occurrences)
            SELECT dm.new_id, src.chunk_index, src.start_line, src.end_line, src.occurrences
            FROM {src}.chunks src
            JOIN doc_map dm ON dm.old_id = src.document_id
            LEFT JOIN chunks existing
                ON existing.document_id = dm.new_id AND existing.chunk_index = src.chunk_index
            WHERE existing.id IS NULL
        """)
        dest.execute(f"""
            INSERT INTO chunk_map (old_id, new_id)
            SELECT src.id, main_chunk.id
            FROM {src}.chunks src
            JOIN doc_map dm ON dm.old_id = src.document_id
            JOIN chunks main_chunk
                ON main_chunk.document_id = dm.new_id AND main_chunk.chunk_index = src.chunk_index
        """)

        dest.execute(f"""
            INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role)
            SELECT cm.new_id, sm.new_id, src.role
            FROM {src}.mentions src
            JOIN chunk_map cm ON cm.old_id = src.chunk_id
            JOIN symbol_map sm ON sm.old_id = src.symbol_id
        """)

        dest.execute(f"""
            INSERT OR IGNORE INTO defn_enclosing_ranges (
                document_id, symbol_id, start_line, start_char, end_line, end_char
            )
            SELECT dm.new_id, sm.new_id, src.start_line, src.start_char, src.end_line, src.end_char
            FROM {src}.defn_enclosing_ranges src
            JOIN doc_map dm ON dm.old_id = src.document_id
            JOIN symbol_map sm ON sm.old_id = src.symbol_id
        """)

        dest.execute("COMMIT")
    except Exception:
        dest.execute("ROLLBACK")
        raise
    finally:
        _drop_merge_maps(dest)
