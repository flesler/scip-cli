"""Project-wide analyze checks — SQL only."""

from __future__ import annotations

import re

from ..paths import path_filter_sql, path_filter_sql_any, path_in_scope
from .common import (
    DEFAULT_LIMIT,
    SYM_DEF_JOIN,
    analyze_noise,
    cycle_path_noise,
    fetch_all,
    file_pair_noise,
    is_test_path,
    short_name,
    stale_type_noise,
)
from .sections import Check, Priority, run_checks

_FILE_EDGES_SQL = """
    SELECT DISTINCT d1.relative_path AS from_file, d2.relative_path AS to_file
    FROM mentions m
    JOIN chunks c ON m.chunk_id = c.id
    JOIN documents d1 ON c.document_id = d1.id
    JOIN defn_enclosing_ranges der ON m.symbol_id = der.symbol_id
    JOIN documents d2 ON der.document_id = d2.id
    WHERE d1.id != d2.id AND m.role != 1
"""


def _scope_suffix(scope: str | None) -> str:
    return f" [{scope}]" if scope else ""


def _cycle_touches_scope(cycle_line: str, scope: str) -> bool:
    parts = re.split(r"\s<->\s|\s->\s", cycle_line)
    return any(path_in_scope(part.strip(), scope) for part in parts if part.strip())


