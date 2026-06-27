"""refs command - find all references to a symbol."""

import re
import sys

from ..cli_args import path_scope_from_args
from ..output import limit_and_warn, maybe_print_symbol_header, symbol_output_label, warn_ambiguous_refs
from ..paths import path_filter_sql, path_in_scope
from ..queries import resolve_symbol
from ..session import setup
from ..source import read_source_lines
from ..symbols import extract_leaf_name


def _leaf_appears_on_line(leaf: str, line: str) -> bool:
    """Match leaf as a whole identifier, not a substring of another name."""
    if not leaf:
        return False
    pattern = rf"(?<![\w$`]){re.escape(leaf)}(?![\w$`])"
    return re.search(pattern, line) is not None


def _refs_from_chunk_groups(by_doc, project_root, leaf):
    """Resolve mention chunks to exact file:line reference tuples."""
    results = []
    for _doc_id, info in by_doc.items():
        rel_path = info["path"]
        chunks_list = info["chunks"]
        if not chunks_list:
            continue

        min_line = min(c[1] for c in chunks_list)
        max_line = max(c[2] for c in chunks_list)
        all_single_line = all(c[1] == c[2] for c in chunks_list if c[1] is not None)

        if all_single_line:
            for _chunk_id, start_line, _end_line in chunks_list:
                if start_line is not None:
                    results.append((rel_path, start_line + 1))
            continue

        lines = read_source_lines(project_root, rel_path, min_line, max_line)
        if lines is None:
            for _chunk_id, start_line, _end_line in chunks_list:
                if start_line is not None:
                    results.append((rel_path, start_line + 1))
            continue

        for _chunk_id, start_line, end_line in chunks_list:
            if start_line is None:
                continue
            offset = min_line
            found = False
            for line_idx in range(start_line - offset, min(end_line - offset + 1, len(lines))):
                if _leaf_appears_on_line(leaf, lines[line_idx]):
                    results.append((rel_path, line_idx + offset + 1))
                    found = True
                    break
            if not found:
                results.append((rel_path, start_line + 1))

    return results


def get_exact_refs(db, symbol_id, project_root, max_refs, path_scope=None):
    """Get references with exact line numbers by reading source files."""
    sym_row = db.execute("SELECT symbol FROM global_symbols WHERE id = ?", (symbol_id,)).fetchone()
    if not sym_row:
        return []

    leaf = extract_leaf_name(sym_row[0])
    path_clause, path_params = path_filter_sql(db, path_scope, doc_alias="d")

    batch_size = max(max_refs * 3, 20)
    sql_offset = 0
    seen: set[tuple[str, int]] = set()
    results: list[tuple[str, int]] = []

    while len(results) <= max_refs:
        chunks = db.execute(
            f"""
            SELECT c.id, c.document_id, c.start_line, c.end_line, d.relative_path
            FROM mentions m
            JOIN chunks c ON m.chunk_id = c.id
            JOIN documents d ON c.document_id = d.id
            WHERE m.symbol_id = ? AND m.role != 1{path_clause}
            ORDER BY d.relative_path, c.start_line
            LIMIT ? OFFSET ?
        """,
            (symbol_id, *path_params, batch_size, sql_offset),
        ).fetchall()
        if not chunks:
            break

        sql_offset += len(chunks)
        by_doc = {}
        for chunk_id, doc_id, start_line, end_line, rel_path in chunks:
            if doc_id not in by_doc:
                by_doc[doc_id] = {"path": rel_path, "chunks": []}
            by_doc[doc_id]["chunks"].append((chunk_id, start_line, end_line))

        for ref in _refs_from_chunk_groups(by_doc, project_root, leaf):
            if ref in seen:
                continue
            seen.add(ref)
            results.append(ref)
            if len(results) > max_refs:
                break

        if len(results) > max_refs or len(chunks) < batch_size:
            break

    return limit_and_warn(results, max_refs, "references")


def _resolve_symbol_groups(db, names, limit, path_scope):
    groups = []
    for query_name in names:
        symbols = resolve_symbol(db, query_name, limit=limit + 1, path_scope=path_scope)
        if not symbols:
            print(f"Symbol '{query_name}' not found", file=sys.stderr)
            continue
        trimmed = limit_and_warn(symbols, limit, "symbols")
        warn_ambiguous_refs(query_name, trimmed, db)
        groups.append((query_name, trimmed))
    return groups


def main(args):
    """Find all references to a symbol."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        limit = args.limit
        groups = _resolve_symbol_groups(db, args.symbol, limit, path_scope)

        all_refs = []
        for query_name, symbols in groups:
            for symbol_id, symbol_str, _display_name in symbols:
                refs = get_exact_refs(db, symbol_id, project_root, limit, path_scope=path_scope)
                if refs:
                    label = symbol_output_label(query_name, symbol_str, len(symbols))
                    all_refs.append((label, refs))

        if not all_refs:
            names = ", ".join(f"'{n}'" for n in args.symbol)
            print(f"No references found for {names}", file=sys.stderr)
            sys.exit(1)

        paths_only = getattr(args, "paths_only", False)
        if paths_only:
            unique_paths = sorted({path for _, refs in all_refs for path, _ in refs})
            for path in unique_paths:
                if path_in_scope(path, path_scope):
                    print(path)
            return

        show_headers = len(all_refs) > 1
        for label, refs in all_refs:
            maybe_print_symbol_header(label, show_headers)
            seen = set()
            for path, line in refs:
                key = (path, line)
                if key not in seen and path_in_scope(path, path_scope):
                    seen.add(key)
                    print(f"{path}:{line}")
    finally:
        db.close()
