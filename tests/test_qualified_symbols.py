"""Tests for qualified symbols, type-literal fields, and members."""

import sqlite3

from scip_cli.queries import get_members, resolve_symbol
from scip_cli.symbols import extract_leaf_name, symbol_matches_qualifier
from tests.analyze_db import AnalyzeDbBuilder

OPTIONS_VERBOSE = "scip-typescript npm test 1.0 src/helper.ts/`helper.ts`/Options#typeLiteral0:verbose."


class TestSymbolMatchesQualifier:
    def test_class_method(self):
        sym = "scip-typescript npm test 1.0 src/`widget.ts`/Widget#run()."
        assert symbol_matches_qualifier(sym, ["Widget"], "run")

    def test_type_literal_field(self):
        assert symbol_matches_qualifier(OPTIONS_VERBOSE, ["Options"], "verbose")

    def test_type_literal_field_rejects_wrong_leaf(self):
        assert not symbol_matches_qualifier(OPTIONS_VERBOSE, ["Options"], "quiet")

    def test_type_literal_field_rejects_wrong_container(self):
        assert not symbol_matches_qualifier(OPTIONS_VERBOSE, ["Other"], "verbose")


class TestResolveTypeLiteralField:
    def _db_with_options(self) -> sqlite3.Connection:
        b = AnalyzeDbBuilder()
        b.define("src/helper.ts", "Options")
        b.type_literal_field("src/helper.ts", "Options", "verbose")
        return b.finish()

    def test_qualified_resolve(self):
        db = self._db_with_options()
        results = resolve_symbol(db, "Options.verbose")
        assert len(results) == 1
        assert "typeLiteral0:verbose" in results[0][1]
        db.close()

    def test_bare_leaf_finds_type_literal(self):
        db = self._db_with_options()
        results = resolve_symbol(db, "verbose")
        assert any("typeLiteral0:verbose" in r[1] for r in results)
        db.close()


class TestGetMembers:
    def test_class_methods(self):
        b = AnalyzeDbBuilder()
        widget_id = b.define("src/widget.ts", "Widget")
        b.method("src/widget.ts", "Widget", "run")
        b.method("src/widget.ts", "Widget", "stop")
        db = b.finish()

        members = get_members(db, widget_id)
        names = {extract_leaf_name(m[1]) for m in members}
        assert names == {"run", "stop"}
        db.close()

    def test_type_literal_fields(self):
        b = AnalyzeDbBuilder()
        options_id = b.define("src/helper.ts", "Options")
        b.type_literal_field("src/helper.ts", "Options", "verbose")
        b.type_literal_field("src/helper.ts", "Options", "debug")
        db = b.finish()

        members = get_members(db, options_id)
        names = {extract_leaf_name(m[1]) for m in members}
        assert names == {"debug", "verbose"}
        db.close()

    def test_excludes_parameters(self):
        b = AnalyzeDbBuilder()
        foo_id = b.define("src/x.ts", "Foo")
        method_id = b.method("src/x.ts", "Foo", "bar")
        db = b.finish()
        param_sym = "scip-typescript npm test 1.0 src/x.ts/`x.ts`/Foo#bar().(eventIds)"
        db.execute(
            "INSERT INTO global_symbols (id, symbol, display_name) VALUES (?, ?, ?)",
            (99, param_sym, "eventIds"),
        )
        db.commit()

        members = get_members(db, foo_id)
        member_ids = {m[0] for m in members}
        assert method_id in member_ids
        assert 99 not in member_ids
        db.close()

    def test_no_enclosing_symbol_column_needed(self):
        """get_members must work on trimmed indexes without enclosing_symbol."""
        b = AnalyzeDbBuilder()
        parent_id = b.define("src/a.ts", "Parent")
        b.method("src/a.ts", "Parent", "child")
        db = b.finish()
        cols = {row[1] for row in db.execute("PRAGMA table_info(global_symbols)").fetchall()}
        assert "enclosing_symbol" not in cols
        assert len(get_members(db, parent_id)) == 1
        db.close()
