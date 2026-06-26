"""SQLite queries for symbol and document resolution."""
from pathlib import Path

from .paths import path_filter_sql, path_in_scope
from .sql import debug_execute, escape_like
from .symbols import (
    extract_leaf_name,
    infer_kind,
    is_parameter_symbol,
    parse_qualified_name,
    symbol_matches_qualifier,
)


def _query_document_paths(db, sql: str, params: tuple) -> list[str]:
    rows = debug_execute(db, sql, params).fetchall()
    return [row[0] for row in rows]


def _rank_file_matches(paths: list[str], pattern: str) -> list[str]:
    """Prefer exact basename hits and non-test files when multiple paths match."""

    def sort_key(path: str) -> tuple:
        name = Path(path).name
        stem = Path(path).stem
        is_test = ".test." in name or name.endswith(".spec.ts") or name.endswith(".spec.tsx")
        exact_basename = name == pattern or stem == pattern
        return (not exact_basename, is_test, path)

    return sorted(paths, key=sort_key)


def resolve_symbol(db, name, kind_filter=None, limit=None, path_scope=None):
    """Resolve bare or qualified name to symbol_id(s)."""
    qualifier_parts, leaf = parse_qualified_name(name)
    search_name = leaf if qualifier_parts else name
    escaped = escape_like(search_name)
    path_clause, path_params = path_filter_sql(db, path_scope)

    if limit:
        limit_clause = "LIMIT ?"
        limit_param = (limit,)
    else:
        limit_clause = ""
        limit_param = ()

    if path_scope:
        sql = f"""
            SELECT DISTINCT gs.id, gs.symbol, gs.display_name
            FROM global_symbols gs
            LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
            LEFT JOIN documents d ON der.document_id = d.id
            WHERE (
                gs.symbol LIKE ? ESCAPE '\\' OR gs.symbol LIKE ? ESCAPE '\\'
                OR gs.symbol LIKE ? ESCAPE '\\' OR gs.symbol LIKE ? ESCAPE '\\'
                OR gs.symbol LIKE ? ESCAPE '\\'
            ){path_clause}
            {limit_clause}
        """
        params = (
            f"%/{escaped}().",
            f"%/{escaped}#",
            f"%/{escaped}.",
            f"%#{escaped}().",
            f"%#{escaped}.",
            *path_params,
        ) + limit_param
        rows = debug_execute(db, sql, params).fetchall()
        results = list(rows)

        if not results:
            sql = f"""
                SELECT DISTINCT gs.id, gs.symbol, gs.display_name
                FROM global_symbols gs
                LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
                LEFT JOIN documents d ON der.document_id = d.id
                WHERE gs.symbol LIKE ? ESCAPE '\\'{path_clause}
                {limit_clause}
            """
            params = (f"%{escaped}%", *path_params) + limit_param
            rows = debug_execute(db, sql, params).fetchall()
            results = [
                r for r in rows
                if search_name in r[1].split("/")[-1] or search_name in extract_leaf_name(r[1])
            ]
    else:
        sql = f"""
            SELECT id, symbol, display_name FROM global_symbols
            WHERE symbol LIKE ? ESCAPE '\\' OR symbol LIKE ? ESCAPE '\\'
               OR symbol LIKE ? ESCAPE '\\' OR symbol LIKE ? ESCAPE '\\'
               OR symbol LIKE ? ESCAPE '\\'
            {limit_clause}
        """
        params = (
            f"%/{escaped}().",
            f"%/{escaped}#",
            f"%/{escaped}.",
            f"%#{escaped}().",
            f"%#{escaped}.",
        ) + limit_param
        rows = debug_execute(db, sql, params).fetchall()
        results = list(rows)

        if not results:
            sql = f"SELECT id, symbol, display_name FROM global_symbols WHERE symbol LIKE ? ESCAPE '\\' {limit_clause}"
            params = (f"%{escaped}%",) + limit_param
            rows = debug_execute(db, sql, params).fetchall()
            results = [
                r for r in rows
                if search_name in r[1].split("/")[-1] or search_name in extract_leaf_name(r[1])
            ]

    if qualifier_parts:
        results = [
            r for r in results
            if symbol_matches_qualifier(r[1], qualifier_parts, leaf)
            and not is_parameter_symbol(r[1])
        ]

    if kind_filter and results:
        results = [r for r in results if infer_kind(r[1]) == kind_filter]

    return results


