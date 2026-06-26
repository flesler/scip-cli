"""search command - search symbols by pattern."""
import sys
import re

from ..cli_args import path_scope_from_args
from ..paths import path_filter_sql
from ..queries import get_def_location, resolve_document_path, resolve_symbol
from ..session import setup
from ..sql import escape_like
from ..symbols import SymbolKind, extract_leaf_name, infer_kind


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
    if "typeLiteral" in symbol_str:
        return True
    if ").(" in symbol_str:
        return True
    return False


def kind_to_display(kind):
    """Convert kind to display format."""
    kind_map = {
        SymbolKind.FUNCTION: "Function",
        SymbolKind.METHOD: "Method",
        SymbolKind.CLASS: "Class",
        SymbolKind.PROPERTY: "Property",
        SymbolKind.VARIABLE: "Variable",
    }
    return kind_map.get(kind, "Unknown")


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
        want_doc_path = bool(
            path_scope
            or getattr(args, "names_only", False)
            or getattr(args, "paths_only", False)
        )

        if (
            "." in args.pattern
            and "/" not in args.pattern
            and "*" not in args.pattern
        ):
            symbols = resolve_symbol(
                db, args.pattern, args.kind, limit=limit + 1, path_scope=path_scope
            )
            if symbols:
                hit_limit = len(symbols) > limit
                symbols = symbols[:limit]
                results = []
                for symbol_id, symbol_str, display_name in symbols:
                    row = get_def_location(db, symbol_id)
                    start_line = row[1] if row else None
                    file_path = row[0] if row else _resolve_file_path(db, symbol_str)
                    kind = infer_kind(symbol_str)
                    line = start_line + 1 if start_line is not None else "?"
                    short = extract_leaf_name(symbol_str)
                    results.append((file_path, line, kind_to_display(kind), short))
                _print_search_results(results, args)
                if hit_limit:
                    print(
                        f"# Warning: more than {limit} results, showing first {limit}",
                        file=sys.stderr,
                    )
                return

        escaped_pattern = escape_like(args.pattern)
        path_clause, path_params = path_filter_sql(db, path_scope)
        join_docs = (
            " LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id"
            " LEFT JOIN documents d ON der.document_id = d.id"
            if want_doc_path
            else " LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id"
        )
        doc_col = ", d.relative_path" if want_doc_path else ""

        if args.kind:
            rows = db.execute(
                f"""
                SELECT gs.id, gs.symbol, gs.display_name, der.start_line{doc_col}
                FROM global_symbols gs
                {join_docs}
                WHERE gs.symbol LIKE ? ESCAPE '\\'{path_clause}
            """,
                (f"%{escaped_pattern}%", *path_params),
            ).fetchall()

            rows = [r for r in rows if infer_kind(r[1]) == args.kind]
            hit_limit = len(rows) > limit
            rows = rows[:limit]
        else:
            rows = db.execute(
                f"""
                SELECT gs.id, gs.symbol, gs.display_name, der.start_line{doc_col}
                FROM global_symbols gs
                {join_docs}
                WHERE gs.symbol LIKE ? ESCAPE '\\'{path_clause}
                LIMIT ?
            """,
                (f"%{escaped_pattern}%", *path_params, limit + 1),
            ).fetchall()
            hit_limit = len(rows) > limit
            rows = rows[:limit]

        if not rows:
            if args.kind:
                print(
                    f"No {args.kind} symbols found matching '{args.pattern}'",
                    file=sys.stderr,
                )
            else:
                print(f"No symbols found matching '{args.pattern}'", file=sys.stderr)
            sys.exit(1)

        results = []
        for row in rows:
            if want_doc_path:
                symbol_id, symbol_str, display_name, start_line, doc_path = row
            else:
                symbol_id, symbol_str, display_name, start_line = row
                doc_path = None
            if is_noisy_symbol(symbol_str):
                continue

            kind = infer_kind(symbol_str)
            file_path = _resolve_file_path(db, symbol_str, doc_path)
            _, symbol_name = parse_symbol(symbol_str)
            line = start_line + 1 if start_line is not None else "?"
            symbol_name = symbol_name.rstrip(".#")
            if symbol_name.endswith("()"):
                symbol_name = symbol_name[:-2]
            if not symbol_name or symbol_name == "?":
                symbol_name = extract_leaf_name(symbol_str)
            results.append((file_path, line, kind_to_display(kind), symbol_name))

        if not results:
            print(f"No symbols found matching '{args.pattern}'", file=sys.stderr)
            sys.exit(1)

        _print_search_results(results, args)

        if hit_limit:
            print(
                f"# Warning: more than {limit} results, showing first {limit}",
                file=sys.stderr,
            )
    finally:
        db.close()
