"""Project-wide analyze checks — SQL only."""

from __future__ import annotations

import re

from ..paths import path_filter_sql, path_filter_sql_any, path_in_scope
from ..symbols import is_module_symbol
from .common import (
    DEFAULT_LIMIT,
    SYM_DEF_JOIN,
    analyze_noise,
    collect_from_producer,
    collect_until_limit,
    cycle_path_noise,
    fetch_all,
    file_pair_noise,
    is_dynamic_loader_path,
    is_test_path,
    short_name,
    stale_type_noise,
)
from .graph import FILE_EDGES_SQL, fetch_file_edges, find_longer_cycles
from .live import (
    LiveIndex,
    file_has_scip_importers,
    has_same_file_reference_usage,
    has_same_file_usage_mention,
    is_low_signal_dead_file,
    live_for,
)
from .sections import Check, Priority, run_checks


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
    sql = f"""
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
               sym_def.end_line - sym_def.start_line + 1 AS loc,
               fi.fan_in * fo.fan_out AS score
        FROM global_symbols gs
        {SYM_DEF_JOIN}
        JOIN fan_in fi ON fi.symbol_id = gs.id
        JOIN fan_out fo ON fo.symbol_id = gs.id
        WHERE fi.fan_in >= 1 AND fo.fan_out >= 1{scope_clause}
        ORDER BY score DESC, fi.fan_in DESC
    """

    def fetch_page(page_size: int, offset: int):
        return fetch_all(db, sql + " LIMIT ? OFFSET ?", (*scope_params, page_size, offset))

    def accept(row):
        symbol, path, fan_in, fan_out, loc, score = row
        if analyze_noise(path, symbol, include_tests=include_tests) or is_module_symbol(symbol):
            return None
        return f"{short_name(symbol)}  score={score}  loc={loc}  fan_in={fan_in}  fan_out={fan_out}  ({path})"

    return collect_until_limit(limit, fetch_page, accept)


