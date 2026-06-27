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


def is_cli_entrypoint(relative_path: str, symbol: str) -> bool:
    """True for command main() entrypoints the index does not link to __main__.py."""
    if short_name(symbol) != "main":
        return False
    path = relative_path.replace("\\", "/")
    return path == "scip_cli/__main__.py" or "/commands/" in path


def analyze_noise(relative_path: str, symbol: str, *, include_tests: bool = False) -> bool:
    """True for rows that clutter analyze dashboards (test paths, module-private helpers)."""
    if not include_tests and is_test_path(relative_path):
        return True
    if short_name(symbol).startswith("_"):
        return True
    if is_cli_entrypoint(relative_path, symbol):
        return True
    return is_analyze_dashboard_export(relative_path, symbol)


_ANALYZE_DASHBOARD_SUFFIXES = (
    "analyze/project.py",
    "analyze/file.py",
    "analyze/symbol.py",
)


def is_analyze_dashboard_export(relative_path: str, symbol: str) -> bool:
    """Section runner functions in analyze/* (same-file only, look like dead exports)."""
    path = relative_path.replace("\\", "/")
    if not any(path.endswith(suffix) for suffix in _ANALYZE_DASHBOARD_SUFFIXES):
        return False
    name = short_name(symbol)
    return "()." in symbol or name.endswith(")")


def stale_type_noise(relative_path: str, symbol: str, consumers: int) -> bool:
    """Dataclass-style types with no SCIP consumers (typing-only)."""
    if consumers > 0:
        return False
    name = short_name(symbol)
    if not name or not name[0].isupper():
        return False
    path = relative_path.replace("\\", "/")
    return path.endswith(("config.py", "scope.py", "analyze/targets.py"))


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
