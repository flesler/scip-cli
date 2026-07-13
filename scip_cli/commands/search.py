"""search command - search symbols by pattern."""

from __future__ import annotations

import re
import sys

from ..cli_args import path_scope_from_args
from ..output import limit_and_warn
from ..paths import path_filter_sql
from ..queries import resolve_document_path, resolve_symbol
from ..session import setup
from ..source import resolve_def_location
from ..sql import escape_like
from ..symbols import SymbolKind, extract_leaf_name, infer_kind, kind_sql_clause


def parse_symbol(symbol):
    """Parse SCIP symbol into (file_path, symbol_name)."""
    match = re.search(r"`([^`]+)`", symbol)
    if match:
        filename = match.group(1)
        before = symbol[: match.start()]
        parts = before.split()
        if len(parts) >= 5:
            dir_path = " ".join(parts[4:])
            file_path = dir_path + filename
        else:
            file_path = filename

        after_file = symbol[match.end() :]
        if after_file.startswith("/"):
            after_file = after_file[1:]

        symbol_name = after_file.rstrip(".")
        return (file_path, symbol_name)

    py_match = re.search(r"(\S+\.py)/(.+)$", symbol)
    if py_match:
        return (py_match.group(1), py_match.group(2))

    return ("?", "?")


def is_noisy_symbol(symbol_str):
    """Filter out noisy symbols (file-level, parameters, etc)."""
    if symbol_str.endswith("/"):
        return True
    if symbol_str.endswith("/__init__:"):
        return True
    if "typeLiteral" in symbol_str and infer_kind(symbol_str) != SymbolKind.PROPERTY:
        return True
    return ").(" in symbol_str


def kind_to_display(kind):
    """Convert kind to compact display format."""
    return kind.value if isinstance(kind, SymbolKind) else str(kind)


def _search_rank_sql() -> str:
    """Prefer real types/functions over nested typeLiteral fields; then shorter symbols."""
    return " ORDER BY CASE WHEN gs.symbol LIKE '%#typeLiteral%' THEN 1 ELSE 0 END, length(gs.symbol)"


def _resolve_file_path(db, symbol_str, doc_path=None):
    if doc_path:
        return doc_path
    resolved = resolve_document_path(db, symbol_str)
    if resolved:
        return resolved
    from ..symbols import extract_file_path_from_symbol

    extracted = extract_file_path_from_symbol(symbol_str)
    if extracted:
        return extracted
    file_path, _ = parse_symbol(symbol_str)
    return file_path


def _print_search_results(results, args):
    """Emit search rows in human or machine-readable form."""
    names_only = getattr(args, "names_only", False)
    paths_only = getattr(args, "paths_only", False)

    if paths_only:
        paths = sorted({file_path for file_path, _, _, _ in results if file_path != "?"})
        for path in paths:
            print(path)
        return

    if names_only:
        for _, _, _, name in results:
            print(name)
        return

    for file_path, line, kind_display, name in results:
        print(f"{file_path}:{line} {kind_display} {name}")


def _qualified_pattern(pattern: str) -> bool:
    return "." in pattern and "/" not in pattern and "*" not in pattern


def _result_key(result: tuple[str, int | str, str, str]) -> tuple[str, int | str, str]:
    """Display identity: same file/line/name collapses SCIP duplicates."""
    file_path, line, _kind, name = result
    return (file_path, line, name)


def _search_results_from_symbols(db, project_root, symbols, limit):
    """Turn resolve_symbol rows into search result tuples."""
    results: list[tuple[str, int | str, str, str]] = []
    seen: set[tuple[str, int | str, str]] = set()
    for symbol_id, symbol_str, _display_name in symbols:
        loc = resolve_def_location(db, project_root, symbol_id, symbol_str)
        if loc:
            file_path, start_line, _end_line = loc
            line: int | str = start_line + 1
        else:
            file_path = _resolve_file_path(db, symbol_str)
            line = "?"
        kind = infer_kind(symbol_str)
        short = extract_leaf_name(symbol_str)
        result = (file_path, line, kind_to_display(kind), short)
        key = _result_key(result)
        if key in seen:
            continue
        seen.add(key)
        results.append(result)
        if len(results) > limit:
            break
    return limit_and_warn(results, limit, "results")


