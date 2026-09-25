"""Replace selected documents in a shard DB from a fresh partial index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..merge import merge_attached_for_paths
from ..sql import configure_bulk_write_connection
from .performance import phase
from .postprocess import recreate_index_indexes


def document_paths_in_db(db_path: Path) -> frozenset[str]:
    """All repo-relative document paths stored in a part or live index DB."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT relative_path FROM documents").fetchall()
    finally:
        conn.close()
    return frozenset(row[0] for row in rows)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def remove_documents_by_paths(db_path: Path, relative_paths: frozenset[str]) -> None:
    """Drop documents and cascade rows for the given repo-relative paths."""
    if not relative_paths:
        return

    with phase("upsert_delete"):
        conn = sqlite3.connect(db_path)
        try:
            configure_bulk_write_connection(conn)
            placeholders = ",".join("?" * len(relative_paths))
            doc_ids = [
                row[0]
                for row in conn.execute(
                    f"SELECT id FROM documents WHERE relative_path IN ({placeholders})",
                    tuple(relative_paths),
                )
            ]
            if not doc_ids:
                return

            id_placeholders = ",".join("?" * len(doc_ids))
            id_params = tuple(doc_ids)

            if _table_exists(conn, "mentions") and _table_exists(conn, "chunks"):
                conn.execute(
                    "DELETE FROM mentions WHERE chunk_id IN "
                    + f"(SELECT id FROM chunks WHERE document_id IN ({id_placeholders}))",
                    id_params,
                )
            if _table_exists(conn, "defn_enclosing_ranges"):
                conn.execute(
                    f"DELETE FROM defn_enclosing_ranges WHERE document_id IN ({id_placeholders})",
                    id_params,
                )
            if _table_exists(conn, "chunks"):
                conn.execute(f"DELETE FROM chunks WHERE document_id IN ({id_placeholders})", id_params)
            conn.execute(f"DELETE FROM documents WHERE id IN ({id_placeholders})", id_params)

            if _table_exists(conn, "global_symbols"):
                conn.execute("""
                    DELETE FROM global_symbols
                    WHERE id NOT IN (
                        SELECT symbol_id FROM mentions
                        UNION
                        SELECT symbol_id FROM defn_enclosing_ranges
                    )
                """)

            recreate_index_indexes(conn)
            conn.commit()
        finally:
            conn.close()


def upsert_shard_documents(
    shard_db: Path,
    part_db: Path,
    relative_paths: frozenset[str],
) -> None:
    """Replace rows for relative_paths in shard_db with data from part_db."""
    if not relative_paths:
        return

    shard_db = Path(shard_db)
    part_db = Path(part_db)
    if not shard_db.is_file():
        raise FileNotFoundError(shard_db)
    if not part_db.is_file():
        raise FileNotFoundError(part_db)

    remove_documents_by_paths(shard_db, relative_paths)

    with phase("upsert_merge"):
        conn = sqlite3.connect(shard_db)
        try:
            configure_bulk_write_connection(conn)
            conn.execute("ATTACH DATABASE ? AS part", (str(part_db),))
            try:
                merge_attached_for_paths(conn, "part", relative_paths)
            finally:
                conn.execute("DETACH DATABASE part")
            recreate_index_indexes(conn)
            conn.commit()
        finally:
            conn.close()
