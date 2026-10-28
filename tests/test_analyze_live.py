"""Unit tests for analyze live-index heuristics."""

from pathlib import Path

from scip_cli.analyze import project as project_checks
from scip_cli.analyze.entrypoints import (
    EntrypointIndex,
    bind_entrypoints,
    reset_entrypoints,
)
from scip_cli.analyze.live import bind_live, is_low_signal_dead_file, live_for, reset_live

from .analyze_db import AnalyzeDbBuilder


class TestAnalyzeLiveHeuristics:
    def test_is_low_signal_dead_file(self):
        b = AnalyzeDbBuilder()
        doc_id, _chunk_id = b.add_file("src/ui/widget.ts")
        b.define_module("src/ui/widget.ts")
        db = b.finish()
        assert is_low_signal_dead_file(db, doc_id)

        typed = AnalyzeDbBuilder()
        typed.define_module("src/ui/button.ts")
        typed.define_type("src/ui/button.ts", "ButtonProps")
        typed_db = typed.finish()
        typed_doc = typed_db.execute(
            "SELECT id FROM documents WHERE relative_path = ?", ("src/ui/button.ts",)
        ).fetchone()[0]
        assert is_low_signal_dead_file(typed_db, typed_doc)

        mixed = AnalyzeDbBuilder()
        mixed.define_module("src/lib/api.ts")
        mixed.define("src/lib/api.ts", "register")
        mixed_db = mixed.finish()
        mixed_doc = mixed_db.execute(
            "SELECT id FROM documents WHERE relative_path = ?", ("src/lib/api.ts",)
        ).fetchone()[0]
        assert not is_low_signal_dead_file(mixed_db, mixed_doc)

    def test_live_for_reuses_one_index_during_a_pass(self):
        db = AnalyzeDbBuilder().finish()
        token = bind_live(db)
        try:
            assert live_for(db) is live_for(db)
        finally:
            reset_live(token)

    def test_nested_bind_live_reuses_same_index(self):
        db = AnalyzeDbBuilder().finish()
        outer = bind_live(db)
        try:
            first = live_for(db)
            inner = bind_live(db)
            try:
                assert live_for(db) is first
            finally:
                reset_live(inner)
            assert live_for(db) is first
        finally:
            reset_live(outer)
        assert live_for(db) is not first

    def test_live_for_does_not_reuse_index_for_a_different_db(self):
        db = AnalyzeDbBuilder().finish()
        other = AnalyzeDbBuilder().finish()
        token = bind_live(db)
        try:
            bound = live_for(db)
            assert live_for(other) is not bound
        finally:
            reset_live(token)


