"""deps command - find outbound dependencies (what a symbol/file calls)."""

import sys

from ..cli_args import path_scope_from_args
from ..output import limit_and_warn
from ..paths import path_in_scope
from ..session import resolve_one_file, resolve_one_symbol, setup
from ..sql import debug_execute
from ..symbols import extract_leaf_name
from ..targets import looks_like_file_target


def _deps_from_symbol(db, symbol_id, limit):
    """Find all symbols referenced within this symbol's definition range."""
    def_range = debug_execute(
        db,
        """
        SELECT document_id, start_line, end_line
        FROM defn_enclosing_ranges
        WHERE symbol_id = ?
        LIMIT 1
        """,
        (symbol_id,),
    ).fetchone()

    if not def_range:
        return []

    doc_id, start_line, end_line = def_range

    # Find chunks that overlap with the function range
    # A chunk overlaps if: chunk.start <= func.end AND chunk.end >= func.start
    return debug_execute(
        db,
        """
        SELECT DISTINCT gs.id, gs.symbol, gs.display_name,
               def_d.relative_path, def_der.start_line
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN global_symbols gs ON m.symbol_id = gs.id
        LEFT JOIN defn_enclosing_ranges def_der ON def_der.symbol_id = gs.id
        LEFT JOIN documents def_d ON def_der.document_id = def_d.id
        WHERE c.document_id = ?
          AND c.start_line <= ?
          AND c.end_line >= ?
          AND m.role != 1
          AND gs.id != ?
        ORDER BY gs.symbol
        LIMIT ?
        """,
        (doc_id, end_line, start_line, symbol_id, limit + 1),
    ).fetchall()


def _deps_from_file(db, file_path, limit):
    """Find all symbols referenced within this file (excluding file's own symbols)."""
    doc_row = debug_execute(
        db,
        "SELECT id FROM documents WHERE relative_path = ?",
        (file_path,),
    ).fetchone()

    if not doc_row:
        return []

    doc_id = doc_row[0]

    # Exclude own symbols via SQL subquery instead of Python filtering
    return debug_execute(
        db,
        """
        SELECT DISTINCT gs.id, gs.symbol, gs.display_name,
               def_d.relative_path, def_der.start_line
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN global_symbols gs ON m.symbol_id = gs.id
        LEFT JOIN defn_enclosing_ranges def_der ON def_der.symbol_id = gs.id
        LEFT JOIN documents def_d ON def_der.document_id = def_d.id
        WHERE c.document_id = ?
          AND m.role != 1
          AND gs.id NOT IN (
              SELECT der2.symbol_id FROM defn_enclosing_ranges der2
              WHERE der2.document_id = ?
          )
        ORDER BY gs.symbol
        LIMIT ?
        """,
        (doc_id, doc_id, limit + 1),
    ).fetchall()


def main(args):
    """Find outbound dependencies of a symbol or file."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        limit = args.limit
        target = args.target
        paths_only = getattr(args, "paths_only", False)

        deps = []
        target_label = target

        if looks_like_file_target(target):
            file_path = resolve_one_file(db, target, path_scope=path_scope)
            deps = _deps_from_file(db, file_path, limit)
            target_label = file_path
        else:
            symbol_id, _symbol_str, _display = resolve_one_symbol(
                db,
                target,
                path_scope=path_scope,
            )
            deps = _deps_from_symbol(db, symbol_id, limit)

        if not deps:
            print(f"No dependencies found for '{target_label}'", file=sys.stderr)
            sys.exit(1)

        deps = limit_and_warn(deps, limit, "dependencies")

        if paths_only:
            seen_paths = set()
            for _sym_id, _symbol, _display, def_path, _def_line in deps:
                if def_path and def_path not in seen_paths and path_in_scope(def_path, path_scope):
                    seen_paths.add(def_path)

            if not seen_paths:
                print(f"No dependency files found for '{target_label}'", file=sys.stderr)
                sys.exit(1)

            for path in sorted(seen_paths):
                print(path)
            return

        for _sym_id, symbol, display, def_path, def_line in deps:
            name = display if display else extract_leaf_name(symbol)

            if def_path and path_in_scope(def_path, path_scope):
                print(f"{def_path}:{def_line + 1}  {name}")
            else:
                print(name)
    finally:
        db.close()