def _row_to_result(db, project_root, symbol_id, symbol_str, start_line, doc_path):
    kind = infer_kind(symbol_str)
    loc = resolve_def_location(db, project_root, symbol_id, symbol_str)
    if loc:
        file_path, resolved_start, _end = loc
        line: int | str = resolved_start + 1
    else:
        file_path = _resolve_file_path(db, symbol_str, doc_path)
        line = start_line + 1 if start_line is not None else "?"
    symbol_name = extract_leaf_name(symbol_str)
    return (file_path, line, kind_to_display(kind), symbol_name)


def _collect_unique_from_rows(db, project_root, cursor, limit, kind=None):
    """Resolve rows to display lines, skipping noisy/duplicate identities."""
    results: list[tuple[str, int | str, str, str]] = []
    seen: set[tuple[str, int | str, str]] = set()
    for symbol_id, symbol_str, _display_name, start_line, doc_path in cursor:
        if is_noisy_symbol(symbol_str):
            continue
        if kind is not None and infer_kind(symbol_str) != kind:
            continue
        result = _row_to_result(db, project_root, symbol_id, symbol_str, start_line, doc_path)
        key = _result_key(result)
        if key in seen:
            continue
        seen.add(key)
        results.append(result)
        if len(results) > limit:
            break
    return limit_and_warn(results, limit, "results")


def main(args):
    """Search symbols by pattern."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        limit = args.limit
        patterns = args.pattern

        resolved_symbols = []
        like_patterns = []
        for pattern in patterns:
            if _qualified_pattern(pattern):
                symbols = resolve_symbol(db, pattern, args.kind, limit=limit + 1, path_scope=path_scope)
                if symbols:
                    resolved_symbols.extend(symbols)
                    continue
            like_patterns.append(pattern)

        if resolved_symbols and not like_patterns:
            results = _search_results_from_symbols(db, project_root, resolved_symbols, limit)
            _print_search_results(results, args)
            return

        prefill = _search_results_from_symbols(db, project_root, resolved_symbols, limit) if resolved_symbols else []
        patterns = like_patterns
        if not patterns:
            if prefill:
                _print_search_results(prefill, args)
            else:
                pattern_str = " or ".join(f"'{p}'" for p in args.pattern)
                print(f"No symbols found matching {pattern_str}", file=sys.stderr)
                sys.exit(1)
            return

        path_clause, path_params = path_filter_sql(db, path_scope)
        kind_clause = kind_sql_clause(args.kind) if args.kind else ""
        join_docs = (
            " LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id"
            " LEFT JOIN documents d ON der.document_id = d.id"
        )

        # Build OR clause for multiple patterns
        pattern_clauses = []
        pattern_params = []
        for pattern in patterns:
            escaped = escape_like(pattern)
            pattern_clauses.append("gs.symbol LIKE ? ESCAPE '\\'")
            pattern_params.append(f"%{escaped}%")

        where_clause = " OR ".join(pattern_clauses)
        rank_sql = _search_rank_sql()
        # Prisma-style indexes can have dozens of typeLiterals per leaf; scan past them.
        scan_limit = max(limit * 50, 1000)

        cursor = db.execute(
            f"""
            SELECT gs.id, gs.symbol, gs.display_name, der.start_line, d.relative_path
            FROM global_symbols gs
            {join_docs}
            WHERE ({where_clause}){path_clause}{kind_clause}
            {rank_sql}
            LIMIT ?
        """,
            (*pattern_params, *path_params, scan_limit),
        )

        results = _collect_unique_from_rows(
            db,
            project_root,
            cursor,
            limit,
            kind=args.kind,
        )

        if not results:
            pattern_str = " or ".join(f"'{p}'" for p in patterns)
            if args.kind:
                print(
                    f"No {args.kind} symbols found matching {pattern_str}",
                    file=sys.stderr,
                )
            else:
                print(f"No symbols found matching {pattern_str}", file=sys.stderr)
            sys.exit(1)

        if prefill:
            seen = {_result_key(r) for r in prefill}
            results = prefill + [r for r in results if _result_key(r) not in seen]
            results = results[:limit]

        _print_search_results(results, args)
    finally:
        db.close()
