"""Shrink converted SQLite indexes."""

from __future__ import annotations

import sqlite3


def _replace_table(conn, old_name: str, new_name: str) -> None:
    conn.execute(f"DROP TABLE {old_name}")
    conn.execute(f"ALTER TABLE {new_name} RENAME TO {old_name}")


def _trim_unused_columns(conn):
    """Remove columns we never use; omit variable symbols while rebuilding global_symbols."""
    conn.execute("""
        CREATE TABLE documents_new (
            id INTEGER PRIMARY KEY,
            relative_path TEXT NOT NULL UNIQUE
        )
    """)
    conn.execute("INSERT INTO documents_new (id, relative_path) SELECT id, relative_path FROM documents")
    _replace_table(conn, "documents", "documents_new")

    from ..symbols import sql_exclude_variable_symbols

    exclude = sql_exclude_variable_symbols("symbol")
    conn.execute("""
        CREATE TABLE global_symbols_new (
            id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL UNIQUE,
            display_name TEXT,
            kind INTEGER
        )
    """)
    conn.execute(f"""
        INSERT INTO global_symbols_new (id, symbol, display_name, kind)
        SELECT id, symbol, display_name, kind FROM global_symbols
        WHERE {exclude}
    """)
    _replace_table(conn, "global_symbols", "global_symbols_new")


def _trim_mentions_to_known_symbols(conn):
    """Copy mentions that reference retained symbols (drops variable refs without DELETE)."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mentions' LIMIT 1").fetchone():
        return
    conn.execute("""
        CREATE TABLE mentions_new (
            chunk_id INTEGER NOT NULL,
            symbol_id INTEGER NOT NULL,
            role INTEGER NOT NULL,
            PRIMARY KEY (chunk_id, symbol_id, role)
        )
    """)
    conn.execute("""
        INSERT INTO mentions_new (chunk_id, symbol_id, role)
        SELECT m.chunk_id, m.symbol_id, m.role
        FROM mentions m
        JOIN global_symbols g ON g.id = m.symbol_id
    """)
    _replace_table(conn, "mentions", "mentions_new")


def _trim_defn_to_known_symbols(conn):
    """Copy defn rows for retained symbols only."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='defn_enclosing_ranges' LIMIT 1"
    ).fetchone():
        return
    conn.execute("""
        CREATE TABLE defn_enclosing_ranges_new (
            id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL,
            symbol_id INTEGER NOT NULL,
            start_line INTEGER NOT NULL,
            start_char INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            end_char INTEGER NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO defn_enclosing_ranges_new (
            id, document_id, symbol_id, start_line, start_char, end_line, end_char
        )
        SELECT d.id, d.document_id, d.symbol_id, d.start_line, d.start_char, d.end_line, d.end_char
        FROM defn_enclosing_ranges d
        JOIN global_symbols g ON g.id = d.symbol_id
    """)
    _replace_table(conn, "defn_enclosing_ranges", "defn_enclosing_ranges_new")


def _recreate_postprocess_indexes(conn: sqlite3.Connection) -> None:
    """expt-convert indexes are dropped when tables are rebuilt."""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_global_symbols_symbol ON global_symbols(symbol)")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mentions' LIMIT 1").fetchone():
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mentions_symbol_id_role ON mentions(symbol_id, role)")


def _postprocess_index(db_path):
    """Shrink index: drop unused columns and omit prunable symbol rows (copy-filter, no DELETE)."""
    from ..sql import configure_bulk_write_connection

    conn = sqlite3.connect(str(db_path))
    try:
        configure_bulk_write_connection(conn)
        # Rebuild tables first; indexes are recreated once at the end (expt-convert indexes
        # are dropped with table swaps — avoid maintaining them during bulk inserts).
        _trim_unused_columns(conn)
        _trim_mentions_to_known_symbols(conn)
        _trim_defn_to_known_symbols(conn)
        _recreate_postprocess_indexes(conn)
        conn.commit()
    finally:
        conn.close()
