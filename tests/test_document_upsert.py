"""Tests for document-level shard upsert."""

import sqlite3
from pathlib import Path

from scip_cli.indexing.document_upsert import remove_documents_by_paths, upsert_shard_documents

SCHEMA = """
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE
);
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    occurrences BLOB NOT NULL DEFAULT X''
);
CREATE TABLE global_symbols (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    display_name TEXT,
    kind INTEGER
);
CREATE TABLE mentions (
    chunk_id INTEGER NOT NULL,
    symbol_id INTEGER NOT NULL,
    role INTEGER NOT NULL,
    PRIMARY KEY (chunk_id, symbol_id, role)
);
CREATE TABLE defn_enclosing_ranges (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    symbol_id INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    start_char INTEGER NOT NULL DEFAULT 0,
    end_line INTEGER NOT NULL,
    end_char INTEGER NOT NULL DEFAULT 0
);
"""


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute("INSERT INTO documents (id, relative_path) VALUES (1, 'pkg/a.ts')")
    conn.execute("INSERT INTO documents (id, relative_path) VALUES (2, 'pkg/b.ts')")
    conn.execute("INSERT INTO chunks (id, document_id, chunk_index, start_line, end_line) VALUES (1, 1, 0, 0, 5)")
    conn.execute("INSERT INTO chunks (id, document_id, chunk_index, start_line, end_line) VALUES (2, 2, 0, 0, 5)")
    conn.execute("INSERT INTO global_symbols (id, symbol, display_name) VALUES (1, 'sym/a', 'a')")
    conn.execute("INSERT INTO global_symbols (id, symbol, display_name) VALUES (2, 'sym/b', 'b')")
    conn.execute(
        "INSERT INTO defn_enclosing_ranges (id, document_id, symbol_id, start_line, end_line) VALUES (1, 1, 1, 0, 5)"
    )
    conn.execute(
        "INSERT INTO defn_enclosing_ranges (id, document_id, symbol_id, start_line, end_line) VALUES (2, 2, 2, 0, 5)"
    )
    conn.execute("INSERT INTO mentions (chunk_id, symbol_id, role) VALUES (1, 1, 1)")
    conn.execute("INSERT INTO mentions (chunk_id, symbol_id, role) VALUES (2, 2, 1)")
    conn.commit()
    conn.close()


class TestDocumentUpsert:
    def test_remove_documents_by_paths(self, tmp_path):
        db = tmp_path / "shard.db"
        _seed_db(db)
        remove_documents_by_paths(db, frozenset({"pkg/a.ts"}))

        conn = sqlite3.connect(db)
        paths = {row[0] for row in conn.execute("SELECT relative_path FROM documents")}
        symbols = {row[0] for row in conn.execute("SELECT symbol FROM global_symbols")}
        conn.close()

        assert paths == {"pkg/b.ts"}
        assert symbols == {"sym/b"}

    def test_upsert_shard_documents_replaces_one_file(self, tmp_path):
        shard = tmp_path / "shard.db"
        part = tmp_path / "part.db"
        _seed_db(shard)
        _seed_db(part)

        conn = sqlite3.connect(part)
        conn.execute("UPDATE global_symbols SET symbol = 'sym/a-new', display_name = 'a-new' WHERE id = 1")
        conn.commit()
        conn.close()

        upsert_shard_documents(shard, part, frozenset({"pkg/a.ts"}))

        conn = sqlite3.connect(shard)
        paths = sorted(row[0] for row in conn.execute("SELECT relative_path FROM documents"))
        symbols = sorted(row[0] for row in conn.execute("SELECT symbol FROM global_symbols"))
        conn.close()

        assert paths == ["pkg/a.ts", "pkg/b.ts"]
        assert symbols == ["sym/a-new", "sym/b"]
