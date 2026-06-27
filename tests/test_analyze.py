"""Tests for scip_cli.analyze SQL dashboards."""

from scip_cli.analyze import file as file_checks
from scip_cli.analyze import project as project_checks
from scip_cli.analyze import symbol as symbol_checks

from .analyze_db import mini_codebase_db


class TestProjectAnalyze:
    def test_hotspots_finds_greet_like_hub(self):
        db = mini_codebase_db()
        lines = project_checks.hotspots(db, limit=5)
        assert any("foo" in line for line in lines)

    def test_cycles_finds_mutual_dependency(self):
        db = mini_codebase_db()
        lines = project_checks.cycles(db, limit=10)
        assert any("cycle/a.ts" in line and "cycle/b.ts" in line for line in lines)

    def test_dead_exports_includes_orphan(self):
        db = mini_codebase_db()
        lines = project_checks.dead_exports(db, limit=20)
        assert any("Orphan" in line or "deadFn" in line for line in lines)

    def test_run_all_returns_six_sections(self):
        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=5)
        assert len(sections) == 6
        titles = [title for title, _lines in sections]
        assert "Hotspots (most referenced)" in titles


class TestFileAnalyze:
    def test_change_surface_lists_exports(self):
        db = mini_codebase_db()
        lines = file_checks.change_surface(db, "src/lib.ts", limit=10)
        assert any("foo" in line for line in lines)

    def test_unused_imports_finds_never_used(self):
        db = mini_codebase_db()
        lines = file_checks.unused_imports(db, "src/importer.ts", limit=10)
        assert any("deadFn" in line for line in lines)

    def test_file_consumers_lists_consumer(self):
        db = mini_codebase_db()
        lines = file_checks.file_consumers(db, "src/lib.ts", limit=10)
        assert any("consumer.ts" in line for line in lines)

    def test_run_all_returns_six_sections(self):
        db = mini_codebase_db()
        sections = file_checks.run_all(db, "src/lib.ts", limit=5)
        assert len(sections) == 6


class TestSymbolAnalyze:
    def test_consumer_files_for_foo(self):
        db = mini_codebase_db()
        foo_id = db.execute(
            "SELECT id FROM global_symbols WHERE display_name = 'foo'",
        ).fetchone()[0]
        lines = symbol_checks.consumer_files(db, foo_id, limit=10)
        assert any("consumer.ts" in line for line in lines)

    def test_symbol_pressure_has_metrics(self):
        db = mini_codebase_db()
        foo_id = db.execute(
            "SELECT id FROM global_symbols WHERE display_name = 'foo'",
        ).fetchone()[0]
        lines = symbol_checks.symbol_pressure(db, foo_id)
        assert any("fan_in=" in line for line in lines)

    def test_def_context(self):
        db = mini_codebase_db()
        foo_id = db.execute(
            "SELECT id FROM global_symbols WHERE display_name = 'foo'",
        ).fetchone()[0]
        lines = symbol_checks.def_context(db, foo_id)
        assert any("kind=function" in line for line in lines)

    def test_run_all_returns_five_sections(self):
        db = mini_codebase_db()
        foo_id = db.execute(
            "SELECT id FROM global_symbols WHERE display_name = 'foo'",
        ).fetchone()[0]
        sections = symbol_checks.run_all(db, foo_id, limit=5)
        assert len(sections) == 5


class TestAnalyzeCommand:
    def test_project_analyze_rejects_path(self, tmp_path, monkeypatch):
        from argparse import Namespace

        import pytest

        from scip_cli.commands import analyze as analyze_cmd

        monkeypatch.setattr(analyze_cmd, "setup", lambda: (None, tmp_path))
        monkeypatch.setattr(analyze_cmd, "path_scope_from_args", lambda _a, _r: "pkg")

        with pytest.raises(SystemExit) as exc:
            analyze_cmd.main(Namespace(target=None, limit=20, path="pkg"))
        assert exc.value.code == 1
