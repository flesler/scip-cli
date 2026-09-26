"""SQLite helpers shared across query modules."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from pathlib import Path

logger = logging.getLogger(__name__)


def debug_execute(db: sqlite3.Connection, sql: str, params: Sequence[object] = ()) -> sqlite3.Cursor:
    """Execute SQL with optional debug logging."""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("SQL: %s | params: %s", sql.strip()[:200], params)
    return db.execute(sql, params)


def escape_like(s: str) -> str:
    """Escape SQL LIKE special characters in a string."""
    return s.replace("%", "\\%").replace("_", "\\_")


def configure_read_connection(db: sqlite3.Connection) -> None:
    """Tune SQLite for read-heavy CLI queries."""
    db.execute("PRAGMA query_only = ON")
    db.execute("PRAGMA temp_store = MEMORY")
    db.execute("PRAGMA cache_size = -64000")
    db.execute("PRAGMA mmap_size = 268435456")


def configure_write_connection(db: sqlite3.Connection) -> None:
    """Tune SQLite for interactive read-write CLI (query --write)."""
    db.execute("PRAGMA temp_store = MEMORY")
    db.execute("PRAGMA cache_size = -64000")
    db.execute("PRAGMA mmap_size = 268435456")


def configure_bulk_write_connection(db: sqlite3.Connection) -> None:
    """Tune SQLite for single-writer bulk rebuilds (postprocess, merge)."""
    db.executescript("""
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        PRAGMA temp_store = MEMORY;
        PRAGMA cache_size = -64000;
        PRAGMA mmap_size = 268435456;
    """)


def _unlink_sqlite_sidecars(db_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.is_file():
            sidecar.unlink()


def finalize_index_db(db_path: Path) -> None:
    """Checkpoint WAL pages and compact the index file after indexing."""
    db_path = Path(db_path)
    if not db_path.is_file():
        return
    if db_path.read_bytes()[:15] != b"SQLite format 3":
        return

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
    finally:
        conn.close()

    _unlink_sqlite_sidecars(db_path)
