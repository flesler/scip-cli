"""Tests for TypeScript project list resolution."""

import json
from pathlib import Path

import pytest

from scip_cli.indexing import typescript_projects as _typescript_projects


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestTypescriptProjects:
    def test_merges_configured_roots_with_discovery(self, tmp_path):
        _write(tmp_path / "package.json", json.dumps({"workspaces": ["packages/api"]}))
        _write(tmp_path / "tsconfig.json", '{"include": ["*.ts"]}')
        _write(tmp_path / "packages" / "api" / "tsconfig.json", '{"include": ["src/**/*.ts"]}')
        _write(tmp_path / "packages" / "worker" / "tsconfig.json", '{"include": ["src/**/*.ts"]}')
        _write(
            tmp_path / ".scip-cli.json",
            json.dumps({"indexRoots": ["packages/worker"]}),
        )

        projects = _typescript_projects(tmp_path)
        assert Path("packages/api") in projects
        assert Path("packages/worker") in projects

    def test_only_index_roots_skips_discovery(self, tmp_path):
        _write(tmp_path / "package.json", json.dumps({"workspaces": ["packages/api"]}))
        _write(tmp_path / "packages" / "api" / "tsconfig.json", '{"include": ["src/**/*.ts"]}')
        _write(tmp_path / "packages" / "worker" / "tsconfig.json", '{"include": ["src/**/*.ts"]}')
        _write(
            tmp_path / ".scip-cli.json",
            json.dumps(
                {
                    "indexRoots": ["packages/worker"],
                    "onlyIndexRoots": True,
                }
            ),
        )

        projects = _typescript_projects(tmp_path)
        assert projects == [Path("packages/worker")]

    def test_only_index_roots_requires_paths(self, tmp_path):
        _write(
            tmp_path / ".scip-cli.json",
            json.dumps({"onlyIndexRoots": True, "indexRoots": []}),
        )
        with pytest.raises(RuntimeError, match="onlyIndexRoots"):
            _typescript_projects(tmp_path)
