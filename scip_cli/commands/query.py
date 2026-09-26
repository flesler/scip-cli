"""query command — run SQL against the project index database."""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Sequence

from ..session import setup
from ..sql import debug_execute


def _column_names(cursor) -> list[str]:
    if not cursor.description:
        return []
    return [col[0] for col in cursor.description]


def _emit_tsv(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    if columns:
        print("\t".join(columns))
    for row in rows:
        print("\t".join("" if value is None else str(value) for value in row))


def _emit_csv(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    writer = csv.writer(sys.stdout, lineterminator="\n")
    if columns:
        writer.writerow(columns)
    for row in rows:
        writer.writerow(row)


def _emit_json(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    payload = [dict(zip(columns, row, strict=True)) for row in rows]
    print(json.dumps(payload, ensure_ascii=False))


def emit_result(columns: Sequence[str], rows: Sequence[Sequence[object]], fmt: str) -> None:
    if fmt == "tsv":
        _emit_tsv(columns, rows)
    elif fmt == "csv":
        _emit_csv(columns, rows)
    elif fmt == "json":
        _emit_json(columns, rows)
    else:
        raise ValueError(f"unsupported format: {fmt}")


def main(args) -> None:
    sql = " ".join(args.sql).strip()
    if not sql:
        print("Error: SQL query required", file=sys.stderr)
        sys.exit(1)

    db, _project_root = setup(write=args.write)
    try:
        cursor = debug_execute(db, sql)
        if args.write:
            db.commit()
        columns = _column_names(cursor)
        rows = cursor.fetchall() if columns else []
        emit_result(columns, rows, args.format)
    finally:
        db.close()
