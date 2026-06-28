"""Per-symbol analyze checks — SQL only."""

from __future__ import annotations

from ..symbols import infer_kind
from .common import DEFAULT_LIMIT, fetch_all, fetch_one, short_name
from .sections import Check, Priority, run_checks


def _bind_symbol(fn, symbol_id: int):
    def run(db, limit: int, **_kwargs):
        return fn(db, symbol_id, limit)

    return run


def _bind_symbol0(fn, symbol_id: int):
    def run(db, _limit: int, **_kwargs):
        return fn(db, symbol_id)

    return run


def affected(db, symbol_id: int, limit: int = DEFAULT_LIMIT) -> list[str]:
    rows = fetch_all(
        db,
        """
        WITH RECURSIVE propagation(symbol_id, depth) AS (
            SELECT ?, 0
            UNION ALL
            SELECT der.symbol_id, p.depth + 1
            FROM propagation p
            JOIN mentions m ON m.symbol_id = p.symbol_id AND m.role != 1
            JOIN chunks c ON m.chunk_id = c.id
            JOIN documents consumer_doc ON c.document_id = consumer_doc.id
            JOIN defn_enclosing_ranges der ON der.document_id = consumer_doc.id
            WHERE p.depth < 5 AND der.symbol_id != p.symbol_id
        )
        SELECT DISTINCT gs.symbol, def_d.relative_path, p.depth
        FROM propagation p
        JOIN global_symbols gs ON gs.id = p.symbol_id
        JOIN defn_enclosing_ranges der ON der.symbol_id = gs.id
        JOIN documents def_d ON der.document_id = def_d.id
        WHERE p.depth > 0
        ORDER BY p.depth, def_d.relative_path, gs.symbol
        LIMIT ?
        """,
        (symbol_id, limit),
    )
    return [f"depth={depth}  {short_name(symbol)}  ({path})" for symbol, path, depth in rows]


def consumer_files(db, symbol_id: int, limit: int = DEFAULT_LIMIT) -> list[str]:
    rows = fetch_all(
        db,
        """
        SELECT ref_d.relative_path, COUNT(*) AS ref_count
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents ref_d ON c.document_id = ref_d.id
        JOIN defn_enclosing_ranges der ON m.symbol_id = der.symbol_id
        JOIN documents def_d ON der.document_id = def_d.id
        WHERE m.symbol_id = ? AND m.role != 1 AND ref_d.id != def_d.id
        GROUP BY ref_d.id
        ORDER BY ref_count DESC, ref_d.relative_path
        LIMIT ?
        """,
        (symbol_id, limit),
    )
    return [f"{path}  refs={count}" for path, count in rows]


def symbol_pressure(db, symbol_id: int) -> list[str]:
    row = fetch_one(
        db,
        """
        WITH target AS (
            SELECT gs.id, gs.symbol, der.document_id, der.start_line, der.end_line
            FROM global_symbols gs
            JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
            WHERE gs.id = ?
        ),
        fan_in AS (
            SELECT COUNT(DISTINCT ref_d.id) AS n
            FROM mentions m
            JOIN chunks c ON m.chunk_id = c.id
            JOIN documents ref_d ON c.document_id = ref_d.id
            JOIN target t ON m.symbol_id = t.id
            WHERE m.role != 1 AND ref_d.id != t.document_id
        ),
        fan_out AS (
            SELECT COUNT(DISTINCT m.symbol_id) AS n
            FROM target t
            JOIN chunks c ON c.document_id = t.document_id
            JOIN mentions m ON m.chunk_id = c.id AND m.role NOT IN (1, 2)
            JOIN defn_enclosing_ranges callee ON m.symbol_id = callee.symbol_id
            WHERE callee.document_id != t.document_id
        )
        SELECT t.symbol, t.end_line - t.start_line + 1, fan_in.n, fan_out.n
        FROM target t, fan_in, fan_out
        """,
        (symbol_id,),
    )
    if not row:
        return ["(symbol not found)"]
    symbol, loc, fan_in, fan_out = row
    return [
        f"{short_name(symbol)}  loc={loc}  fan_in={fan_in}  fan_out={fan_out}  pressure={fan_in * fan_out}",
    ]


def dependencies(db, symbol_id: int, limit: int = DEFAULT_LIMIT) -> list[str]:
    rows = fetch_all(
        db,
        """
        SELECT DISTINCT gs.symbol, callee_d.relative_path
        FROM global_symbols target_gs
        JOIN defn_enclosing_ranges target_der ON target_gs.id = target_der.symbol_id
        JOIN chunks c ON c.document_id = target_der.document_id
        JOIN mentions m ON m.chunk_id = c.id AND m.role NOT IN (1, 2)
        JOIN global_symbols gs ON m.symbol_id = gs.id
        JOIN defn_enclosing_ranges callee_def ON callee_def.symbol_id = gs.id
        JOIN documents callee_d ON callee_def.document_id = callee_d.id
        WHERE target_gs.id = ? AND callee_d.id != target_der.document_id
        ORDER BY callee_d.relative_path, gs.symbol
        LIMIT ?
        """,
        (symbol_id, limit),
    )
    return [f"{short_name(symbol)}  ({path})" for symbol, path in rows]


def def_context(db, symbol_id: int) -> list[str]:
    row = fetch_one(
        db,
        """
        SELECT gs.symbol, gs.display_name, def_d.relative_path,
               der.start_line, der.end_line
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents def_d ON der.document_id = def_d.id
        WHERE gs.id = ?
        """,
        (symbol_id,),
    )
    if not row:
        return ["(symbol not found)"]
    symbol, display_name, path, start, end = row
    kind = infer_kind(symbol).value
    members = fetch_one(
        db,
        """
        SELECT COUNT(*) FROM global_symbols gs
        WHERE gs.symbol LIKE ? AND gs.symbol != ?
        """,
        (f"{symbol}%", symbol),
    )
    member_count = members[0] if members else 0
    return [
        f"name={short_name(symbol)}  kind={kind}",
        f"file={path}  lines={start + 1}:{end + 1}",
        f"display_name={display_name or '-'}  members≈{member_count}",
    ]


def run_all(
    db,
    symbol_id: int,
    limit: int = DEFAULT_LIMIT,
    priorities=None,
    budget=None,
) -> list[tuple[str, list[str], str | None]]:
    checks = [
        Check("consumer_files", Priority.HIGH, "Consumer files (direct)", _bind_symbol(consumer_files, symbol_id)),
        Check("dependencies", Priority.HIGH, "Dependencies (cross-file)", _bind_symbol(dependencies, symbol_id)),
        Check("affected", Priority.LOW, "Affected (transitive, coarse)", _bind_symbol(affected, symbol_id)),
        Check(
            "symbol_pressure",
            Priority.LOW,
            "Symbol pressure (loc x fan metrics)",
            _bind_symbol0(symbol_pressure, symbol_id),
        ),
        Check("def_context", Priority.LOW, "Definition context", _bind_symbol0(def_context, symbol_id)),
    ]
    return run_checks(checks, db, limit, priorities, budget=budget)
