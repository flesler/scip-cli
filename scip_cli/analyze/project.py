"""Project-wide analyze checks — SQL only."""

from __future__ import annotations

from .common import DEFAULT_LIMIT, SYM_DEF_JOIN, fetch_all, section, short_name

_FILE_EDGES_SQL = """
    SELECT DISTINCT d1.relative_path AS from_file, d2.relative_path AS to_file
    FROM mentions m
    JOIN chunks c ON m.chunk_id = c.id
    JOIN documents d1 ON c.document_id = d1.id
    JOIN defn_enclosing_ranges der ON m.symbol_id = der.symbol_id
    JOIN documents d2 ON der.document_id = d2.id
    WHERE d1.id != d2.id AND m.role != 1
"""


def bottlenecks(db, limit: int = DEFAULT_LIMIT) -> list[str]:
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
        WHERE fi.fan_in >= 1 AND fo.fan_out >= 1
        ORDER BY score DESC, fi.fan_in DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [
        f"{short_name(symbol)}  score={score}  fan_in={fan_in}  fan_out={fan_out}  ({path})"
        for symbol, path, fan_in, fan_out, score in rows
    ]


def hotspots(db, limit: int = DEFAULT_LIMIT) -> list[str]:
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
        WHERE m.role != 1
        GROUP BY gs.id
        ORDER BY ref_count DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [
        f"{short_name(symbol)}  refs={ref_count}  files={file_count}  ({path})"
        for symbol, path, ref_count, file_count in rows
    ]


def cycles(db, limit: int = DEFAULT_LIMIT) -> list[str]:
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
        (limit,),
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
        (limit,),
    )
    lines = [row[0] for row in two_way]
    for row in rows:
        path = row[0]
        if path not in lines:
            lines.append(path)
    return lines[:limit]


def stale_types(db, limit: int = DEFAULT_LIMIT) -> list[str]:
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
          AND gs.symbol NOT LIKE '%#typeLiteral%'
        GROUP BY gs.id
        HAVING consumers <= 1
        ORDER BY consumers ASC, def_d.relative_path
        LIMIT ?
        """,
        (limit,),
    )
    return [f"{short_name(symbol)}  consumers={consumers}  ({path})" for symbol, path, consumers in rows]


def dead_exports(db, limit: int = DEFAULT_LIMIT) -> list[str]:
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
        )
        ORDER BY loc DESC, def_d.relative_path
        LIMIT ?
        """,
        (limit,),
    )
    return [f"{short_name(symbol)}  loc={loc}  ({path})" for symbol, path, loc in rows]


def top_coupling(db, limit: int = DEFAULT_LIMIT) -> list[str]:
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
        WHERE m.role != 1 AND def_d.id != ref_d.id
        GROUP BY def_d.id, ref_d.id
        ORDER BY shared DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [f"{file1}  <->  {file2}  shared={shared}" for file1, file2, shared in rows]


def run_all(db, limit: int = DEFAULT_LIMIT) -> list[tuple[str, list[str]]]:
    return [
        section("Bottlenecks (fan-in x fan-out)", bottlenecks(db, limit)),
        section("Hotspots (most referenced)", hotspots(db, limit)),
        section("Cycles (file dependencies)", cycles(db, limit)),
        section("Stale types (≤1 external consumer)", stale_types(db, limit)),
        section("Dead exports (no external refs)", dead_exports(db, limit)),
        section("Top coupling (file pairs)", top_coupling(db, limit)),
    ]
