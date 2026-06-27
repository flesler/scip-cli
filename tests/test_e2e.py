"""End-to-end command tests against the shared indexed fixture."""

import sqlite3

import pytest

from tests.e2e_harness import run_cli
from tests.fixture_catalog import (
    APP_HANDLER_FILE,
    CLASS_HANDLER,
    CLASS_WIDGET,
    CONSUMER_FILE,
    FIELD_VERBOSE,
    FN_GREET,
    HELPER_FILE,
    LIB_HANDLER_FILE,
    METHOD_RUN,
    TYPE_OPTIONS,
    USER_FILE,
    WIDGET_FILE,
)

pytestmark = pytest.mark.integration


class TestCliBasics:
    def test_version(self):
        result = run_cli(["--version"])
        assert result.returncode == 0
        assert "scip-cli" in result.stdout
        assert "(" in result.stdout
        assert ")" in result.stdout

    def test_skill_outputs_markdown(self):
        result = run_cli(["skill"])
        assert result.returncode == 0
        assert "Quick Decision Guide" in result.stdout


class TestSearch:
    def test_bare_name(self, cli):
        result = cli.run("search", FN_GREET, "--limit", "3")
        assert result.returncode == 0
        assert FN_GREET in result.stdout

    def test_qualified_type_field(self, cli):
        result = cli.run("search", f"{TYPE_OPTIONS}.{FIELD_VERBOSE}", "--limit", "3")
        assert result.returncode == 0
        assert FIELD_VERBOSE in result.stdout
        assert ":? " not in result.stdout
        assert f"{HELPER_FILE}:2" in result.stdout

    def test_multi_pattern_qualified_and_bare(self, cli):
        result = cli.run("search", METHOD_RUN, FN_GREET, "--limit", "5")
        assert result.returncode == 0
        assert "run" in result.stdout
        assert FN_GREET in result.stdout


class TestSymbols:
    def test_by_path(self, cli):
        result = cli.run("symbols", HELPER_FILE, "--limit", "10")
        assert result.returncode == 0
        assert FN_GREET in result.stdout

    def test_by_bare_filename(self, cli):
        result = cli.run("symbols", "helper.ts", "--limit", "10")
        assert result.returncode == 0
        assert FN_GREET in result.stdout

    def test_search_paths_pipe_symbols(self, cli):
        paths = cli.run("search", FN_GREET, "--paths-only", "--limit", "3")
        assert paths.returncode == 0
        first = paths.stdout.strip().splitlines()[0]
        result = cli.run("symbols", first, "--limit", "10")
        assert result.returncode == 0
        assert FN_GREET in result.stdout


class TestCode:
    def test_single_symbol_no_header(self, cli):
        result = cli.run("code", FN_GREET, "--limit", "1")
        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert lines[0].startswith(HELPER_FILE)
        assert lines[0] != FN_GREET
        assert "function greet" in result.stdout

    def test_multiple_symbols_with_headers(self, cli):
        result = cli.run("code", FN_GREET, METHOD_RUN, "--snippet", "--limit", "1")
        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert lines[0] == FN_GREET
        assert lines[2] == METHOD_RUN
        assert HELPER_FILE in result.stdout
        assert WIDGET_FILE in result.stdout

    def test_ambiguous_class(self, cli):
        result = cli.run("code", CLASS_HANDLER, "--snippet", "--limit", "2")
        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert lines[0].startswith(f"{CLASS_HANDLER} (")
        assert APP_HANDLER_FILE in result.stdout or LIB_HANDLER_FILE in result.stdout
        assert len(lines) >= 4

    def test_qualified_type_field(self, cli):
        result = cli.run("code", f"{TYPE_OPTIONS}.{FIELD_VERBOSE}")
        assert result.returncode == 0
        assert FIELD_VERBOSE in result.stdout

    def test_missing_symbol(self, cli):
        result = cli.run("code", "__scip_cli_missing_symbol_xyz__")
        assert result.returncode != 0
        assert "not found" in result.stderr.lower()


class TestRefs:
    def test_paths_only(self, cli):
        result = cli.run("refs", FN_GREET, "--paths-only", "--limit", "10")
        assert result.returncode == 0
        assert CONSUMER_FILE in result.stdout
        assert WIDGET_FILE in result.stdout

    def test_multiple_symbols_with_headers(self, cli):
        result = cli.run("refs", FN_GREET, METHOD_RUN, "--limit", "10")
        assert result.returncode == 0
        lines = result.stdout.strip().splitlines()
        assert FN_GREET in lines
        assert METHOD_RUN in lines
        assert CONSUMER_FILE in result.stdout
        assert USER_FILE in result.stdout


class TestMembers:
    def test_class_methods(self, cli):
        result = cli.run("members", CLASS_WIDGET, "--names-only")
        assert result.returncode == 0
        assert "run" in result.stdout

    def test_type_literal_fields(self, cli):
        result = cli.run("members", TYPE_OPTIONS, "--names-only")
        assert result.returncode == 0
        assert FIELD_VERBOSE in result.stdout


class TestRdeps:
    def test_importers(self, cli):
        result = cli.run("rdeps", HELPER_FILE, "--limit", "10")
        assert result.returncode == 0
        assert CONSUMER_FILE in result.stdout or WIDGET_FILE in result.stdout


class TestAnalyze:
    def test_project_dashboard(self, cli):
        result = cli.run("analyze", "--limit", "5")
        assert result.returncode == 0
        assert "[high]" in result.stdout
        assert "===" in result.stdout

    def test_priority_high_skips_low(self, cli):
        result = cli.run("analyze", "--priority", "high", "--limit", "5")
        assert result.returncode == 0
        assert "[high]" in result.stdout
        assert "[low]" not in result.stdout


class TestIndex:
    def test_fixture_index_queryable(self, indexed_fixture):
        conn = sqlite3.connect(indexed_fixture.db_path)
        docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        symbols = conn.execute("SELECT COUNT(*) FROM global_symbols").fetchone()[0]
        conn.close()
        assert docs >= 8
        assert symbols >= 10
