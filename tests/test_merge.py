"""Tests for SQLite index merging."""

import sqlite3
from pathlib import Path

import pytest

from scip_cli.merge import merge_sqlite_indexes

SCHEMA = """
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE
);
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    occurrences BLOB NOT NULL
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
    start_char INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    end_char INTEGER NOT NULL
);
"""


def _make_db(path: Path, relative_path: str, symbol: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO documents (relative_path) VALUES (?)",
        (relative_path,),
    )
    conn.execute(
        "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
        (symbol, symbol.rsplit("/", 1)[-1]),
    )
    conn.execute(
        """
        INSERT INTO chunks (document_id, chunk_index, start_line, end_line, occurrences)
        VALUES (1, 0, 0, 0, X'00')
        """
    )
    conn.execute("INSERT INTO mentions (chunk_id, symbol_id, role) VALUES (1, 1, 0)")
    conn.execute(
        """
        INSERT INTO defn_enclosing_ranges (
            document_id, symbol_id, start_line, start_char, end_line, end_char
        ) VALUES (1, 1, 0, 0, 1, 0)
        """
    )
    conn.commit()
    conn.close()


class TestMergeSqliteIndexes:
    def test_merge_two_indexes(self, tmp_path):
        first = tmp_path / "first.db"
        second = tmp_path / "second.db"
        output = tmp_path / "merged.db"
        _make_db(first, "src/a.ts", "scheme a/symA().")
        _make_db(second, "src/b.ts", "scheme b/symB().")

        merge_sqlite_indexes([first, second], output)

        conn = sqlite3.connect(output)
        docs = conn.execute("SELECT relative_path FROM documents ORDER BY 1").fetchall()
        symbols = conn.execute("SELECT COUNT(*) FROM global_symbols").fetchone()[0]
        conn.close()

        assert docs == [("src/a.ts",), ("src/b.ts",)]
        assert symbols == 2

    def test_merge_reuses_duplicate_symbols(self, tmp_path):
        first = tmp_path / "first.db"
        second = tmp_path / "second.db"
        output = tmp_path / "merged.db"
        shared = "scheme shared/sym()."
        _make_db(first, "src/a.ts", shared)
        _make_db(second, "src/b.ts", shared)

        merge_sqlite_indexes([first, second], output)

        conn = sqlite3.connect(output)
        symbol_count = conn.execute("SELECT COUNT(*) FROM global_symbols").fetchone()[0]
        conn.close()
        assert symbol_count == 1

    def test_merge_reuses_duplicate_chunks(self, tmp_path):
        first = tmp_path / "first.db"
        second = tmp_path / "second.db"
        output = tmp_path / "merged.db"
        shared = "scheme shared/sym()."
        _make_db(first, "src/shared.ts", shared)
        _make_db(second, "src/shared.ts", shared)

        merge_sqlite_indexes([first, second], output)

        conn = sqlite3.connect(output)
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        conn.close()
        assert chunk_count == 1

    def test_merge_preserves_mentions_on_duplicate_chunks(self, tmp_path):
        first = tmp_path / "first.db"
        second = tmp_path / "second.db"
        output = tmp_path / "merged.db"

        conn = sqlite3.connect(first)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO documents (relative_path) VALUES (?)",
            ("src/shared.ts",),
        )
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            ("scheme a/symA().", "symA"),
        )
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            ("scheme a/symB().", "symB"),
        )
        conn.execute(
            """
            INSERT INTO chunks (document_id, chunk_index, start_line, end_line, occurrences)
            VALUES (1, 0, 0, 0, X'00')
            """
        )
        conn.execute("INSERT INTO mentions (chunk_id, symbol_id, role) VALUES (1, 1, 0)")
        conn.commit()
        conn.close()

        conn = sqlite3.connect(second)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO documents (relative_path) VALUES (?)",
            ("src/shared.ts",),
        )
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            ("scheme b/symB().", "symB"),
        )
        conn.execute(
            "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
            ("scheme b/symC().", "symC"),
        )
        conn.execute(
            """
            INSERT INTO chunks (document_id, chunk_index, start_line, end_line, occurrences)
            VALUES (1, 0, 0, 0, X'00')
            """
        )
        conn.execute("INSERT INTO mentions (chunk_id, symbol_id, role) VALUES (1, 2, 0)")
        conn.commit()
        conn.close()

        merge_sqlite_indexes([first, second], output)

        conn = sqlite3.connect(output)
        mention_count = conn.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
        symbols = {
            row[0]
            for row in conn.execute(
                """
                SELECT gs.symbol FROM mentions m
                JOIN global_symbols gs ON m.symbol_id = gs.id
                """
            )
        }
        conn.close()

        assert mention_count == 2
        assert "scheme a/symA()." in symbols
        assert "scheme b/symC()." in symbols

    def test_merge_requires_inputs(self):
        with pytest.raises(ValueError, match="at least one input"):
            merge_sqlite_indexes([], Path("out.db"))
