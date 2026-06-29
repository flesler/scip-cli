"""Tests for TypeScript project discovery."""

import json
from pathlib import Path

from scip_cli.discover import (
    discover_golang_modules,
    discover_python_projects,
    discover_rust_crates,
    discover_typescript_projects,
    should_index_root_alongside_projects,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestDiscoverTypescriptProjects:
    def test_single_package_repo(self, tmp_path):
        _write(tmp_path / "package.json", "{}")
        _write(tmp_path / "tsconfig.json", '{"include": ["src/**/*.ts"]}')
        assert discover_typescript_projects(tmp_path) == [Path(".")]

    def test_npm_workspaces(self, tmp_path):
        _write(
            tmp_path / "package.json",
            json.dumps({"workspaces": ["packages/*"]}),
        )
        _write(tmp_path / "tsconfig.json", '{"include": ["*.ts"]}')
        _write(
            tmp_path / "packages" / "api" / "tsconfig.json",
            '{"include": ["src/**/*.ts"]}',
        )
        _write(
            tmp_path / "packages" / "web" / "tsconfig.json",
            '{"include": ["src/**/*.ts"]}',
        )

        projects = discover_typescript_projects(tmp_path)
        assert projects == [
            Path("packages/api"),
            Path("packages/web"),
        ]

    def test_broad_root_tsconfig_includes_repo_root(self, tmp_path):
        _write(
            tmp_path / "package.json",
            json.dumps({"workspaces": ["packages/*"]}),
        )
        _write(tmp_path / "tsconfig.json", '{"include": ["packages/**/*.ts"]}')
        _write(
            tmp_path / "packages" / "api" / "tsconfig.json",
            '{"include": ["src/**/*.ts"]}',
        )

        projects = discover_typescript_projects(tmp_path)
        assert projects == [Path("."), Path("packages/api")]

    def test_nested_workspace_prefers_child(self, tmp_path):
        _write(tmp_path / "package.json", "{}")
        _write(
            tmp_path / "packages" / "nested" / "tsconfig.json",
            '{"include": ["**/*.ts"]}',
        )
        _write(
            tmp_path / "packages" / "nested" / "child" / "tsconfig.json",
            '{"include": ["src/**/*.ts"]}',
        )

        projects = discover_typescript_projects(tmp_path)
        assert projects == [Path("packages/nested/child")]

    def test_finds_nested_service_style_project(self, tmp_path):
        _write(tmp_path / "package.json", "{}")
        _write(tmp_path / "tsconfig.json", '{"include": ["*.ts"]}')
        _write(
            tmp_path / "services" / "api" / "tsconfig.json",
            '{"include": ["**/*.ts"]}',
        )

        projects = discover_typescript_projects(tmp_path)
        assert Path("services/api") in projects

    def test_skips_node_modules_tsconfig(self, tmp_path):
        _write(tmp_path / "package.json", "{}")
        _write(tmp_path / "tsconfig.json", '{"include": ["src/**/*.ts"]}')
        _write(
            tmp_path / "node_modules" / "pkg" / "tsconfig.json",
            '{"include": ["src/**/*.ts"]}',
        )

        projects = discover_typescript_projects(tmp_path)
        assert projects == [Path(".")]

    def test_tsconfig_variant_with_include(self, tmp_path):
        _write(tmp_path / "package.json", "{}")
        _write(
            tmp_path / "apps" / "api" / "tsconfig.build.json",
            '{"include": ["src/**/*.ts"]}',
        )

        projects = discover_typescript_projects(tmp_path)
        assert projects == [Path("apps/api")]


class TestShouldIndexRootAlongsideProjects:
    def test_narrow_root_tsconfig_is_skipped(self, tmp_path):
        _write(tmp_path / "tsconfig.json", '{"include": ["*.ts", "types"]}')
        projects = [Path("packages/api")]
        assert should_index_root_alongside_projects(tmp_path, projects) is False

    def test_broad_root_tsconfig_is_included(self, tmp_path):
        _write(tmp_path / "tsconfig.json", '{"include": ["packages/**/*.ts"]}')
        projects = [Path("packages/api")]
        assert should_index_root_alongside_projects(tmp_path, projects) is True

    def test_empty_include_is_not_broad(self, tmp_path):
        _write(tmp_path / "tsconfig.json", '{"include": []}')
        projects = [Path("packages/api")]
        assert should_index_root_alongside_projects(tmp_path, projects) is False

    def test_string_include_is_accepted(self, tmp_path):
        _write(tmp_path / "tsconfig.json", '{"include": "packages/**/*.ts"}')
        projects = [Path("packages/api")]
        assert should_index_root_alongside_projects(tmp_path, projects) is True


class TestDiscoverGolangModules:
    def test_single_module_repo(self, tmp_path):
        _write(tmp_path / "go.mod", "module example.com/app\n\ngo 1.22\n")
        assert discover_golang_modules(tmp_path) == [Path(".")]

    def test_nested_modules(self, tmp_path):
        _write(tmp_path / "go.mod", "module example.com/root\n\ngo 1.22\n")
        _write(tmp_path / "services" / "api" / "go.mod", "module example.com/api\n\ngo 1.22\n")
        _write(tmp_path / "services" / "worker" / "go.mod", "module example.com/worker\n\ngo 1.22\n")

        assert discover_golang_modules(tmp_path) == [
            Path("."),
            Path("services/api"),
            Path("services/worker"),
        ]

    def test_skips_vendor(self, tmp_path):
        _write(tmp_path / "go.mod", "module example.com/root\n\ngo 1.22\n")
        _write(tmp_path / "vendor" / "lib" / "go.mod", "module example.com/vendor\n\ngo 1.22\n")

        assert discover_golang_modules(tmp_path) == [Path(".")]


class TestDiscoverPythonProjects:
    def test_single_package_repo(self, tmp_path):
        _write(tmp_path / "pyproject.toml", "[project]\nname = 'app'\n")
        assert discover_python_projects(tmp_path) == [Path(".")]

    def test_nested_packages(self, tmp_path):
        _write(tmp_path / "pyproject.toml", "[project]\nname = 'root'\n")
        _write(tmp_path / "packages" / "api" / "pyproject.toml", "[project]\nname = 'api'\n")
        _write(tmp_path / "packages" / "worker" / "setup.py", "from setuptools import setup\nsetup(name='worker')\n")

        assert discover_python_projects(tmp_path) == [
            Path("."),
            Path("packages/api"),
            Path("packages/worker"),
        ]

    def test_skips_venv(self, tmp_path):
        _write(tmp_path / "pyproject.toml", "[project]\nname = 'root'\n")
        _write(tmp_path / ".venv" / "lib" / "pkg" / "pyproject.toml", "[project]\nname = 'dep'\n")

        assert discover_python_projects(tmp_path) == [Path(".")]


class TestDiscoverRustCrates:
    def test_single_crate_repo(self, tmp_path):
        _write(tmp_path / "Cargo.toml", '[package]\nname = "app"\nversion = "0.1.0"\n')
        assert discover_rust_crates(tmp_path) == [Path(".")]

    def test_nested_crates(self, tmp_path):
        _write(tmp_path / "Cargo.toml", '[workspace]\nmembers = ["crates/a", "crates/b"]\n')
        _write(tmp_path / "crates" / "a" / "Cargo.toml", '[package]\nname = "a"\nversion = "0.1.0"\n')
        _write(tmp_path / "crates" / "b" / "Cargo.toml", '[package]\nname = "b"\nversion = "0.1.0"\n')

        assert discover_rust_crates(tmp_path) == [
            Path("."),
            Path("crates/a"),
            Path("crates/b"),
        ]

    def test_skips_target(self, tmp_path):
        _write(tmp_path / "Cargo.toml", '[package]\nname = "root"\nversion = "0.1.0"\n')
        _write(tmp_path / "target" / "debug" / "build" / "dep" / "Cargo.toml", '[package]\nname = "dep"\n')

        assert discover_rust_crates(tmp_path) == [Path(".")]
