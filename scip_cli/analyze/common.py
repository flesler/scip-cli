"""Shared SQL helpers and formatting for analyze checks."""

from __future__ import annotations

from ..sql import debug_execute
from ..symbols import extract_leaf_name

DEFAULT_LIMIT = 20

# Definition document for a symbol (our trimmed schema uses defn_enclosing_ranges).
SYM_DEF_JOIN = """
    JOIN defn_enclosing_ranges sym_def ON sym_def.symbol_id = gs.id
    JOIN documents def_d ON sym_def.document_id = def_d.id
"""


def fetch_all(db, sql: str, params=()) -> list:
    return debug_execute(db, sql, params).fetchall()


def fetch_one(db, sql: str, params=()):
    return debug_execute(db, sql, params).fetchone()


def short_name(symbol: str) -> str:
    leaf = extract_leaf_name(symbol)
    return leaf or symbol.split("/")[-1][:60]


def section(title: str, lines: list[str]) -> tuple[str, list[str]]:
    if not lines:
        return title, ["(none)"]
    return title, lines
