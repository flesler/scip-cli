"""Tests for persisted index scope."""

import json
import shutil
from pathlib import Path

from scip_cli.cache import get_cache_dir
from scip_cli.indexing import typescript_projects
from scip_cli.scope import (
    load_index_scope,
    project_in_scope,
    save_index_scope,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestIndexScope:
    def test_scope_uses_same_cache_dir(self, tmp_path):
        default = get_cache_dir(tmp_path)
        save_index_scope(tmp_path, ["packages/api"])
        assert get_cache_dir(tmp_path) == default
        save_index_scope(tmp_path, None)
        assert get_cache_dir(tmp_path) == default

    def test_save_and_load_scope(self, tmp_path):
        assert load_index_scope(tmp_path) is None
        save_index_scope(tmp_path, ["packages/server", "packages/api"])
        scope = load_index_scope(tmp_path)
        assert scope is not None
        assert scope.paths == ("packages/server", "packages/api")
        save_index_scope(tmp_path, None)
        assert load_index_scope(tmp_path) is None

    def test_project_in_scope(self):
        assert project_in_scope(Path("packages/server"), ("packages/server",))
        assert project_in_scope(
            Path("packages/server/domains/foo"),
            ("packages/server",),
        )
        assert not project_in_scope(Path("packages/dashboard"), ("packages/server",))

    def test_scope_survives_cache_clear(self, tmp_path):
        save_index_scope(tmp_path, ["packages/api"])
        cache_dir = get_cache_dir(tmp_path)
        (cache_dir / "index.db").write_text("old", encoding="utf-8")
        shutil.rmtree(cache_dir)
        save_index_scope(tmp_path, ["packages/api"])
        loaded = load_index_scope(tmp_path)
        assert loaded is not None
        assert loaded.paths == ("packages/api",)

    def test_typescript_projects_filtered_by_scope(self, tmp_path):
        _write(tmp_path / "package.json", json.dumps({"workspaces": ["packages/api"]}))
        _write(tmp_path / "packages" / "api" / "tsconfig.json", '{"include": ["src/**/*.ts"]}')
        _write(tmp_path / "packages" / "worker" / "tsconfig.json", '{"include": ["src/**/*.ts"]}')
        save_index_scope(tmp_path, ["packages/worker"])

        projects = typescript_projects(tmp_path)
        assert projects == [Path("packages/worker")]
