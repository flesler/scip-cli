"""Tests for TypeScript project discovery."""

import json
from pathlib import Path

from scip_cli.discover import (
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