def bottlenecks(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    rows = fetch_all(
        db,
        f"""
        WITH fan_in AS (
            SELECT gs.id AS symbol_id,
                   COUNT(DISTINCT ref_d.id) AS fan_in
            FROM global_symbols gs
            {SYM_DEF_JOIN}
            JOIN mentions m ON m.symbol_id = gs.id AND m.role != 1
            JOIN chunks c ON m.chunk_id = c.id
            JOIN documents ref_d ON c.document_id = ref_d.id
            WHERE ref_d.id != def_d.id
            GROUP BY gs.id
        ),
        fan_out AS (
            SELECT der.symbol_id,
                   COUNT(DISTINCT m.symbol_id) AS fan_out
            FROM defn_enclosing_ranges der
            JOIN documents def_doc ON der.document_id = def_doc.id
            JOIN chunks c ON c.document_id = def_doc.id
            JOIN mentions m ON m.chunk_id = c.id AND m.role NOT IN (1, 2)
            JOIN defn_enclosing_ranges callee_def ON m.symbol_id = callee_def.symbol_id
            JOIN documents callee_doc ON callee_def.document_id = callee_doc.id
            WHERE callee_doc.id != def_doc.id
            GROUP BY der.symbol_id
        )
        SELECT gs.symbol, def_d.relative_path, fi.fan_in, fo.fan_out,
               fi.fan_in * fo.fan_out AS score
        FROM global_symbols gs
        {SYM_DEF_JOIN}
        JOIN fan_in fi ON fi.symbol_id = gs.id
        JOIN fan_out fo ON fo.symbol_id = gs.id
        WHERE fi.fan_in >= 1 AND fo.fan_out >= 1{scope_clause}
        ORDER BY score DESC, fi.fan_in DESC
        LIMIT ?
        """,
        (*scope_params, limit * 5),
    )
    lines = [
        f"{short_name(symbol)}  score={score}  fan_in={fan_in}  fan_out={fan_out}  ({path})"
        for symbol, path, fan_in, fan_out, score in rows
        if not analyze_noise(path, symbol, include_tests=include_tests)
    ]
    return lines[:limit]


def hotspots(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    rows = fetch_all(
        db,
        f"""
        SELECT gs.symbol, def_d.relative_path,
               COUNT(*) AS ref_count,
               COUNT(DISTINCT ref_d.id) AS file_count
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents ref_d ON c.document_id = ref_d.id
        JOIN global_symbols gs ON m.symbol_id = gs.id
        {SYM_DEF_JOIN}
        WHERE m.role != 1{scope_clause}
        GROUP BY gs.id
        ORDER BY ref_count DESC
        LIMIT ?
        """,
        (*scope_params, limit * 5),
    )
    lines = [
        f"{short_name(symbol)}  refs={ref_count}  files={file_count}  ({path})"
        for symbol, path, ref_count, file_count in rows
        if not analyze_noise(path, symbol, include_tests=include_tests)
    ]
    return lines[:limit]


def cycles(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    rows = fetch_all(
        db,
        f"""
        WITH RECURSIVE
        edges AS ({_FILE_EDGES_SQL}),
        walk(origin, current, depth, path) AS (
            SELECT from_file, from_file, 0, from_file FROM edges
            UNION ALL
            SELECT walk.origin, e.to_file, walk.depth + 1,
                   walk.path || ' -> ' || e.to_file
            FROM walk
            JOIN edges e ON walk.current = e.from_file
            WHERE walk.depth < 8
              AND instr(walk.path, e.to_file) = 0
        )
        SELECT DISTINCT walk.path || ' -> ' || walk.origin AS cycle_path
        FROM walk
        JOIN edges e ON walk.current = e.from_file AND e.to_file = walk.origin
        WHERE walk.depth > 0
        ORDER BY cycle_path
        LIMIT ?
        """,
        (limit * 5,),
    )
    two_way = fetch_all(
        db,
        f"""
        WITH edges AS ({_FILE_EDGES_SQL})
        SELECT e1.from_file || ' <-> ' || e1.to_file
        FROM edges e1
        JOIN edges e2 ON e1.from_file = e2.to_file AND e1.to_file = e2.from_file
        WHERE e1.from_file < e1.to_file
        ORDER BY 1
        LIMIT ?
        """,
        (limit * 5,),
    )
    lines = [row[0] for row in two_way if not cycle_path_noise(row[0], include_tests=include_tests)]
    for row in rows:
        path = row[0]
        if path not in lines and not cycle_path_noise(path, include_tests=include_tests):
            lines.append(path)
    if scope:
        lines = [line for line in lines if _cycle_touches_scope(line, scope)]
    return lines[:limit]


def stale_types(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    rows = fetch_all(
        db,
        f"""
        SELECT gs.symbol, def_d.relative_path,
               COUNT(DISTINCT CASE WHEN ref_d.id != def_d.id THEN ref_d.id END) AS consumers
        FROM global_symbols gs
        {SYM_DEF_JOIN}
        LEFT JOIN mentions m ON m.symbol_id = gs.id AND m.role != 1
        LEFT JOIN chunks c ON m.chunk_id = c.id
        LEFT JOIN documents ref_d ON c.document_id = ref_d.id
        WHERE gs.symbol LIKE '%#'
          AND gs.symbol NOT LIKE '%().'
          AND gs.symbol NOT LIKE '%#typeLiteral%'{scope_clause}
        GROUP BY gs.id
        HAVING consumers <= 1
        ORDER BY consumers ASC, def_d.relative_path
        LIMIT ?
        """,
        (*scope_params, limit * 5),
    )
    lines = [
        f"{short_name(symbol)}  consumers={consumers}  ({path})"
        for symbol, path, consumers in rows
        if not analyze_noise(path, symbol, include_tests=include_tests)
        and not stale_type_noise(path, symbol, consumers)
    ]
    return lines[:limit]


def unreferenced_symbols(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    rows = fetch_all(
        db,
        f"""
        SELECT gs.symbol, def_d.relative_path,
               sym_def.end_line - sym_def.start_line + 1 AS loc
        FROM global_symbols gs
        {SYM_DEF_JOIN}
        WHERE NOT EXISTS (
            SELECT 1 FROM mentions m
            WHERE m.symbol_id = gs.id AND m.role = 0
        )
        AND NOT EXISTS (
            SELECT 1 FROM mentions m
            JOIN chunks c ON m.chunk_id = c.id
            WHERE m.symbol_id = gs.id AND m.role != 1 AND c.document_id != def_d.id
        ){scope_clause}
        ORDER BY loc DESC, def_d.relative_path
        LIMIT ?
        """,
        (*scope_params, limit * 5),
    )
    lines = [
        f"{short_name(symbol)}  loc={loc}  ({path})"
        for symbol, path, loc in rows
        if not analyze_noise(path, symbol, include_tests=include_tests)
    ]
    return lines[:limit]


def same_file_only(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    rows = fetch_all(
        db,
        f"""
        SELECT gs.symbol, def_d.relative_path,
               sym_def.end_line - sym_def.start_line + 1 AS loc
        FROM global_symbols gs
        {SYM_DEF_JOIN}
        WHERE EXISTS (
            SELECT 1 FROM mentions m
            JOIN chunks c ON m.chunk_id = c.id
            WHERE m.symbol_id = gs.id AND m.role = 0 AND c.document_id = def_d.id
        )
        AND NOT EXISTS (
            SELECT 1 FROM mentions m
            JOIN chunks c ON m.chunk_id = c.id
            WHERE m.symbol_id = gs.id AND m.role = 0 AND c.document_id != def_d.id
        ){scope_clause}
        ORDER BY loc DESC, def_d.relative_path
        LIMIT ?
        """,
        (*scope_params, limit * 5),
    )
    lines = [
        f"{short_name(symbol)}  loc={loc}  ({path})"
        for symbol, path, loc in rows
        if not analyze_noise(path, symbol, include_tests=include_tests)
    ]
    return lines[:limit]


def symbols_test_only_consumers(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    if include_tests:
        return []
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    rows = fetch_all(
        db,
        f"""
        SELECT gs.symbol, def_d.relative_path,
               GROUP_CONCAT(DISTINCT ref_d.relative_path) AS consumer_paths
        FROM global_symbols gs
        {SYM_DEF_JOIN}
        JOIN mentions m ON m.symbol_id = gs.id AND m.role != 1
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents ref_d ON c.document_id = ref_d.id
        WHERE ref_d.id != def_d.id{scope_clause}
        GROUP BY gs.id
        HAVING COUNT(DISTINCT ref_d.id) > 0
        ORDER BY def_d.relative_path, gs.symbol
        LIMIT ?
        """,
        (*scope_params, limit * 10),
    )
    lines = []
    for symbol, path, consumer_paths in rows:
        if analyze_noise(path, symbol, include_tests=include_tests):
            continue
        paths = [part.strip() for part in (consumer_paths or "").split(",") if part.strip()]
        if paths and all(is_test_path(p) for p in paths):
            lines.append(f"{short_name(symbol)}  test_consumers={len(paths)}  ({path})")
    return lines[:limit]


def dead_exports(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    rows = fetch_all(
        db,
        f"""
        SELECT gs.symbol, def_d.relative_path,
               sym_def.end_line - sym_def.start_line + 1 AS loc
        FROM global_symbols gs
        {SYM_DEF_JOIN}
        WHERE NOT EXISTS (
            SELECT 1
            FROM mentions m
            JOIN chunks c ON m.chunk_id = c.id
            WHERE m.symbol_id = gs.id
              AND m.role != 1
              AND c.document_id != def_d.id
        ){scope_clause}
        ORDER BY loc DESC, def_d.relative_path
        LIMIT ?
        """,
        (*scope_params, limit * 5),
    )
    lines = [
        f"{short_name(symbol)}  loc={loc}  ({path})"
        for symbol, path, loc in rows
        if not analyze_noise(path, symbol, include_tests=include_tests)
    ]
    return lines[:limit]


def top_coupling(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql_any(db, scope, "def_d", "ref_d")
    rows = fetch_all(
        db,
        f"""
        SELECT def_d.relative_path AS file1,
               ref_d.relative_path AS file2,
               COUNT(DISTINCT gs.id) AS shared
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents ref_d ON c.document_id = ref_d.id
        JOIN global_symbols gs ON m.symbol_id = gs.id
        {SYM_DEF_JOIN}
        WHERE m.role != 1 AND def_d.id != ref_d.id{scope_clause}
        GROUP BY def_d.id, ref_d.id
        ORDER BY shared DESC
        LIMIT ?
        """,
        (*scope_params, limit * 5),
    )
    lines = [
        f"{file1}  <->  {file2}  shared={shared}"
        for file1, file2, shared in rows
        if not file_pair_noise(file1, file2, include_tests=include_tests)
    ]
    return lines[:limit]


def run_all(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
    priorities=None,
) -> list[tuple[str, list[str]]]:
    suffix = _scope_suffix(scope)
    opts = {"include_tests": include_tests, "scope": scope}
    checks = [
        Check("cycles", Priority.HIGH, f"Cycles (file dependencies){suffix}", cycles),
        Check("unreferenced", Priority.HIGH, f"Unreferenced symbols (no refs){suffix}", unreferenced_symbols),
        Check("dead_exports", Priority.HIGH, f"Dead exports (no external refs){suffix}", dead_exports),
        Check("stale_types", Priority.HIGH, f"Stale types (≤1 external consumer){suffix}", stale_types),
        Check("same_file_only", Priority.MEDIUM, f"Same-file only (consider _prefix){suffix}", same_file_only),
        Check("test_only", Priority.MEDIUM, f"Test-only consumers{suffix}", symbols_test_only_consumers),
        Check("top_coupling", Priority.LOW, f"Top coupling (file pairs){suffix}", top_coupling),
        Check("bottlenecks", Priority.LOW, f"Bottlenecks (fan-in x fan-out){suffix}", bottlenecks),
        Check("hotspots", Priority.LOW, f"Hotspots (most referenced){suffix}", hotspots),
    ]
    return run_checks(checks, db, limit, priorities, **opts)