def hotspots(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    sql = f"""
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
    """

    def fetch_page(page_size: int, offset: int):
        return fetch_all(db, sql + " LIMIT ? OFFSET ?", (*scope_params, page_size, offset))

    def accept(row):
        symbol, path, ref_count, file_count = row
        if analyze_noise(path, symbol, include_tests=include_tests) or is_module_symbol(symbol):
            return None
        return f"{short_name(symbol)}  refs={ref_count}  files={file_count}  ({path})"

    return collect_until_limit(limit, fetch_page, accept)


def _accept_cycle_line(line: str, *, include_tests: bool, scope: str | None) -> str | None:
    if cycle_path_noise(line, include_tests=include_tests):
        return None
    if scope and not _cycle_touches_scope(line, scope):
        return None
    return line


def cycles(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    sql = f"""
        WITH edges AS ({FILE_EDGES_SQL})
        SELECT e1.from_file || ' <-> ' || e1.to_file
        FROM edges e1
        JOIN edges e2 ON e1.from_file = e2.to_file AND e1.to_file = e2.from_file
        WHERE e1.from_file < e1.to_file
        ORDER BY 1
    """

    def fetch_page(page_size: int, offset: int):
        return fetch_all(db, sql + " LIMIT ? OFFSET ?", (page_size, offset))

    def accept_row(row):
        return _accept_cycle_line(row[0], include_tests=include_tests, scope=scope)

    lines = collect_until_limit(limit, fetch_page, accept_row)
    if len(lines) >= limit:
        return lines

    edges = fetch_file_edges(db)

    def accept_path(path: str) -> str | None:
        return _accept_cycle_line(path, include_tests=include_tests, scope=scope)

    def produce(cap: int) -> list[str]:
        return find_longer_cycles(edges, max_depth=8, limit=cap)

    longer = collect_from_producer(
        limit - len(lines),
        produce,
        accept_path,
    )
    return lines + longer


def _dead_export_sql(scope_clause: str) -> str:
    return f"""
        SELECT gs.id, gs.symbol, def_d.relative_path,
               sym_def.end_line - sym_def.start_line + 1 AS loc,
               def_d.id
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
    """


def _unreferenced_sql(scope_clause: str) -> str:
    return f"""
        SELECT gs.id, gs.symbol, def_d.relative_path,
               sym_def.end_line - sym_def.start_line + 1 AS loc,
               def_d.id
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
    """


def _collect_dead_export_rows(
    db,
    sql: str,
    scope_params: tuple[object, ...],
    live: LiveIndex,
    *,
    include_tests: bool,
    limit: int,
) -> list[str]:
    def fetch_page(page_size: int, offset: int):
        return fetch_all(db, sql + " LIMIT ? OFFSET ?", (*scope_params, page_size, offset))

    def accept(row):
        symbol_id, symbol, path, loc, def_doc_id = row
        if analyze_noise(path, symbol, include_tests=include_tests):
            return None
        if has_same_file_reference_usage(db, symbol_id, def_doc_id):
            return None
        if has_same_file_usage_mention(db, symbol_id, def_doc_id):
            return None
        if live.dead_export_noise(symbol, def_doc_id):
            return None
        return f"{short_name(symbol)}  loc={loc}  ({path})"

    return collect_until_limit(limit, fetch_page, accept)


def stale_types(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    sql = f"""
        SELECT gs.id, gs.symbol, def_d.relative_path, def_d.id,
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
        HAVING consumers = 0
        ORDER BY consumers ASC, def_d.relative_path
    """
    live = live_for(db)

    def fetch_page(page_size: int, offset: int):
        return fetch_all(db, sql + " LIMIT ? OFFSET ?", (*scope_params, page_size, offset))

    def accept(row):
        sym_id, symbol, path, def_doc_id, consumers = row
        if analyze_noise(path, symbol, include_tests=include_tests):
            return None
        if stale_type_noise(path, symbol, consumers):
            return None
        if consumers == 0 and has_same_file_reference_usage(db, sym_id, def_doc_id):
            return None
        if live.stale_type_live_noise(symbol, def_doc_id):
            return None
        return f"{short_name(symbol)}  consumers={consumers}  ({path})"

    return collect_until_limit(limit, fetch_page, accept)


def unreferenced_symbols(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    return _collect_dead_export_rows(
        db,
        _unreferenced_sql(scope_clause),
        tuple(scope_params),
        live_for(db),
        include_tests=include_tests,
        limit=limit,
    )


def same_file_only(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    live = live_for(db)
    sql = f"""
        SELECT gs.symbol, def_d.relative_path,
               sym_def.end_line - sym_def.start_line + 1 AS loc,
               def_d.id
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
    """

    def fetch_page(page_size: int, offset: int):
        return fetch_all(db, sql + " LIMIT ? OFFSET ?", (*scope_params, page_size, offset))

    def accept(row):
        symbol, path, loc, def_doc_id = row
        if analyze_noise(path, symbol, include_tests=include_tests):
            return None
        if live.same_file_export_noise(symbol, def_doc_id):
            return None
        if not file_has_scip_importers(db, path, live=live, def_doc_id=def_doc_id):
            return None
        return f"{short_name(symbol)}  loc={loc}  ({path})"

    return collect_until_limit(limit, fetch_page, accept)


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
    sql = f"""
        SELECT gs.symbol, def_d.relative_path,
               GROUP_CONCAT(DISTINCT ref_d.relative_path) AS consumer_paths
        FROM global_symbols gs
        {SYM_DEF_JOIN}
        JOIN mentions m ON m.symbol_id = gs.id AND m.role != 1
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents ref_d ON c.document_id = ref_d.id
        WHERE ref_d.id != def_d.id{scope_clause}
          AND NOT EXISTS (
              SELECT 1 FROM mentions m2
              JOIN chunks c2 ON m2.chunk_id = c2.id
              WHERE m2.symbol_id = gs.id AND m2.role = 0 AND c2.document_id = def_d.id
          )
        GROUP BY gs.id
        HAVING COUNT(DISTINCT ref_d.id) > 0
        ORDER BY def_d.relative_path, gs.symbol
    """

    def fetch_page(page_size: int, offset: int):
        return fetch_all(db, sql + " LIMIT ? OFFSET ?", (*scope_params, page_size, offset))

    def accept(row):
        symbol, path, consumer_paths = row
        if analyze_noise(path, symbol, include_tests=include_tests):
            return None
        paths = [part.strip() for part in (consumer_paths or "").split(",") if part.strip()]
        if paths and all(is_test_path(p) for p in paths):
            return f"{short_name(symbol)}  test_consumers={len(paths)}  ({path})"
        return None

    return collect_until_limit(limit, fetch_page, accept)


def dead_exports(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    return _collect_dead_export_rows(
        db,
        _dead_export_sql(scope_clause),
        tuple(scope_params),
        live_for(db),
        include_tests=include_tests,
        limit=limit,
    )


def dead_files(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    """Files with no inbound mentions from other documents (empty rdeps)."""
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="d")
    sql = f"""
        SELECT d.relative_path, d.id
        FROM documents d
        WHERE NOT EXISTS (
            SELECT 1
            FROM defn_enclosing_ranges der
            JOIN mentions m ON m.symbol_id = der.symbol_id AND m.role != 1
            JOIN chunks c ON m.chunk_id = c.id
            WHERE der.document_id = d.id AND c.document_id != d.id
        ){scope_clause}
        ORDER BY d.relative_path
    """

    def fetch_page(page_size: int, offset: int):
        return fetch_all(db, sql + " LIMIT ? OFFSET ?", (*scope_params, page_size, offset))

    def accept(row):
        path, doc_id = row
        if not include_tests and is_test_path(path):
            return None
        if is_dynamic_loader_path(path):
            return None
        if is_low_signal_dead_file(db, doc_id):
            return None
        return path

    return collect_until_limit(limit, fetch_page, accept)


def top_coupling(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    scope_clause, scope_params = path_filter_sql_any(db, scope, "def_d", "ref_d")
    sql = f"""
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
    """

    def fetch_page(page_size: int, offset: int):
        return fetch_all(db, sql + " LIMIT ? OFFSET ?", (*scope_params, page_size, offset))

    def accept(row):
        file1, file2, shared = row
        if file_pair_noise(file1, file2, include_tests=include_tests):
            return None
        return f"{file1}  <->  {file2}  shared={shared}"

    return collect_until_limit(limit, fetch_page, accept)


def run_all(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
    priorities=None,
    budget=None,
    check_keys=None,
    per_check_limit=None,
) -> list[tuple[str, list[str], str | None]]:
    suffix = _scope_suffix(scope)
    checks = [
        Check("cycles", Priority.HIGH, f"Cycles (file dependencies){suffix}", cycles),
        Check("unreferenced", Priority.HIGH, f"Unreferenced symbols (no refs){suffix}", unreferenced_symbols),
        Check(
            "dead_exports",
            Priority.HIGH,
            f"Dead exports (no in-file or external use){suffix}",
            dead_exports,
        ),
        Check("dead_files", Priority.HIGH, f"Dead files (no importers){suffix}", dead_files),
        Check("stale_types", Priority.HIGH, f"Stale types (no external consumers){suffix}", stale_types),
        Check("same_file_only", Priority.MEDIUM, f"Same-file only (in-file use, not exported){suffix}", same_file_only),
        Check(
            "test_only",
            Priority.LOW,
            f"Test-only consumers (index may miss same-file calls){suffix}",
            symbols_test_only_consumers,
        ),
        Check("top_coupling", Priority.LOW, f"Top coupling (file pairs){suffix}", top_coupling),
        Check("bottlenecks", Priority.LOW, f"Bottlenecks (fan-in x fan-out){suffix}", bottlenecks),
        Check("hotspots", Priority.LOW, f"Hotspots (most referenced){suffix}", hotspots),
    ]
    return run_checks(
        checks,
        db,
        limit,
        priorities,
        include_tests=include_tests,
        scope=scope,
        budget=budget,
        check_keys=check_keys,
        per_check_limit=per_check_limit,
    )
