"""Shared SQL helpers and formatting for analyze checks."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from ..sql import debug_execute
from ..symbols import extract_leaf_name, is_module_symbol

DEFAULT_LIMIT = 20
# Cap rows scanned when post-filtering SQL (filters drop many SCIP false hits).
ANALYZE_MAX_SCAN_ROWS = 10_000


def collect_until_limit(
    limit: int,
    fetch_page: Callable[[int, int], list[object]],
    accept: Callable[[object], str | None],
    *,
    page_size: int | None = None,
    max_scan: int = ANALYZE_MAX_SCAN_ROWS,
) -> list[str]:
    """Fetch SQL pages until `limit` rows pass `accept`, or data is exhausted.

    Use only when a check post-filters SQL rows (analyze_noise, live heuristics, …).
    Checks that format every SQL row as-is should use a single ``LIMIT ?`` instead.
    """
    batch = page_size or max(limit, 50)
    lines: list[str] = []
    offset = 0
    scanned = 0
    while len(lines) < limit:
        rows = fetch_page(batch, offset)
        if not rows:
            break
        for row in rows:
            scanned += 1
            if scanned > max_scan:
                return lines
            line = accept(row)
            if line is None:
                continue
            lines.append(line)
            if len(lines) >= limit:
                return lines
        if len(rows) < batch:
            break
        offset += len(rows)
    return lines


def collect_from_producer(
    limit: int,
    produce: Callable[[int], list[str]],
    accept: Callable[[str], str | None],
    *,
    max_scan: int = ANALYZE_MAX_SCAN_ROWS,
) -> list[str]:
    """Fill ``limit`` rows from a capped producer that can return more candidates on retry.

    Used when results are not SQL-paginated (e.g. graph cycle search). ``produce(cap)``
    must return a deterministic prefix as ``cap`` grows; already-seen strings are skipped.
    """
    lines: list[str] = []
    seen: set[str] = set()
    scanned = 0
    fetch_cap = limit
    while len(lines) < limit and fetch_cap <= max_scan:
        candidates = produce(fetch_cap)
        if not candidates:
            break
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            scanned += 1
            if scanned > max_scan:
                return lines
            line = accept(candidate)
            if line is None:
                continue
            lines.append(line)
            if len(lines) >= limit:
                return lines
        if len(candidates) < fetch_cap:
            break
        fetch_cap += limit
    return lines


def collect_from_iterable(
    limit: int,
    candidates: Iterable[str],
    accept: Callable[[str], str | None],
    *,
    max_scan: int = ANALYZE_MAX_SCAN_ROWS,
) -> list[str]:
    """Filter an in-memory candidate list until ``limit`` rows pass ``accept``."""
    lines: list[str] = []
    scanned = 0
    for candidate in candidates:
        scanned += 1
        if scanned > max_scan:
            break
        line = accept(candidate)
        if line is None:
            continue
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


# Definition document for a symbol (our trimmed schema uses defn_enclosing_ranges).
SYM_DEF_JOIN = """
    JOIN defn_enclosing_ranges sym_def ON sym_def.symbol_id = gs.id
    JOIN documents def_d ON sym_def.document_id = def_d.id
"""


def fetch_all(db, sql: str, params=()):
    return debug_execute(db, sql, params).fetchall()


def fetch_one(db, sql: str, params=()):
    return debug_execute(db, sql, params).fetchone()


def short_name(symbol: str) -> str:
    if is_module_symbol(symbol):
        return "(module)"
    leaf = extract_leaf_name(symbol)
    if leaf:
        return leaf
    if symbol.endswith("/"):
        return "(module)"
    return symbol.split("/")[-1][:60]


def is_test_path(relative_path: str) -> bool:
    """True for common test layout paths and test-like filenames."""
    p = relative_path.replace("\\", "/")
    lower = p.lower()
    if lower.startswith(("tests/", "test/")):
        return True
    if "/tests/" in lower or "/test/" in lower or "/__tests__/" in lower:
        return True
    if "/__fixtures__/" in lower or "/__mocks__/" in lower:
        return True
    name = lower.rsplit("/", 1)[-1]
    if ".test." in name or ".spec." in name or ".mocha." in name:
        return True
    stem = name.rsplit(".", 1)[0]
    if stem.endswith("_test") or stem.endswith("_spec"):
        return True
    if "test-fixture" in name or "test_fixture" in name or "test-mocks" in name:
        return True
    if name.startswith("test_") and name.endswith(".py"):
        return True
    return name == "conftest.py"


def is_dynamic_loader_path(relative_path: str) -> bool:
    """True for migration files typically loaded by filename; SCIP has no import edge."""
    p = relative_path.replace("\\", "/").lower()
    return "/migrations/" in p


def is_python_main_entrypoint(relative_path: str, symbol: str) -> bool:
    """True for main() in __main__.py — argparse entrypoints SCIP does not link to callers."""
    if short_name(symbol) != "main":
        return False
    return relative_path.replace("\\", "/").endswith("__main__.py")


def analyze_noise(relative_path: str, symbol: str, *, include_tests: bool = False) -> bool:
    """True for rows that clutter analyze dashboards (test paths, module-private helpers)."""
    if not include_tests and is_test_path(relative_path):
        return True
    if short_name(symbol).startswith("_"):
        return True
    if is_python_main_entrypoint(relative_path, symbol):
        return True
    if is_dynamic_loader_path(relative_path):
        return True
    if short_name(symbol) in {"<constructor>", "constructor"}:
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


def is_component_props_type(symbol: str) -> bool:
    """React-style Props interfaces — rarely referenced outside the component file."""
    name = short_name(symbol)
    return bool(name and name.endswith("Props") and "#" in symbol.split("/")[-1])


def stale_type_noise(relative_path: str, symbol: str, consumers: int) -> bool:
    """Dataclass-style types with no SCIP consumers (typing-only)."""
    if is_component_props_type(symbol):
        return True
    if consumers > 0:
        return False
    name = short_name(symbol)
    if not name or name == "(module)" or not name[0].isupper():
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


def section(title: str, lines: list[str], *, preface: str | None = None) -> tuple[str, list[str], str | None]:
    if not lines:
        return title, ["(none)"], None
    return title, lines, preface
