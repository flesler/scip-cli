"""In-memory SCIP-like database builder for analyze tests."""

from __future__ import annotations

import sqlite3

ANALYZE_SCHEMA = """
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE
);
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL
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


class AnalyzeDbBuilder:
    """Build a minimal index in :memory: for analyze query tests."""

    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(ANALYZE_SCHEMA)
        self._next_doc = 1
        self._next_chunk = 1
        self._next_sym = 1
        self._next_der = 1

    def finish(self) -> sqlite3.Connection:
        self.conn.commit()
        return self.conn

    def add_file(self, path: str) -> tuple[int, int]:
        """Add a file with one full-file chunk. Returns (doc_id, chunk_id)."""
        doc_id = self._next_doc
        self._next_doc += 1
        chunk_id = self._next_chunk
        self._next_chunk += 1
        self.conn.execute("INSERT INTO documents (id, relative_path) VALUES (?, ?)", (doc_id, path))
        self.conn.execute(
            "INSERT INTO chunks (id, document_id, start_line, end_line) VALUES (?, ?, 0, 200)",
            (chunk_id, doc_id),
        )
        return doc_id, chunk_id

    def define(self, path: str, name: str, *, start: int = 0, end: int = 10) -> int:
        """Define a symbol in a file (creates file if needed). Returns symbol_id."""
        doc_id, chunk_id = self._ensure_file(path)
        sym_id = self._next_sym
        self._next_sym += 1
        symbol = f"scip-typescript npm test 1.0 {path}/`{path.split('/')[-1]}`/{name}()."
        if name[0].isupper() and not name.endswith("()"):
            symbol = f"scip-typescript npm test 1.0 {path}/`{path.split('/')[-1]}`/{name}#"
        self.conn.execute(
            "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
            (sym_id, symbol, name),
        )
        der_id = self._next_der
        self._next_der += 1
        self.conn.execute(
            """
            INSERT INTO defn_enclosing_ranges
            (id, document_id, symbol_id, start_line, start_char, end_line, end_char)
            VALUES (?, ?, ?, ?, 0, ?, 0)
            """,
            (der_id, doc_id, sym_id, start, end),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 1)",
            (chunk_id, sym_id),
        )
        return sym_id

    def reference(self, from_path: str, to_sym_id: int) -> None:
        """Record a cross-file or same-file reference (role=0)."""
        _doc_id, chunk_id = self._ensure_file(from_path)
        self.conn.execute(
            "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 0)",
            (chunk_id, to_sym_id),
        )

    def import_symbol(self, into_path: str, sym_id: int) -> None:
        """Record an import (role=2)."""
        _doc_id, chunk_id = self._ensure_file(into_path)
        self.conn.execute(
            "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 2)",
            (chunk_id, sym_id),
        )

    def method(self, path: str, class_name: str, method_name: str, *, start: int = 0, end: int = 10) -> int:
        """Define a class method. Returns symbol_id."""
        doc_id, chunk_id = self._ensure_file(path)
        sym_id = self._next_sym
        self._next_sym += 1
        file_label = path.split("/")[-1]
        symbol = f"scip-typescript npm test 1.0 {path}/`{file_label}`/{class_name}#{method_name}()."
        self.conn.execute(
            "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
            (sym_id, symbol, method_name),
        )
        der_id = self._next_der
        self._next_der += 1
        self.conn.execute(
            """
            INSERT INTO defn_enclosing_ranges
            (id, document_id, symbol_id, start_line, start_char, end_line, end_char)
            VALUES (?, ?, ?, ?, 0, ?, 0)
            """,
            (der_id, doc_id, sym_id, start, end),
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 1)",
            (chunk_id, sym_id),
        )
        return sym_id

    def type_literal_field(
        self,
        path: str,
        parent_name: str,
        field_name: str,
        *,
        literal_index: int = 0,
    ) -> int:
        """Define a type-literal object field (e.g. Options.verbose). Returns symbol_id."""
        _doc_id, _chunk_id = self._ensure_file(path)
        sym_id = self._next_sym
        self._next_sym += 1
        file_label = path.split("/")[-1]
        symbol = (
            f"scip-typescript npm test 1.0 {path}/`{file_label}`/{parent_name}#typeLiteral{literal_index}:{field_name}."
        )
        self.conn.execute(
            "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
            (sym_id, symbol, field_name),
        )
        return sym_id

    def _ensure_file(self, path: str) -> tuple[int, int]:
        row = self.conn.execute("SELECT id FROM documents WHERE relative_path = ?", (path,)).fetchone()
        if row:
            doc_id = row[0]
            chunk_row = self.conn.execute(
                "SELECT id FROM chunks WHERE document_id = ? LIMIT 1",
                (doc_id,),
            ).fetchone()
            return doc_id, chunk_row[0]
        return self.add_file(path)


def mini_codebase_db() -> sqlite3.Connection:
    """Small graph: lib exports, consumer uses, cycle pair, unused import."""
    b = AnalyzeDbBuilder()
    foo = b.define("src/lib.ts", "foo")
    b.define("src/lib.ts", "Orphan")
    bar = b.define("src/lib.ts", "Bar")
    unused = b.define("src/dead.ts", "deadFn")
    b.define("src/consumer.ts", "message")
    b.reference("src/consumer.ts", foo)
    b.reference("src/consumer.ts", bar)
    b.import_symbol("src/consumer.ts", foo)
    b.import_symbol("src/importer.ts", unused)  # import only, never referenced

    sym_x = b.define("src/cycle/a.ts", "alpha")
    sym_y = b.define("src/cycle/b.ts", "beta")
    b.reference("src/cycle/a.ts", sym_y)
    b.reference("src/cycle/b.ts", sym_x)

    stale = b.define("src/types.ts", "StaleType")
    b.reference("src/only.ts", stale)

    return b.finish()
