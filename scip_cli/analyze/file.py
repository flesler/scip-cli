"""Per-file analyze checks — SQL only."""

from __future__ import annotations

from .common import DEFAULT_LIMIT, SYM_DEF_JOIN, analyze_noise, fetch_all, short_name
from .live import LiveIndex, file_has_scip_importers, has_same_file_reference_usage
from .sections import Check, Priority, run_checks
from .symbol import symbol_pressure


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


def unreferenced_in_file(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    live = LiveIndex(db)
    rows = fetch_all(
        db,
        """
        SELECT gs.symbol, der.start_line, der.end_line, def_d.id
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents def_d ON der.document_id = def_d.id
        WHERE def_d.relative_path = ?
          AND NOT EXISTS (
              SELECT 1 FROM mentions m
              WHERE m.symbol_id = gs.id AND m.role = 0
          )
          AND NOT EXISTS (
              SELECT 1 FROM mentions m
              JOIN chunks c ON m.chunk_id = c.id
              WHERE m.symbol_id = gs.id AND m.role != 1 AND c.document_id != def_d.id
          )
        ORDER BY der.start_line
        LIMIT ?
        """,
        (relative_path, limit),
    )
    lines = []
    for symbol, start, end, def_doc_id in rows:
        if analyze_noise(relative_path, symbol, include_tests=True):
            continue
        if live.dead_export_noise(symbol, def_doc_id):
            continue
        lines.append(f"{short_name(symbol)}  {start + 1}:{end + 1}")
    return lines


def same_file_only_in_file(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    live = LiveIndex(db)
    rows = fetch_all(
        db,
        """
        SELECT gs.symbol, der.start_line, der.end_line, def_d.id
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents def_d ON der.document_id = def_d.id
        WHERE def_d.relative_path = ?
          AND EXISTS (
              SELECT 1 FROM mentions m
              JOIN chunks c ON m.chunk_id = c.id
              WHERE m.symbol_id = gs.id AND m.role = 0 AND c.document_id = def_d.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM mentions m
              JOIN chunks c ON m.chunk_id = c.id
              WHERE m.symbol_id = gs.id AND m.role = 0 AND c.document_id != def_d.id
          )
        ORDER BY der.start_line
        LIMIT ?
        """,
        (relative_path, limit),
    )
    lines = []
    for symbol, start, end, def_doc_id in rows:
        if analyze_noise(relative_path, symbol, include_tests=True):
            continue
        if live.same_file_export_noise(symbol, def_doc_id):
            continue
        if not file_has_scip_importers(db, relative_path, live=live, def_doc_id=def_doc_id):
            continue
        lines.append(f"{short_name(symbol)}  {start + 1}:{end + 1}")
    return lines


def dead_in_file(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    live = LiveIndex(db)
    rows = fetch_all(
        db,
        """
        SELECT gs.id, gs.symbol, der.start_line, der.end_line, def_d.id
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
    lines = []
    for sym_id, symbol, start, end, def_doc_id in rows:
        if analyze_noise(relative_path, symbol, include_tests=True):
            continue
        if has_same_file_reference_usage(db, sym_id, def_doc_id):
            continue
        if live.dead_export_noise(symbol, def_doc_id):
            continue
        lines.append(f"{short_name(symbol)}  {start + 1}:{end + 1}")
    return lines


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


def count_file_importers(db, relative_path: str) -> int:
    from ..queries import get_file_symbols, get_importer_paths

    symbols = get_file_symbols(db, relative_path)
    if not symbols:
        return 0
    symbol_ids = [row[0] for row in symbols]
    return len(get_importer_paths(db, symbol_ids, relative_path))


def top_symbol_pressure(db, relative_path: str, limit: int = DEFAULT_LIMIT) -> list[str]:
    """Pressure metrics for the most-consumed exports in a file."""
    cap = min(5, limit)
    rows = fetch_all(
        db,
        """
        SELECT gs.id,
               COUNT(DISTINCT CASE WHEN ref_d.id != def_d.id THEN ref_d.id END) AS consumers
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents def_d ON der.document_id = def_d.id
        LEFT JOIN mentions m ON m.symbol_id = gs.id AND m.role != 1
        LEFT JOIN chunks c ON m.chunk_id = c.id
        LEFT JOIN documents ref_d ON c.document_id = ref_d.id
        WHERE def_d.relative_path = ?
        GROUP BY gs.id
        HAVING consumers > 0
        ORDER BY consumers DESC, der.start_line
        LIMIT ?
        """,
        (relative_path, cap),
    )
    lines: list[str] = []
    for sym_id, consumers in rows:
        pressure = symbol_pressure(db, sym_id)
        if pressure and not pressure[0].startswith("("):
            lines.append(f"consumers={consumers}  {pressure[0]}")
    return lines


def _bind_path(fn, relative_path: str):
    def run(db, limit: int, **kwargs):
        return fn(db, relative_path, limit)

    return run


def _file_checks(relative_path: str, *, include_top_symbols: bool) -> list[Check]:
    title = f"({relative_path})"
    checks = [
        Check(
            "unreferenced",
            Priority.HIGH,
            f"Unreferenced in file {title}",
            _bind_path(unreferenced_in_file, relative_path),
        ),
        Check(
            "dead_in_file",
            Priority.HIGH,
            f"Dead exports in file {title}",
            _bind_path(dead_in_file, relative_path),
        ),
        Check("unused_imports", Priority.HIGH, f"Unused imports {title}", _bind_path(unused_imports, relative_path)),
        Check(
            "same_file_only",
            Priority.MEDIUM,
            f"Same-file only {title}",
            _bind_path(same_file_only_in_file, relative_path),
        ),
        Check("change_surface", Priority.MEDIUM, f"Change surface {title}", _bind_path(change_surface, relative_path)),
        Check("file_consumers", Priority.MEDIUM, f"File consumers {title}", _bind_path(file_consumers, relative_path)),
        Check("coupling", Priority.LOW, f"Coupling partners {title}", _bind_path(coupling_for, relative_path)),
        Check("imports_summary", Priority.LOW, f"Imports summary {title}", _bind_path(imports_summary, relative_path)),
    ]
    if include_top_symbols:
        checks.append(
            Check(
                "top_symbols",
                Priority.LOW,
                f"Top symbols (by external consumers) {title}",
                _bind_path(top_symbol_pressure, relative_path),
            )
        )
    return checks


def _run_file_checks(
    checks: list[Check],
    db,
    limit: int,
    priorities,
    *,
    budget=None,
) -> list[tuple[str, list[str], str | None]]:
    return run_checks(checks, db, limit, priorities, budget=budget)


def run_all(
    db,
    relative_path: str,
    limit: int = DEFAULT_LIMIT,
    priorities=None,
    budget=None,
) -> list[tuple[str, list[str], str | None]]:
    return _run_file_checks(
        _file_checks(relative_path, include_top_symbols=True),
        db,
        limit,
        priorities,
        budget=budget,
    )


def run_all_sections_only(
    db,
    relative_path: str,
    limit: int = DEFAULT_LIMIT,
    priorities=None,
    budget=None,
) -> list[tuple[str, list[str], str | None]]:
    """Per-file sections without top-symbols (directory batch)."""
    return _run_file_checks(
        _file_checks(relative_path, include_top_symbols=False),
        db,
        limit,
        priorities,
        budget=budget,
    )
