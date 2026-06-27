"""Tests for scip_cli.analyze SQL dashboards."""

from scip_cli.analyze import file as file_checks
from scip_cli.analyze import project as project_checks
from scip_cli.analyze import symbol as symbol_checks
from scip_cli.analyze.common import analyze_noise, is_test_path

from .analyze_db import mini_codebase_db


class TestAnalyzeNoise:
    def test_is_test_path(self):
        assert is_test_path("tests/test_foo.py")
        assert is_test_path("src/foo.test.ts")
        assert is_test_path("src/foo.spec.tsx")
        assert is_test_path("pkg/__tests__/bar.js")
        assert is_test_path("conftest.py")
        assert not is_test_path("scip_cli/queries.py")

    def test_skips_tests_and_private(self):
        assert analyze_noise("tests/test_foo.py", "scip-python x `t.py`/helper().")
        assert analyze_noise("scip_cli/foo.py", "scip-python x `t.py`/_helper().")
        assert not analyze_noise("scip_cli/foo.py", "scip-python x `t.py`/helper().")

    def test_include_tests_keeps_test_paths(self):
        assert not analyze_noise("tests/test_foo.py", "scip-python x `t.py`/helper().", include_tests=True)
        assert analyze_noise("tests/test_foo.py", "scip-python x `t.py`/_helper().", include_tests=True)


class TestProjectAnalyze:
    def test_hotspots_finds_greet_like_hub(self):
        db = mini_codebase_db()
        lines = project_checks.hotspots(db, limit=5)
        assert any("foo" in line for line in lines)

    def test_hotspots_scoped_to_directory(self):
        db = mini_codebase_db()
        all_lines = project_checks.hotspots(db, limit=20)
        scoped = project_checks.hotspots(db, limit=20, scope="src/cycle")
        assert scoped
        assert all("cycle/" in line for line in scoped)
        assert len(scoped) <= len(all_lines)

    def test_cycles_scoped_to_directory(self):
        db = mini_codebase_db()
        lines = project_checks.cycles(db, limit=10, scope="src/cycle")
        assert any("cycle/a.ts" in line and "cycle/b.ts" in line for line in lines)

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

    def test_run_all_includes_coupling(self):
        db = mini_codebase_db()
        sections = file_checks.run_all(db, "src/lib.ts", limit=5)
        titles = [title for title, _lines in sections]
        assert "Coupling partners" in titles


class TestAnalyzeTargets:
    def test_resolve_directory_from_index_prefix(self, tmp_path):
        from scip_cli.analyze.targets import list_dir_files, resolve_analyze_target

        db = mini_codebase_db()
        resolved = resolve_analyze_target(db, "src/cycle", tmp_path, None)
        assert resolved.kind == "dir"
        assert resolved.scope == "src/cycle"
        files = list_dir_files(db, "src/cycle")
        assert files == ["src/cycle/a.ts", "src/cycle/b.ts"]

    def test_resolve_single_file(self, tmp_path):
        from scip_cli.analyze.targets import resolve_analyze_target

        db = mini_codebase_db()
        resolved = resolve_analyze_target(db, "src/lib.ts", tmp_path, None)
        assert resolved.kind == "file"
        assert resolved.scope == "src/lib.ts"

    def test_resolve_symbol_when_not_file_or_dir(self, tmp_path):
        from scip_cli.analyze.targets import resolve_analyze_target

        db = mini_codebase_db()
        resolved = resolve_analyze_target(db, "foo", tmp_path, None)
        assert resolved.kind == "symbol"
        assert resolved.symbol_name == "foo"


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
