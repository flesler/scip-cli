"""Shared SQL helpers and formatting for analyze checks."""

from __future__ import annotations

import re

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


def is_test_path(relative_path: str) -> bool:
    """True for common test layout paths and *.test.* / *.spec.* filenames."""
    p = relative_path.replace("\\", "/")
    lower = p.lower()
    if lower.startswith(("tests/", "test/")):
        return True
    if "/tests/" in lower or "/test/" in lower or "/__tests__/" in lower:
        return True
    name = lower.rsplit("/", 1)[-1]
    if ".test." in name or ".spec." in name:
        return True
    if name.startswith("test_") and name.endswith(".py"):
        return True
    return name == "conftest.py"


def analyze_noise(relative_path: str, symbol: str, *, include_tests: bool = False) -> bool:
    """True for rows that clutter analyze dashboards (test paths, module-private helpers)."""
    if not include_tests and is_test_path(relative_path):
        return True
    return short_name(symbol).startswith("_")


def file_pair_noise(file1: str, file2: str, *, include_tests: bool = False) -> bool:
    if include_tests:
        return False
    return is_test_path(file1) or is_test_path(file2)


def cycle_path_noise(cycle_line: str, *, include_tests: bool = False) -> bool:
    if include_tests:
        return False
    parts = re.split(r"\s<->\s|\s->\s", cycle_line)
    return any(is_test_path(part.strip()) for part in parts if part.strip())


def section(title: str, lines: list[str]) -> tuple[str, list[str]]:
    if not lines:
        return title, ["(none)"]
    return title, lines
