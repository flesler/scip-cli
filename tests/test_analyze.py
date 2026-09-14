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
        assert is_test_path("src/foo.mocha.ts")
        assert is_test_path("src/foo_test.ts")
        assert is_test_path("src/lib/test-fixtures.ts")
        assert is_test_path("pkg/__fixtures__/builders.ts")
        assert is_test_path("pkg/__mocks__/fs.ts")
        assert is_test_path("src/lib/test-mocks.ts")
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
        from scip_cli.analyze.sections import TRUNCATION_LINE

        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=3)
        data_rows = 0
        for title, lines, _preface in sections:
            if title.startswith("[note]"):
                continue
            if lines == ["(none)"]:
                continue
            data_rows += sum(1 for line in lines if line != TRUNCATION_LINE)
        assert data_rows <= 3
        assert any(title.startswith("[note]") for title, _lines, _preface in sections)

    def test_run_all_per_check_limit_spreads_budget(self):
        from scip_cli.analyze.sections import TRUNCATION_LINE

        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=20, per_check_limit=1)
        hit_sections = [
            [line for line in lines if line != TRUNCATION_LINE]
            for title, lines, _preface in sections
            if lines != ["(none)"] and not title.startswith("[note]")
        ]
        assert hit_sections
        assert all(len(lines) <= 1 for lines in hit_sections)
        assert len(hit_sections) > 1
        assert any(TRUNCATION_LINE in lines for _title, lines, _preface in sections)

    def test_run_all_returns_nine_sections_without_duplicate_unreferenced(self):
        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=500)
        assert len(sections) == 9
        titles = [title for title, _lines, _preface in sections]
        assert sum(1 for t in titles if "[low]" in t) == 4
        assert sum(1 for t in titles if "[medium]" in t) == 1
        assert not any("Unreferenced symbols" in title for title in titles)
        assert any("Dead exports" in title for title in titles)
        assert titles[0].startswith("[high]")
        assert "Cycles" in titles[0]
        assert titles[-1].startswith("[low]")
        assert "Top coupling" in titles[-1]

    def test_unreferenced_runs_when_dead_exports_off(self):
        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=20, check_keys={"unreferenced"})
        assert len(sections) == 1
        assert "Unreferenced" in sections[0][0]

    def test_dead_exports_preface_when_hits(self):
        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=20)
        dead = next((entry for entry in sections if "Dead exports" in entry[0]), None)
        assert dead is not None
        _title, lines, preface = dead
        if lines != ["(none)"]:
            assert preface is not None
            assert "rdeps" in preface
            assert "STEM" in preface

    def test_run_all_high_priority_only(self):
        from scip_cli.analyze.sections import Priority

        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=500, priorities={Priority.HIGH})
        assert len(sections) == 4
        titles = [title for title, _lines, _preface in sections]
        assert all("[high]" in title for title in titles)

    def test_run_all_check_keys_only(self):
        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=500, check_keys={"cycles"})
        assert len(sections) == 1
        assert "Cycles" in sections[0][0]

    def test_run_all_check_and_priority_and(self):
        from scip_cli.analyze.sections import Priority

        db = mini_codebase_db()
        sections = project_checks.run_all(
            db,
            limit=500,
            priorities={Priority.HIGH},
            check_keys={"cycles", "hotspots"},
        )
        assert len(sections) == 1
        assert "Cycles" in sections[0][0]

    def test_dead_files_empty_rdeps(self):
        b = AnalyzeDbBuilder()
        used = b.define("src/used.ts", "usedFn")
        b.reference("src/entry.ts", used)
        b.define("src/orphan.ts", "orphanFn")
        b.define("tests/orphan.spec.ts", "testHelper")
        db = b.finish()
        lines = project_checks.dead_files(db, limit=20)
        assert "src/orphan.ts" in lines
        assert "src/entry.ts" in lines
        assert "src/used.ts" not in lines
        assert not any("orphan.spec.ts" in line for line in lines)
        with_tests = project_checks.dead_files(db, limit=20, include_tests=True)
        assert any("orphan.spec.ts" in line for line in with_tests)

    def test_dead_files_preface_when_hits(self):
        db = mini_codebase_db()
        sections = project_checks.run_all(db, limit=20, check_keys={"dead_files"})
        assert len(sections) == 1
        _title, lines, preface = sections[0]
        assert "Dead files" in _title
        if lines != ["(none)"]:
            assert preface is not None
            assert "STEM" in preface
            assert "rg -F" in preface

    def test_dead_files_skips_module_and_type_only_docs(self):
        b = AnalyzeDbBuilder()
        b.define_module("src/ui/widget.ts")
        b.define_type("src/ui/widget.ts", "WidgetProps")
        db = b.finish()
        lines = project_checks.dead_files(db, limit=20)
        assert "src/ui/widget.ts" not in lines

    def test_dead_files_skips_live_module_import(self):
        b = AnalyzeDbBuilder()
        mod = b.define_module("src/pkg/mod.ts")
        b.reference("src/entry.ts", mod)
        db = b.finish()
        lines = project_checks.dead_files(db, limit=20)
        assert "src/pkg/mod.ts" not in lines

    def test_dead_exports_skips_job_run_entrypoint(self):
        b = AnalyzeDbBuilder()
        b.define("src/jobs/tasks/cleanup.ts", "run")
        db = b.finish()
        dead = project_checks.dead_exports(db, limit=20)
        assert not any("run" in line and "cleanup.ts" in line for line in dead)

    def test_dead_files_skips_migration_loader_paths(self):
        b = AnalyzeDbBuilder()
        b.define("src/db/migrations/001_init.ts", "up")
        b.define("src/orphan.ts", "orphanFn")
        lines = project_checks.dead_files(b.finish(), limit=20)
        assert "src/orphan.ts" in lines
        assert not any("migrations/" in line for line in lines)

    def test_dead_files_does_not_skip_job_layout_paths(self):
        b = AnalyzeDbBuilder()
        b.define("src/jobs/tasks/cleanup.ts", "helper")
        lines = project_checks.dead_files(b.finish(), limit=20)
        assert "src/jobs/tasks/cleanup.ts" in lines


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
        assert not any("Unreferenced in file" in title for title in titles)
        assert any("Dead exports in file" in title for title in titles)

    def test_unreferenced_in_file_runs_when_dead_in_file_off(self):
        db = mini_codebase_db()
        sections = file_checks.run_all(db, "src/lib.ts", limit=20, check_keys={"unreferenced"})
        assert len(sections) == 1
        assert "Unreferenced in file" in sections[0][0]

    def test_one_live_index_across_project_and_file_when_bound(self, monkeypatch):
        from scip_cli.analyze import live as live_mod
        from scip_cli.analyze.live import bind_live, reset_live
        from scip_cli.analyze.sections import RowBudget

        builds = {"n": 0}
        orig = live_mod.LiveIndex.__init__

        def wrapped(self, db):
            builds["n"] += 1
            orig(self, db)

        monkeypatch.setattr(live_mod.LiveIndex, "__init__", wrapped)
        db = mini_codebase_db()
        token = bind_live(db)
        try:
            budget = RowBudget(remaining=500)
            project_checks.run_all(db, limit=500, budget=budget)
            file_checks.run_all(db, "src/lib.ts", limit=500, budget=budget)
        finally:
            reset_live(token)
        assert builds["n"] == 1


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

    def test_parse_checks(self):
        import pytest

        from scip_cli.analyze.sections import parse_checks

        assert parse_checks(None) is None
        assert parse_checks([]) is None
        assert parse_checks(["cycles"]) == {"cycles"}
        assert parse_checks(["cycles,hotspots"]) == {"cycles", "hotspots"}
        assert parse_checks(["cycles", "hotspots"]) == {"cycles", "hotspots"}
        with pytest.raises(RuntimeError, match="unknown analyze check"):
            parse_checks(["not_a_check"])


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
