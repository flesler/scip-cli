"""Tests for pipe-friendly CLI output flags."""
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scip_cli.commands import members, refs, search


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE global_symbols (
            id INTEGER PRIMARY KEY,
            symbol TEXT,
            display_name TEXT,
            enclosing_symbol TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            relative_path TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE defn_enclosing_ranges (
            symbol_id INTEGER,
            document_id INTEGER,
            start_line INTEGER,
            end_line INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE mentions (
            symbol_id INTEGER,
            chunk_id INTEGER,
            role INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE chunks (
            id INTEGER PRIMARY KEY,
            document_id INTEGER,
            start_line INTEGER,
            end_line INTEGER
        )
        """
    )
    conn.execute("INSERT INTO documents (relative_path) VALUES ('pkg/a.ts')")
    conn.execute("INSERT INTO documents (relative_path) VALUES ('pkg/b.ts')")
    conn.execute(
        "INSERT INTO global_symbols (symbol) VALUES (?)",
        ("scip-typescript npm app 1.0 pkg/`a.ts`/foo().",),
    )
    conn.execute(
        "INSERT INTO global_symbols (symbol) VALUES (?)",
        ("scip-typescript npm app 1.0 pkg/`b.ts`/bar().",),
    )
    conn.execute(
        "INSERT INTO defn_enclosing_ranges VALUES (1, 1, 10, 12)"
    )
    conn.execute(
        "INSERT INTO defn_enclosing_ranges VALUES (2, 2, 4, 6)"
    )
    conn.commit()
    return conn


class TestMachineOutputFlags:
    def test_search_names_only(self, capsys):
        db = _make_db()
        args = SimpleNamespace(
            pattern="foo",
            kind=None,
            limit=10,
            path=None,
            names_only=True,
            paths_only=False,
        )
        with patch("scip_cli.commands.search.setup", return_value=(db, Path("/proj"))):
            with patch(
                "scip_cli.commands.search.path_scope_from_args", return_value=None
            ):
                search.main(args)
        out = capsys.readouterr().out.strip().splitlines()
        assert "foo" in out
        assert all(" " not in line or line == "foo" for line in out)
        db.close()

    def test_search_paths_only(self, capsys):
        db = _make_db()
        args = SimpleNamespace(
            pattern="foo",
            kind=None,
            limit=10,
            path=None,
            names_only=False,
            paths_only=True,
        )
        with patch("scip_cli.commands.search.setup", return_value=(db, Path("/proj"))):
            with patch(
                "scip_cli.commands.search.path_scope_from_args", return_value=None
            ):
                search.main(args)
        out = capsys.readouterr().out.strip().splitlines()
        assert out == ["pkg/a.ts"]
        db.close()

    def test_refs_paths_only(self, capsys):
        db = _make_db()
        db.execute("INSERT INTO chunks VALUES (1, 1, 20, 20)")
        db.execute("INSERT INTO chunks VALUES (2, 2, 30, 30)")
        db.execute("INSERT INTO mentions VALUES (1, 1, 0)")
        db.execute("INSERT INTO mentions VALUES (1, 2, 0)")
        db.commit()

        args = SimpleNamespace(symbol="foo", limit=10, path=None, paths_only=True)
        project_root = Path(tempfile.mkdtemp())
        (project_root / "pkg").mkdir(parents=True)
        (project_root / "pkg" / "a.ts").write_text("const x = foo()\n", encoding="utf-8")
        (project_root / "pkg" / "b.ts").write_text("foo()\n", encoding="utf-8")

        with patch("scip_cli.commands.refs.setup", return_value=(db, project_root)):
            with patch(
                "scip_cli.commands.refs.path_scope_from_args", return_value=None
            ):
                with patch(
                    "scip_cli.commands.refs.resolve_symbol",
                    return_value=[(1, "sym", "foo")],
                ):
                    refs.main(args)
        out = capsys.readouterr().out.strip().splitlines()
        assert out == ["pkg/a.ts", "pkg/b.ts"]
        db.close()

    def test_members_names_only(self, capsys):
        db = _make_db()
        db.execute(
            "INSERT INTO global_symbols (symbol, enclosing_symbol) VALUES (?, ?)",
            ("scip-typescript npm app 1.0 pkg/`a.ts`/MyClass#run().", "parent"),
        )
        db.execute(
            "UPDATE global_symbols SET symbol = 'parent#' WHERE id = 1"
        )
        db.commit()

        args = SimpleNamespace(symbol="MyClass", limit=10, path=None, names_only=True)
        with patch("scip_cli.commands.members.setup", return_value=(db, Path("/proj"))):
            with patch(
                "scip_cli.commands.members.path_scope_from_args", return_value=None
            ):
                with patch(
                    "scip_cli.commands.members.resolve_one_symbol",
                    return_value=(1, "parent#", "MyClass"),
                ):
                    with patch(
                        "scip_cli.commands.members.get_members",
                        return_value=[
                            (2, "parent#run().", "run", 1, 1),
                            (3, "parent#stop().", "stop", 2, 2),
                        ],
                    ):
                        with patch(
                            "scip_cli.commands.members.get_def_location",
                            return_value=("pkg/a.ts", 0, 10),
                        ):
                            members.main(args)
        out = capsys.readouterr().out.strip().splitlines()
        assert out == ["run", "stop"]
        db.close()
