"""Heuristics for SCIP symbols that look dead but are live via module or export-alias indirection."""

from __future__ import annotations

import re

from ..sql import debug_execute
from ..symbols import extract_leaf_name, is_module_symbol

_EXTERNAL_MENTION = """
    SELECT 1 FROM mentions m
    JOIN chunks c ON m.chunk_id = c.id
    WHERE m.symbol_id = ? AND m.role != 1 AND c.document_id != ?
    LIMIT 1
"""


def _fetch_all(db, sql: str, params=()) -> list:
    return debug_execute(db, sql, params).fetchall()


def _fetch_one(db, sql: str, params=()):
    return debug_execute(db, sql, params).fetchone()


def is_export_alias_symbol(symbol: str) -> bool:
    tail = symbol.split("/")[-1]
    return tail.endswith("0:") and "()." not in tail


def export_alias_base(symbol: str) -> str | None:
    if not is_export_alias_symbol(symbol):
        return None
    tail = symbol.split("/")[-1]
    return tail[:-2]


def export_value_base(symbol: str) -> str | None:
    """Base name for a default-exported function or class/type definition."""
    if symbol.endswith("()."):
        return extract_leaf_name(symbol) or None
    if symbol.endswith("#") and "#typeLiteral" not in symbol and "()." not in symbol.split("/")[-1]:
        leaf = extract_leaf_name(symbol)
        return leaf or None
    return None


def _def_doc_id_from_symbol(db, symbol: str) -> int | None:
    match = re.search(r"`([^`]+)`", symbol)
    if not match:
        return None
    filename = match.group(1)
    row = _fetch_one(
        db,
        "SELECT id FROM documents WHERE relative_path GLOB ? OR relative_path = ? LIMIT 1",
        (f"*/{filename}", filename),
    )
    return row[0] if row else None


class LiveIndex:
    """Precomputed live-module docs and export-alias bases for one analyze pass."""

    def __init__(self, db) -> None:
        self.live_module_docs: set[int] = set()
        self.live_alias_bases: set[str] = set()
        self._build(db)

    def _build(self, db) -> None:
        for (doc_id,) in _fetch_all(
            db,
            """
            SELECT DISTINCT der.document_id
            FROM global_symbols gs
            JOIN defn_enclosing_ranges der ON der.symbol_id = gs.id
            WHERE gs.symbol LIKE '%/' AND gs.symbol NOT LIKE '%().'
              AND EXISTS (
                SELECT 1 FROM mentions m
                JOIN chunks c ON m.chunk_id = c.id
                WHERE m.symbol_id = gs.id AND m.role != 1 AND c.document_id != der.document_id
              )
            """,
        ):
            self.live_module_docs.add(doc_id)

        for sym_id, symbol in _fetch_all(
            db,
            """
            SELECT id, symbol FROM global_symbols
            WHERE symbol LIKE '%0:' AND symbol NOT LIKE '%().'
            """,
        ):
            base = export_alias_base(symbol)
            if not base:
                continue
            def_doc = _def_doc_id_from_symbol(db, symbol)
            if def_doc is None:
                continue
            if _fetch_one(db, _EXTERNAL_MENTION, (sym_id, def_doc)):
                self.live_alias_bases.add(base)

    def dead_export_noise(self, symbol: str, def_doc_id: int) -> bool:
        if is_module_symbol(symbol):
            return True
        base = export_value_base(symbol)
        if base and base in self.live_alias_bases:
            return True
        return bool(base and def_doc_id in self.live_module_docs)

    def same_file_export_noise(self, symbol: str) -> bool:
        """Export used only in-file but live via module or export alias elsewhere."""
        base = export_value_base(symbol)
        if not base:
            return False
        return base in self.live_alias_bases

    def stale_type_live_noise(self, symbol: str, def_doc_id: int) -> bool:
        """Class/type looks unused but file is live via default export or module import."""
        base = export_value_base(symbol)
        if not base:
            return False
        if base in self.live_alias_bases:
            return True
        return def_doc_id in self.live_module_docs


def has_same_file_reference_usage(db, symbol_id: int, def_doc_id: int) -> bool:
    """Type or value referenced in the same file (extends, signatures, object literal)."""
    row = _fetch_one(
        db,
        """
        SELECT 1 FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        WHERE m.symbol_id = ? AND m.role = 0 AND c.document_id = ?
        LIMIT 1
        """,
        (symbol_id, def_doc_id),
    )
    return row is not None