class TestEntrypointIndex:
    def test_package_json_bin_and_scripts(self, tmp_path: Path):
        (tmp_path / "bin").mkdir()
        script = tmp_path / "bin" / "run.ts"
        script.write_text("export function run() {}\n", encoding="utf-8")
        (tmp_path / "package.json").write_text(
            ('{"bin":{"app":"bin/run.ts"},"scripts":{"start":"tsx bin/run.ts"}}'),
            encoding="utf-8",
        )
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("bin/run.ts")

    def test_node_import_tsx_script_path(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        script = tmp_path / "src" / "app.test.ts"
        script.write_text("export function test() {}\n", encoding="utf-8")
        (tmp_path / "package.json").write_text(
            '{"scripts":{"test": "node --import tsx --test src/app.test.ts"}}',
            encoding="utf-8",
        )
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("src/app.test.ts")

    def test_pyproject_scripts(self, tmp_path: Path):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__main__.py").write_text("def main(): pass\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\n\n[project.scripts]\ncli = "pkg.__main__:main"\n',
            encoding="utf-8",
        )
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("pkg/__main__.py")

    def test_setup_py_console_scripts(self, tmp_path: Path):
        (tmp_path / "legacy").mkdir()
        (tmp_path / "legacy" / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\nsetup(entry_points={'console_scripts': ['tool=legacy.cli:main']})\n",
            encoding="utf-8",
        )
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("legacy/cli.py")

    def test_main_py_module_without_manifest(self, tmp_path: Path):
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "__main__.py").write_text("def main(): pass\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("app/__main__.py")

    def test_shebang_without_package_json(self, tmp_path: Path):
        (tmp_path / "bin").mkdir()
        script = tmp_path / "bin" / "cli.ts"
        script.write_text("#!/usr/bin/env node\nexport function main() {}\n", encoding="utf-8")
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("bin/cli.ts")

    def test_non_entrypoint(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        script = tmp_path / "src" / "lib.ts"
        script.write_text("export function helper() {}\n", encoding="utf-8")
        index = EntrypointIndex(tmp_path)
        assert not index.is_entrypoint("src/lib.ts")

    def test_monorepo_nested_package_json(self, tmp_path: Path):
        pkg_dir = tmp_path / "packages" / "api"
        pkg_dir.mkdir(parents=True)
        script = pkg_dir / "bin" / "run.ts"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text("export function run() {}\n", encoding="utf-8")
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        (pkg_dir / "package.json").write_text(
            '{"scripts":{"start":"tsx bin/run.ts"}}',
            encoding="utf-8",
        )
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("packages/api/bin/run.ts")

    def test_loose_script_path_in_shell_style_command(self, tmp_path: Path):
        (tmp_path / "bin").mkdir()
        script = tmp_path / "bin" / "task.ts"
        script.write_text("export function task() {}\n", encoding="utf-8")
        (tmp_path / "package.json").write_text(
            '{"scripts":{"task":"bash bin/task.ts"}}',
            encoding="utf-8",
        )
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("bin/task.ts")

    def test_bare_filename_in_script_command(self, tmp_path: Path):
        script = tmp_path / "run.ts"
        script.write_text("export function run() {}\n", encoding="utf-8")
        (tmp_path / "package.json").write_text(
            '{"scripts":{"start":"tsx run.ts"}}',
            encoding="utf-8",
        )
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("run.ts")

    def test_main_dist_js_maps_to_src_ts(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("export {};\n", encoding="utf-8")
        (tmp_path / "package.json").write_text(
            '{"main":"dist/index.js","scripts":{"cli":"npm run node -- dist/bin/cli"}}',
            encoding="utf-8",
        )
        (tmp_path / "src" / "bin").mkdir()
        (tmp_path / "src" / "bin" / "cli.ts").write_text("export function cli() {}\n", encoding="utf-8")
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("src/index.ts")
        assert index.is_entrypoint("src/bin/cli.ts")

    def test_index_html_vite_entry(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.tsx").write_text("export {};\n", encoding="utf-8")
        (tmp_path / "index.html").write_text(
            '<html><body><script type="module" src="/src/main.tsx"></script></body></html>',
            encoding="utf-8",
        )
        (tmp_path / "package.json").write_text('{"name":"app"}', encoding="utf-8")
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("src/main.tsx")

    def test_go_cmd_main(self, tmp_path: Path):
        (tmp_path / "cmd" / "server").mkdir(parents=True)
        (tmp_path / "cmd" / "server" / "main.go").write_text("package main\n", encoding="utf-8")
        (tmp_path / "go.mod").write_text("module example.com/app\n\ngo 1.21\n", encoding="utf-8")
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("cmd/server/main.go")

    def test_cargo_bin_and_default_main(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "app"\nversion = "0.1.0"\n',
            encoding="utf-8",
        )
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("src/main.rs")

    def test_setup_cfg_console_scripts(self, tmp_path: Path):
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
        (tmp_path / "setup.cfg").write_text(
            "[options.entry_points]\nconsole_scripts =\n    tool = app.cli:main\n",
            encoding="utf-8",
        )
        index = EntrypointIndex(tmp_path)
        assert index.is_entrypoint("app/cli.py")


class TestDeadFilesEntrypoints:
    def test_dead_files_skips_shebang_and_npm_targets(self, tmp_path: Path):
        (tmp_path / "bin").mkdir()
        shebang = tmp_path / "bin" / "shebang.ts"
        shebang.write_text("#!/usr/bin/env tsx\nexport function a() {}\n", encoding="utf-8")
        npm_only = tmp_path / "bin" / "script.ts"
        npm_only.write_text("export function b() {}\n", encoding="utf-8")
        (tmp_path / "package.json").write_text(
            '{"scripts":{"go":"tsx bin/script.ts"}}',
            encoding="utf-8",
        )

        b = AnalyzeDbBuilder()
        b.define("bin/shebang.ts", "a")
        b.define("bin/script.ts", "b")
        b.define("src/orphan.ts", "orphanFn")
        db = b.finish()

        token = bind_entrypoints(tmp_path)
        try:
            lines = project_checks.dead_files(db, limit=20)
            dead_exports = project_checks.dead_exports(db, limit=20)
        finally:
            reset_entrypoints(token)

        assert "src/orphan.ts" in lines
        assert "bin/shebang.ts" not in lines
        assert "bin/script.ts" not in lines
        assert not any("bin/shebang.ts" in line for line in dead_exports)
        assert not any("bin/script.ts" in line for line in dead_exports)

    def test_dead_files_skips_pyproject_script_target(self, tmp_path: Path):
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__main__.py").write_text("def main(): pass\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\n\n[project.scripts]\ncli = "pkg.__main__:main"\n',
            encoding="utf-8",
        )

        b = AnalyzeDbBuilder()
        b.define("pkg/__main__.py", "main")
        b.define("src/orphan.py", "orphan_fn")
        db = b.finish()

        token = bind_entrypoints(tmp_path)
        try:
            lines = project_checks.dead_files(db, limit=20)
            dead_exports = project_checks.dead_exports(db, limit=20)
        finally:
            reset_entrypoints(token)

        assert "src/orphan.py" in lines
        assert "pkg/__main__.py" not in lines
        assert not any("pkg/__main__.py" in line for line in dead_exports)
