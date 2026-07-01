"""Shrink converted SQLite indexes."""

from __future__ import annotations

import os
import sqlite3


def _replace_table(conn, old_name: str, new_name: str) -> None:
    conn.execute(f"DROP TABLE {old_name}")
    conn.execute(f"ALTER TABLE {new_name} RENAME TO {old_name}")


def _trim_unused_columns(conn, keep_external=False):
    """Remove columns we never use; omit variable symbols while rebuilding global_symbols.

    Args:
        conn: SQLite connection
        keep_external: If True, keep symbols without definitions (external libs)
    """
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

    # Build the WHERE clause: exclude variables AND optionally require definitions
    where_clauses = [exclude]
    if not keep_external:
        # Keep symbols that are either:
        # 1. Defined in the project (have defn_enclosing_ranges entries)
        # 2. Structural symbols needed for type analysis (type literals, parameters)
        # 3. Functions/methods (even without defs, they may be project code)
        #
        # SCIP symbol format patterns (language-agnostic):
        # - %typeLiteral% : Type/interface fields (e.g., Options#typeLiteral0:verbose.)
        # - %).(% : Function parameters (e.g., greet().(name))
        # - %().% : Functions and methods (e.g., Widget.run()., greet().)
        where_clauses.append(
            "EXISTS (SELECT 1 FROM defn_enclosing_ranges der WHERE der.symbol_id = global_symbols.id) "
            + "OR symbol LIKE '%typeLiteral%' "
            + "OR symbol LIKE '%).(%' "
            + "OR symbol LIKE '%().%'"
        )

    where_clause = " AND ".join(where_clauses)

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
        WHERE {where_clause}
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


def postprocess_index(db_path, keep_external=None):
    """Shrink index: drop unused columns and prune external symbols by default.

    Args:
        db_path: Path to the SQLite database
        keep_external: If True, keep symbols without definitions (external libs).
                      If None, reads from SCIP_CLI_KEEP_EXTERNAL env var.
    """
    from ..sql import configure_bulk_write_connection

    # Default to False unless explicitly set via parameter or env var
    if keep_external is None:
        keep_external = os.environ.get("SCIP_CLI_KEEP_EXTERNAL", "0") == "1"

    conn = sqlite3.connect(str(db_path))
    try:
        configure_bulk_write_connection(conn)
        # Rebuild tables first; indexes are recreated once at the end (expt-convert indexes
        # are dropped with table swaps — avoid maintaining them during bulk inserts).
        _trim_unused_columns(conn, keep_external=keep_external)
        _trim_mentions_to_known_symbols(conn)
        _trim_defn_to_known_symbols(conn)
        _recreate_postprocess_indexes(conn)
        conn.commit()
    finally:
        conn.close()
