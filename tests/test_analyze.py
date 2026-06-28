"""Tests for scip_cli.analyze SQL dashboards."""

from scip_cli.analyze import file as file_checks
from scip_cli.analyze import project as project_checks
from scip_cli.analyze import symbol as symbol_checks
from scip_cli.analyze.common import analyze_noise, is_component_props_type, is_test_path

from .analyze_db import AnalyzeDbBuilder, mini_codebase_db


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

    def test_component_props_stale_noise(self):
        sym = "scip-typescript npm x 1.0 src/ui/`Button.ts`/ButtonProps#"
        assert is_component_props_type(sym)
        assert not is_component_props_type("scip-typescript npm x 1.0 src/`t.ts`/Options#")

    def test_skips_analyze_dashboard_runners(self):
        sym = "scip-python x `project.py`/bottlenecks()."
        assert analyze_noise("scip_cli/analyze/project.py", sym)

    def test_stale_type_noise_for_dataclasses(self):
        from scip_cli.analyze.common import stale_type_noise

        assert stale_type_noise("scip_cli/config.py", "scip-python x `config.py`/ProjectSettings#", 0)
        assert not stale_type_noise("scip_cli/config.py", "scip-python x `config.py`/ProjectSettings#", 1)


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

    def test_cycles_ignores_type_only_mutual_imports(self):
        b = AnalyzeDbBuilder()
        t_a = b.define_type("src/types/a.ts", "AType")
        t_b = b.define_type("src/types/b.ts", "BType")
        b.reference("src/types/a.ts", t_b)
        b.reference("src/types/b.ts", t_a)
        lines = project_checks.cycles(b.finish(), limit=10)
        assert not any("types/a.ts" in line and "types/b.ts" in line for line in lines)

    def test_cycles_keeps_runtime_mutual_imports(self):
        b = AnalyzeDbBuilder()
        sym_b = b.define("src/runtime/b.ts", "runB")
        sym_a = b.define("src/runtime/a.ts", "runA")
        b.reference("src/runtime/a.ts", sym_b)
        b.reference("src/runtime/b.ts", sym_a)
        lines = project_checks.cycles(b.finish(), limit=10)
        assert any("runtime/a.ts" in line and "runtime/b.ts" in line for line in lines)

    def test_dead_exports_includes_orphan(self):
        db = mini_codebase_db()
        lines = project_checks.dead_exports(db, limit=20)
        assert any("Orphan" in line or "deadFn" in line for line in lines)

    def test_unreferenced_finds_orphan(self):
        db = mini_codebase_db()
        lines = project_checks.unreferenced_symbols(db, limit=20)
        assert any("Orphan" in line for line in lines)
        assert not any("foo" in line for line in lines)

    def test_same_file_only_finds_helper(self):
        db = mini_codebase_db()
        lines = project_checks.same_file_only(db, limit=20)
        assert any("sameFileHelper" in line for line in lines)
        assert not any("Orphan" in line for line in lines)

    def test_test_only_symbols(self):
        db = mini_codebase_db()
        lines = project_checks.symbols_test_only_consumers(db, limit=20)
        assert any("testOnlyFn" in line for line in lines)
        assert not any("moduleUsed" in line for line in lines)

    def test_run_all_global_limit_stops_early(self):
        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=3)
        total_rows = sum(len(lines) for _title, lines, _preface in sections if lines != ["(none)"])
        assert total_rows <= 3
        assert len(sections) < 9

    def test_run_all_returns_nine_sections(self):
        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=500)
        assert len(sections) == 9
        titles = [title for title, _lines, _preface in sections]
        assert sum(1 for t in titles if "[low]" in t) == 4
        assert sum(1 for t in titles if "[medium]" in t) == 1
        titles = [title for title, _lines, _preface in sections]
        assert titles[0].startswith("[high]")
        assert "Cycles" in titles[0]
        assert titles[-1].startswith("[low]")
        assert "Top coupling" in titles[-1]

    def test_dead_exports_preface_when_hits(self):
        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=20)
        dead = next((entry for entry in sections if "Dead exports" in entry[0]), None)
        assert dead is not None
        _title, lines, preface = dead
        if lines != ["(none)"]:
            assert preface is not None
            assert "rdeps" in preface

    def test_run_all_high_priority_only(self):
        from scip_cli.analyze.sections import Priority

        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=500, priorities={Priority.HIGH})
        assert len(sections) == 4
        titles = [title for title, _lines, _preface in sections]
        assert all("[high]" in title for title in titles)


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

    def test_same_file_helper_not_in_dead_exports(self):
        db = mini_codebase_db()
        dead = project_checks.dead_exports(db, limit=20)
        assert not any("sameFileHelper" in line for line in dead)
        same = project_checks.same_file_only(db, limit=20)
        assert any("sameFileHelper" in line for line in same)

    def test_same_file_only_skips_dynamic_load_modules(self):
        b = AnalyzeDbBuilder()
        handler = b.define("src/rules/handler.ts", "onEvent")
        b.reference("src/rules/handler.ts", handler)
        lines = project_checks.same_file_only(b.finish(), limit=20)
        assert not any("onEvent" in line for line in lines)

    def test_run_all_includes_coupling(self):
        db = mini_codebase_db()
        sections = file_checks.run_all(db, "src/lib.ts", limit=500)
        titles = [title for title, _lines, _preface in sections]
        assert any("Coupling partners" in title for title in titles)


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
        sections = symbol_checks.run_all(db, foo_id, limit=500)
        assert len(sections) == 5


class TestAnalyzeSections:
    def test_parse_priorities(self):
        from scip_cli.analyze.sections import Priority, parse_priorities

        assert parse_priorities(None) is None
        assert parse_priorities("high") == {Priority.HIGH}
        assert parse_priorities("1,medium") == {Priority.HIGH, Priority.MEDIUM}


class TestAnalyzeCommand:
    def test_project_include_tests_for_test_file_path(self):
        from scip_cli.commands.analyze import _project_include_tests

        assert _project_include_tests(False, "tests/test_foo.py") is True
        assert _project_include_tests(False, "scip_cli/queries.py") is False
        assert _project_include_tests(True, "scip_cli/queries.py") is True

    def test_project_analyze_rejects_path(self, tmp_path, monkeypatch):
        from argparse import Namespace
        from unittest.mock import MagicMock

        import pytest

        from scip_cli.commands import analyze as analyze_cmd

        monkeypatch.setattr(analyze_cmd, "setup", lambda: (MagicMock(), tmp_path))
        monkeypatch.setattr(analyze_cmd, "path_scope_from_args", lambda _a, _r: "pkg")

        with pytest.raises(SystemExit) as exc:
            analyze_cmd.main(Namespace(target=None, limit=20, path="pkg"))
        assert exc.value.code == 1