def resolve_file(db, file_pattern, path_scope=None):
    """Resolve a file path using exact, basename, suffix, then fuzzy matching."""
    pattern = file_pattern.strip()
    if not pattern:
        return []

    escaped = escape_like(pattern)
    basename = Path(pattern).name
    escaped_basename = escape_like(basename)

    candidates: list[str] = []

    candidates.extend(
        _query_document_paths(
            db,
            "SELECT relative_path FROM documents WHERE relative_path = ?",
            (pattern,),
        )
    )

    if "/" in pattern:
        candidates.extend(
            _query_document_paths(
                db,
                """
                SELECT relative_path FROM documents
                WHERE relative_path LIKE ? ESCAPE '\\'
                   OR relative_path LIKE ? ESCAPE '\\'
                ORDER BY relative_path
                """,
                (f"%/{escaped}", f"%{escaped}"),
            )
        )
    elif "." in pattern:
        candidates.extend(
            _query_document_paths(
                db,
                """
                SELECT relative_path FROM documents
                WHERE relative_path = ?
                   OR relative_path LIKE ? ESCAPE '\\'
                ORDER BY relative_path
                """,
                (pattern, f"%/{escaped_basename}"),
            )
        )
    else:
        candidates.extend(
            _query_document_paths(
                db,
                """
                SELECT relative_path FROM documents
                WHERE relative_path LIKE ? ESCAPE '\\'
                   OR relative_path LIKE ? ESCAPE '\\'
                   OR relative_path LIKE ? ESCAPE '\\'
                ORDER BY relative_path
                """,
                (
                    f"%/{escaped_basename}.ts",
                    f"%/{escaped_basename}.tsx",
                    f"%/{escaped_basename}.js",
                ),
            )
        )
        candidates.extend(
            path
            for path in _query_document_paths(
                db,
                "SELECT relative_path FROM documents WHERE relative_path LIKE ? ESCAPE '\\'",
                (f"%{escaped}%",),
            )
            if Path(path).stem == pattern
        )

    if not candidates:
        candidates.extend(
            _query_document_paths(
                db,
                "SELECT relative_path FROM documents WHERE relative_path LIKE ? ESCAPE '\\' ORDER BY relative_path",
                (f"%{escaped}%",),
            )
        )

    unique = list(dict.fromkeys(candidates))
    ranked = _rank_file_matches(unique, basename if "." in pattern else pattern)
    if path_scope:
        ranked = [path for path in ranked if path_in_scope(path, path_scope)]
    return ranked


def get_file_symbols(db, relative_path, limit=None):
    """Get all symbols defined in a file."""
    limit_clause = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT gs.id, gs.symbol, gs.display_name, der.start_line, der.end_line
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents d ON der.document_id = d.id
        WHERE d.relative_path = ?
        ORDER BY der.start_line
        {limit_clause}
    """
    return debug_execute(db, sql, (relative_path,)).fetchall()


def get_refs_for_symbols(db, symbol_ids):
    """Get all references for multiple symbol_ids in one query."""
    if not symbol_ids:
        return {}

    placeholders = ",".join("?" * len(symbol_ids))
    rows = debug_execute(db, f"""
        SELECT m.symbol_id, d.relative_path, c.start_line
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents d ON c.document_id = d.id
        WHERE m.symbol_id IN ({placeholders}) AND m.role != 1
    """, symbol_ids).fetchall()

    result = {}
    for symbol_id, path, line in rows:
        if symbol_id not in result:
            result[symbol_id] = []
        result[symbol_id].append((path, line))

    return result


def get_members(db, symbol_id):
    """Get members (children) of a symbol."""
    row = debug_execute(db, "SELECT symbol FROM global_symbols WHERE id = ?", (symbol_id,)).fetchone()
    if not row:
        return []
    parent_symbol = row[0]

    rows = debug_execute(db, """
        SELECT gs.id, gs.symbol, gs.display_name, der.start_line, der.end_line
        FROM global_symbols gs
        LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        WHERE gs.enclosing_symbol = ?
        ORDER BY der.start_line
    """, (parent_symbol,)).fetchall()

    if not rows:
        escaped_parent = escape_like(parent_symbol)
        rows = debug_execute(db, """
            SELECT gs.id, gs.symbol, gs.display_name, der.start_line, der.end_line
            FROM global_symbols gs
            LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
            WHERE gs.symbol LIKE ? ESCAPE '\\' AND gs.symbol != ?
            ORDER BY der.start_line
        """, (escaped_parent + "%", parent_symbol)).fetchall()

    return [r for r in rows if ").(" not in r[1]]


def get_def_location(db, symbol_id):
    """Get definition location for a symbol."""
    return debug_execute(db, """
        SELECT d.relative_path, der.start_line, der.end_line
        FROM defn_enclosing_ranges der
        JOIN documents d ON der.document_id = d.id
        WHERE der.symbol_id = ?
    """, (symbol_id,)).fetchone()


def resolve_document_path(db, symbol_str):
    """Map a SCIP symbol to the indexed document relative_path."""
    from .symbols import extract_file_path_from_symbol

    extracted = extract_file_path_from_symbol(symbol_str)
    if not extracted:
        return None

    rows = db.execute(
        "SELECT relative_path FROM documents WHERE relative_path = ?",
        (extracted,),
    ).fetchall()
    if rows:
        return rows[0][0]

    basename = Path(extracted).name
    rows = db.execute(
        "SELECT relative_path FROM documents WHERE relative_path LIKE ? ESCAPE '\\'",
        (f"%{escape_like(basename)}",),
    ).fetchall()
    if not rows:
        return extracted

    suffix_matches = [row[0] for row in rows if row[0].endswith(extracted)]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    if len(rows) == 1:
        return rows[0][0]
    return suffix_matches[0] if suffix_matches else rows[0][0]
