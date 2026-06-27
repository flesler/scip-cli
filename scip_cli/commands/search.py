"""search command - search symbols by pattern."""

import re
import sys

from ..cli_args import path_scope_from_args
from ..output import limit_and_warn
from ..paths import path_filter_sql
from ..queries import get_def_location, resolve_document_path, resolve_symbol
from ..session import setup
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


def _search_rows_with_kind(db, sql, params, kind, limit):
    """Fetch search rows matching kind, stopping once limit is exceeded."""
    rows = []
    cursor = db.execute(sql, params)
    while True:
        batch = cursor.fetchmany(500)
        if not batch:
            break
        for row in batch:
            if infer_kind(row[1]) != kind:
                continue
            rows.append(row)
            if len(rows) > limit:
                break
        if len(rows) > limit:
            break
    return limit_and_warn(rows, limit, "results")


def _resolve_file_path(db, symbol_str, doc_path=None):
    if doc_path:
        return doc_path
    resolved = resolve_document_path(db, symbol_str)
    if resolved:
        return resolved
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


def main(args):
    """Search symbols by pattern."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        limit = args.limit
        patterns = args.pattern

        # Single dotted pattern (e.g. "Widget.run") - try exact resolve first
        if len(patterns) == 1 and "." in patterns[0] and "/" not in patterns[0] and "*" not in patterns[0]:
            symbols = resolve_symbol(db, patterns[0], args.kind, limit=limit + 1, path_scope=path_scope)
            if symbols:
                symbols = limit_and_warn(symbols, limit, "results")
                results = []
                for symbol_id, symbol_str, _display_name in symbols:
                    row = get_def_location(db, symbol_id)
                    start_line = row[1] if row else None
                    file_path = row[0] if row else _resolve_file_path(db, symbol_str)
                    kind = infer_kind(symbol_str)
                    line = start_line + 1 if start_line is not None else "?"
                    short = extract_leaf_name(symbol_str)
                    results.append((file_path, line, kind_to_display(kind), short))
                _print_search_results(results, args)
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

        if args.kind:
            rows = _search_rows_with_kind(
                db,
                f"""
                SELECT gs.id, gs.symbol, gs.display_name, der.start_line, d.relative_path
                FROM global_symbols gs
                {join_docs}
                WHERE ({where_clause}){path_clause}{kind_clause}
            """,
                (*pattern_params, *path_params),
                args.kind,
                limit,
            )
        else:
            rows = db.execute(
                f"""
                SELECT gs.id, gs.symbol, gs.display_name, der.start_line, d.relative_path
                FROM global_symbols gs
                {join_docs}
                WHERE ({where_clause}){path_clause}
                LIMIT ?
            """,
                (*pattern_params, *path_params, limit + 1),
            ).fetchall()
            rows = limit_and_warn(rows, limit, "results")

        if not rows:
            pattern_str = " or ".join(f"'{p}'" for p in patterns)
            if args.kind:
                print(
                    f"No {args.kind} symbols found matching {pattern_str}",
                    file=sys.stderr,
                )
            else:
                print(f"No symbols found matching {pattern_str}", file=sys.stderr)
            sys.exit(1)

        results = []
        for _symbol_id, symbol_str, _display_name, start_line, doc_path in rows:
            if is_noisy_symbol(symbol_str):
                continue

            kind = infer_kind(symbol_str)
            file_path = _resolve_file_path(db, symbol_str, doc_path)
            line = start_line + 1 if start_line is not None else "?"
            symbol_name = extract_leaf_name(symbol_str)
            results.append((file_path, line, kind_to_display(kind), symbol_name))

        if not results:
            pattern_str = " or ".join(f"'{p}'" for p in patterns)
            print(f"No symbols found matching {pattern_str}", file=sys.stderr)
            sys.exit(1)

        _print_search_results(results, args)
    finally:
        db.close()
