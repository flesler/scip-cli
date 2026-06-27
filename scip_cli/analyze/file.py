"""Per-file analyze checks — SQL only."""

from __future__ import annotations

from .common import DEFAULT_LIMIT, SYM_DEF_JOIN, analyze_noise, fetch_all, section, short_name


def change_surface(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    rows = fetch_all(
        db,
        """
        SELECT gs.symbol, der.start_line, der.end_line,
               COUNT(DISTINCT CASE WHEN ref_d.id != def_d.id THEN ref_d.id END) AS consumers
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents def_d ON der.document_id = def_d.id
        LEFT JOIN mentions m ON m.symbol_id = gs.id AND m.role != 1
        LEFT JOIN chunks c ON m.chunk_id = c.id
        LEFT JOIN documents ref_d ON c.document_id = ref_d.id
        WHERE def_d.relative_path = ?
        GROUP BY gs.id
        ORDER BY consumers DESC, der.start_line
        LIMIT ?
        """,
        (relative_path, limit),
    )
    lines = []
    for symbol, start, end, consumers in rows:
        risk = "high" if consumers > 10 else "medium" if consumers > 0 else "low"
        lines.append(f"{short_name(symbol)}  {start + 1}:{end + 1}  consumers={consumers}  risk={risk}")
    return lines


def unused_imports(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    rows = fetch_all(
        db,
        """
        SELECT gs.symbol
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents imp_d ON c.document_id = imp_d.id
        JOIN global_symbols gs ON m.symbol_id = gs.id
        WHERE imp_d.relative_path = ?
          AND m.role = 2
          AND NOT EXISTS (
              SELECT 1
              FROM mentions ref_m
              JOIN chunks ref_c ON ref_m.chunk_id = ref_c.id
              WHERE ref_m.symbol_id = gs.id
                AND ref_m.role NOT IN (1, 2)
                AND ref_c.document_id = imp_d.id
          )
        ORDER BY gs.symbol
        LIMIT ?
        """,
        (relative_path, limit),
    )
    return [short_name(row[0]) for row in rows]


def file_consumers(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    rows = fetch_all(
        db,
        """
        SELECT ref_d.relative_path, COUNT(DISTINCT gs.id) AS symbol_hits
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents def_d ON der.document_id = def_d.id
        JOIN mentions m ON m.symbol_id = gs.id AND m.role != 1
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents ref_d ON c.document_id = ref_d.id
        WHERE def_d.relative_path = ? AND ref_d.id != def_d.id
        GROUP BY ref_d.id
        ORDER BY symbol_hits DESC, ref_d.relative_path
        LIMIT ?
        """,
        (relative_path, limit),
    )
    return [f"{path}  symbols={hits}" for path, hits in rows]


def dead_in_file(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    rows = fetch_all(
        db,
        """
        SELECT gs.symbol, der.start_line, der.end_line
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents def_d ON der.document_id = def_d.id
        WHERE def_d.relative_path = ?
          AND NOT EXISTS (
              SELECT 1
              FROM mentions m
              JOIN chunks c ON m.chunk_id = c.id
              WHERE m.symbol_id = gs.id
                AND m.role != 1
                AND c.document_id != def_d.id
          )
        ORDER BY der.start_line
        LIMIT ?
        """,
        (relative_path, limit),
    )
    return [
        f"{short_name(symbol)}  {start + 1}:{end + 1}"
        for symbol, start, end in rows
        if not analyze_noise(relative_path, symbol, include_tests=True)
    ]


def imports_summary(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    count_row = fetch_all(
        db,
        """
        SELECT COUNT(DISTINCT m.symbol_id)
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents d ON c.document_id = d.id
        WHERE d.relative_path = ? AND m.role = 2
        """,
        (relative_path,),
    )
    total = count_row[0][0] if count_row else 0
    rows = fetch_all(
        db,
        """
        SELECT gs.symbol, def_d.relative_path AS from_file
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents imp_d ON c.document_id = imp_d.id
        JOIN global_symbols gs ON m.symbol_id = gs.id
        LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        LEFT JOIN documents def_d ON der.document_id = def_d.id
        WHERE imp_d.relative_path = ? AND m.role = 2
        ORDER BY gs.symbol
        LIMIT ?
        """,
        (relative_path, limit),
    )
    lines = [f"total imports: {total}"]
    for symbol, from_file in rows:
        src = from_file or "(external)"
        lines.append(f"  {short_name(symbol)}  from {src}")
    return lines


def coupling_for(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    rows = fetch_all(
        db,
        f"""
        SELECT other_file, shared FROM (
            SELECT ref_d.relative_path AS other_file,
                   COUNT(DISTINCT gs.id) AS shared
            FROM mentions m
            JOIN chunks c ON m.chunk_id = c.id
            JOIN documents ref_d ON c.document_id = ref_d.id
            JOIN global_symbols gs ON m.symbol_id = gs.id
            {SYM_DEF_JOIN}
            WHERE m.role != 1 AND def_d.relative_path = ? AND ref_d.relative_path != ?
            GROUP BY ref_d.id
            UNION ALL
            SELECT def_d.relative_path AS other_file,
                   COUNT(DISTINCT gs.id) AS shared
            FROM mentions m
            JOIN chunks c ON m.chunk_id = c.id
            JOIN documents ref_d ON c.document_id = ref_d.id
            JOIN global_symbols gs ON m.symbol_id = gs.id
            {SYM_DEF_JOIN}
            WHERE m.role != 1 AND ref_d.relative_path = ? AND def_d.relative_path != ?
            GROUP BY def_d.id
        )
        ORDER BY shared DESC, other_file
        LIMIT ?
        """,
        (relative_path, relative_path, relative_path, relative_path, limit),
    )
    return [f"{other}  shared={shared}" for other, shared in rows]


def run_all(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[tuple[str, list[str]]]:
    return [
        section(f"Change surface ({relative_path})", change_surface(db, relative_path, limit)),
        section("Unused imports", unused_imports(db, relative_path, limit)),
        section("File consumers", file_consumers(db, relative_path, limit)),
        section("Dead exports in file", dead_in_file(db, relative_path, limit)),
        section("Imports summary", imports_summary(db, relative_path, limit)),
        section("Coupling partners", coupling_for(db, relative_path, limit)),
    ]
