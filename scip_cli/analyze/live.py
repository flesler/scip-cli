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
        self.module_importers: dict[int, int] = {}
        self._build(db)

    def _build(self, db) -> None:
        for doc_id, importer_count in _fetch_all(
            db,
            """
            SELECT der.document_id, COUNT(DISTINCT c.document_id)
            FROM global_symbols gs
            JOIN defn_enclosing_ranges der ON der.symbol_id = gs.id
            JOIN mentions m ON m.symbol_id = gs.id AND m.role != 1
            JOIN chunks c ON m.chunk_id = c.id
            WHERE gs.symbol LIKE '%/' AND gs.symbol NOT LIKE '%().'
              AND c.document_id != der.document_id
            GROUP BY der.document_id
            """,
        ):
            self.live_module_docs.add(doc_id)
            self.module_importers[doc_id] = importer_count

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

    def possibly_live_label(self, symbol: str, def_doc_id: int) -> str | None:
        """Proof of liveness via module or export alias (used to suppress false dead-export hits)."""
        if is_module_symbol(symbol):
            if def_doc_id not in self.live_module_docs:
                return None
            count = self.module_importers.get(def_doc_id, 0)
            return f"module_import:{count}"
        base = export_value_base(symbol)
        if not base:
            return None
        if base in self.live_alias_bases:
            return "export_alias"
        if def_doc_id in self.live_module_docs:
            count = self.module_importers.get(def_doc_id, 0)
            return f"default_export:{count}"
        return None

    def dead_export_noise(self, symbol: str, def_doc_id: int) -> bool:
        """Suppress from dead_exports when live via module or export alias."""
        return self.possibly_live_label(symbol, def_doc_id) is not None or is_module_symbol(symbol)

    def same_file_export_noise(self, symbol: str, def_doc_id: int | None = None) -> bool:
        """Export used only in-file but live via module or export alias elsewhere."""
        base = export_value_base(symbol)
        if not base:
            return False
        if base in self.live_alias_bases:
            return True
        return def_doc_id is not None and def_doc_id in self.live_module_docs

    def stale_type_live_noise(self, symbol: str, def_doc_id: int) -> bool:
        """Class/type looks unused but file is live via default export or module import."""
        base = export_value_base(symbol)
        if not base:
            return False
        if base in self.live_alias_bases:
            return True
        return def_doc_id in self.live_module_docs


def has_same_file_reference_usage(db, symbol_id: int, def_doc_id: int) -> bool:
    """Type or value referenced in the same file (extends, signatures, handler registration)."""
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


def file_has_scip_importers(db, relative_path: str, *, live: LiveIndex, def_doc_id: int) -> bool:
    """True when the index shows another file importing this module or its symbols."""
    if def_doc_id in live.live_module_docs:
        return True
    from ..queries import get_file_symbols, get_importer_paths

    symbols = get_file_symbols(db, relative_path)
    if not symbols:
        return False
    symbol_ids = [row[0] for row in symbols]
    return bool(get_importer_paths(db, symbol_ids, relative_path))
