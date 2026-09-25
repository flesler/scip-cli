"""SQLite helper tests."""

import sqlite3
from pathlib import Path

from scip_cli.sql import finalize_index_db


def test_finalize_index_db_compacts_and_clears_sidecars(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t(x)")
    conn.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(1000)])
    conn.execute("DROP TABLE t")
    conn.commit()
    assert conn.execute("PRAGMA freelist_count").fetchone()[0] > 0
    conn.close()

    wal = Path(f"{db_path}-wal")
    wal.write_bytes(b"fake")
    before = db_path.stat().st_size

    finalize_index_db(db_path)

    after = db_path.stat().st_size
    assert after < before
    assert not wal.is_file()
    conn = sqlite3.connect(db_path)
    assert conn.execute("PRAGMA freelist_count").fetchone()[0] == 0
    conn.close()
