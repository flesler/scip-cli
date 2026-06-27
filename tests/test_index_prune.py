"""Tests for index post-processing (column trim, variable omission)."""

import sqlite3

from scip_cli.indexing import _postprocess_index
from scip_cli.symbols import is_variable_symbol, sql_exclude_variable_symbols


def _seed_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            relative_path TEXT UNIQUE,
            language TEXT
        );
        CREATE TABLE global_symbols (
            id INTEGER PRIMARY KEY,
            symbol TEXT,
            display_name TEXT,
            kind INTEGER
        );
        CREATE TABLE defn_enclosing_ranges (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            symbol_id INTEGER,
            start_line INTEGER,
            start_char INTEGER,
            end_line INTEGER,
            end_char INTEGER
        );
        CREATE TABLE mentions (
            chunk_id INTEGER,
            symbol_id INTEGER,
            role INTEGER
        );
    """)
    conn.execute("INSERT INTO documents VALUES (1, 'src/a.ts', 'ts')")
    conn.execute(
        "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
        ("scip-typescript npm t 1.0 src/`a.ts`/greet().", "greet"),
    )
    conn.execute(
        "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
        ("scip-typescript npm t 1.0 src/`a.ts`/message.", "message"),
    )
    conn.execute(
        "INSERT INTO global_symbols (symbol, display_name) VALUES (?, ?)",
        ("scip-typescript npm t 1.0 src/`a.ts`/Options#typeLiteral0:verbose.", "verbose"),
    )
    conn.execute("INSERT INTO mentions VALUES (1, 2, 0)")
    conn.execute("INSERT INTO defn_enclosing_ranges VALUES (1, 1, 2, 0, 0, 0, 0)")
    conn.commit()
    conn.close()


class TestVariableSymbolDetection:
    def test_const_is_variable(self):
        sym = "scip-typescript npm t 1.0 src/`a.ts`/message."
        assert is_variable_symbol(sym)

    def test_type_literal_is_not_variable(self):
        sym = "scip-typescript npm t 1.0 src/`a.ts`/Options#typeLiteral0:verbose."
        assert not is_variable_symbol(sym)

    def test_function_is_not_variable(self):
        sym = "scip-typescript npm t 1.0 src/`a.ts`/greet()."
        assert not is_variable_symbol(sym)


class TestSqlExcludeVariableSymbols:
    def test_matches_python_helper(self):
        clause = sql_exclude_variable_symbols("symbol")
        for sym, expected in [
            ("scip-typescript npm t 1.0 src/`a.ts`/message.", 0),
            ("scip-typescript npm t 1.0 src/`a.ts`/greet().", 1),
        ]:
            conn = sqlite3.connect(":memory:")
            ok = conn.execute(f"SELECT {clause} FROM (SELECT ? AS symbol)", (sym,)).fetchone()[0]
            assert ok == expected


class TestOmitVariableSymbols:
    def test_postprocess_omits_variables_on_copy(self, tmp_path):
        db_path = tmp_path / "index.db"
        _seed_db(db_path)
        _postprocess_index(db_path)

        conn = sqlite3.connect(db_path)
        symbols = {row[0] for row in conn.execute("SELECT symbol FROM global_symbols").fetchall()}
        assert any("greet()." in s for s in symbols)
        assert any("typeLiteral0:verbose" in s for s in symbols)
        assert not any(s.endswith("/message.") for s in symbols)
        assert conn.execute("SELECT COUNT(*) FROM mentions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM defn_enclosing_ranges").fetchone()[0] == 0
        conn.close()


class TestIndexLogging:
    def test_format_db_size(self, tmp_path):
        from scip_cli.indexing import format_db_size

        tiny = tmp_path / "tiny.db"
        tiny.write_bytes(b"x" * 512)
        assert format_db_size(tiny) == "512 B"

        kb = tmp_path / "kb.db"
        kb.write_bytes(b"x" * 2048)
        assert format_db_size(kb) == "2.0 KB"

    def test_log_index_complete(self, tmp_path, capsys):
        from scip_cli.indexing import log_index_complete

        db = tmp_path / "index.db"
        db.write_bytes(b"x" * 1024)
        log_index_complete(db, "typescript", projects=3, skipped=1)
        err = capsys.readouterr().err
        assert "Indexed" in err
        assert "1.0 KB" in err
        assert "typescript" in err
        assert "3 tsconfigs" in err
        assert "1 skipped" in err
