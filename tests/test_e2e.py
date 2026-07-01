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


class TestDeps:
    def test_symbol_deps(self, cli):
        result = cli.run("deps", "useWidget", "--limit", "10")
        assert result.returncode == 0
        assert "Widget" in result.stdout or "greet" in result.stdout

    def test_file_deps(self, cli):
        result = cli.run("deps", USER_FILE, "--limit", "10")
        assert result.returncode == 0
        assert "Widget" in result.stdout or "greet" in result.stdout

    def test_paths_only(self, cli):
        result = cli.run("deps", USER_FILE, "--paths-only", "--limit", "10")
        assert result.returncode == 0
        assert WIDGET_FILE in result.stdout
        # Should not contain line numbers in paths-only mode
        assert ":" not in result.stdout

    def test_filters_builtin_symbols(self, cli):
        """Built-in symbols without definitions should be filtered from deps output."""
        result = cli.run("deps", USER_FILE, "--limit", "50")
        assert result.returncode == 0
        # All output lines (except warnings) should have file:path format
        # Built-ins or symbols without definitions should NOT appear as bare names
        raw_lines = result.stdout.strip().splitlines()
        lines = [line.strip() for line in raw_lines if line.strip() and not line.startswith("#")]
        # Every line should contain a colon (file:line format)
        for line in lines:
            assert ":" in line, f"Expected file:line format but got bare symbol: {line}"

    def test_with_external_keeps_all_symbols(self):
        """Verify that --with-external flag is available for reindex."""
        from tests.e2e_harness import run_cli

        # Just verify the flag exists and doesn't crash
        result = run_cli(["reindex", "--help"])
        assert result.returncode == 0
        assert "--with-external" in result.stdout


class TestPruningBehavior:
    """Test what gets pruned vs kept during indexing."""

    def test_keeps_functions_with_definitions(self, indexed_fixture):
        """Functions with definitions should be kept."""
        conn = sqlite3.connect(indexed_fixture.db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM global_symbols gs "
            "JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id "
            "WHERE gs.symbol LIKE '%greet()%'"
        ).fetchone()[0]
        conn.close()
        assert count > 0, "Function 'greet' should have a definition and be kept"

    def test_keeps_type_literal_fields(self, indexed_fixture):
        """Type literal fields (no defs) should be kept for type analysis."""
        conn = sqlite3.connect(indexed_fixture.db_path)
        count = conn.execute("SELECT COUNT(*) FROM global_symbols WHERE symbol LIKE '%typeLiteral%'").fetchone()[0]
        conn.close()
        assert count > 0, "Type literal fields should be kept even without definitions"

    def test_keeps_parameters(self, indexed_fixture):
        """Function parameters should be kept for understanding signatures."""
        conn = sqlite3.connect(indexed_fixture.db_path)
        count = conn.execute("SELECT COUNT(*) FROM global_symbols WHERE symbol LIKE '%).(%'").fetchone()[0]
        conn.close()
        assert count > 0, "Parameters should be kept even without definitions"

    def test_prunes_external_imports_without_defs(self, indexed_fixture):
        """External library imports without definitions should be pruned by default."""
        conn = sqlite3.connect(indexed_fixture.db_path)
        # Check if external-lib symbols exist (they shouldn't after pruning)
        external_count = conn.execute(
            "SELECT COUNT(*) FROM global_symbols gs "
            "LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id "
            "WHERE der.symbol_id IS NULL "
            "AND gs.symbol NOT LIKE '%typeLiteral%' "
            "AND gs.symbol NOT LIKE '%).(%' "
            "AND gs.symbol NOT LIKE '%().'"
        ).fetchone()[0]
        conn.close()
        assert external_count == 0, f"External symbols should be pruned, found {external_count}"

    def test_prunes_variables(self, indexed_fixture):
        """Const/let/var variables should be pruned (already handled by sql_exclude_variable_symbols)."""
        conn = sqlite3.connect(indexed_fixture.db_path)
        var_count = conn.execute(
            "SELECT COUNT(*) FROM global_symbols "
            + "WHERE symbol LIKE '%.' AND symbol NOT LIKE '%().%' "
            + "AND symbol NOT LIKE '%typeLiteral%'"
        ).fetchone()[0]
        conn.close()
        # Variables ending with '.' (like 'message.') should be excluded
        # Note: This might be 0 if no vars were indexed at all
        assert var_count == 0, f"Variables should be pruned, found {var_count}"


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
        assert docs >= 25
        assert symbols >= 40
