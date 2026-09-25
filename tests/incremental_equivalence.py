"""Semantic comparison of index DBs (ignores SQLite row ids)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from scip_cli.sql import configure_read_connection

_MENTIONS_SQL = """
SELECT d.relative_path, g.symbol, m.role
FROM mentions m
JOIN chunks c ON c.id = m.chunk_id
JOIN documents d ON d.id = c.document_id
JOIN global_symbols g ON g.id = m.symbol_id
ORDER BY d.relative_path, g.symbol, m.role
"""

_DEFNS_SQL = """
SELECT d.relative_path, g.symbol, der.start_line, der.end_line
FROM defn_enclosing_ranges der
JOIN documents d ON d.id = der.document_id
JOIN global_symbols g ON g.id = der.symbol_id
ORDER BY d.relative_path, g.symbol, der.start_line, der.end_line
"""


def semantic_fingerprint(db_path: Path) -> dict[str, tuple]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    configure_read_connection(conn)
    fp = {
        "documents": tuple(
            row[0] for row in conn.execute("SELECT relative_path FROM documents ORDER BY relative_path")
        ),
        "symbols": tuple(conn.execute("SELECT symbol, display_name, kind FROM global_symbols ORDER BY symbol")),
        "mentions": tuple(conn.execute(_MENTIONS_SQL)),
        "defns": tuple(conn.execute(_DEFNS_SQL)),
    }
    conn.close()
    return fp


def assert_index_equivalent(left: Path, right: Path, *, label: str = "") -> None:
    left_fp = semantic_fingerprint(left)
    right_fp = semantic_fingerprint(right)
    prefix = f"{label}: " if label else ""
    for key in left_fp:
        if left_fp[key] != right_fp[key]:
            left_only = set(left_fp[key]) - set(right_fp[key])
            right_only = set(right_fp[key]) - set(left_fp[key])
            raise AssertionError(
                f"{prefix}index mismatch in {key}: "
                f"left={len(left_fp[key])} right={len(right_fp[key])} "
                f"left_only_sample={sorted(left_only)[:3]} right_only_sample={sorted(right_only)[:3]}"
            )
