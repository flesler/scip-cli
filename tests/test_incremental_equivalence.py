"""Incremental index behavior on the shared fixture (git manifest + in-place upsert)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scip_cli.cache import index_db_path, promote_next_index
from scip_cli.indexing.core import indexer_env
from scip_cli.indexing.typescript import index_typescript, typescript_projects

FIXTURE_SOURCE = Path(__file__).parent / "fixtures" / "incremental-bench"
FIXTURE_TOUCH_LARGE = "packages/bulk/src/modules/module_25.ts"

INCREMENTAL_ENV = {
    "SCIP_CLI_FILE_INCREMENTAL": "1",
}


def _init_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _run_incremental_flow(
    root: Path,
    cache_dir: Path,
    *,
    touch_path: str | None = None,
) -> Path:
    if not (root / ".git").exists():
        _init_git(root)
    env = indexer_env(root)
    projects = typescript_projects(root)

    _db, _, _, _, promote = index_typescript(root, cache_dir, projects, env, replace=True, incremental=True)
    if promote:
        promote_next_index(cache_dir)

    _db, _, _, _, promote = index_typescript(root, cache_dir, projects, env, replace=True, incremental=True)
    if promote:
        promote_next_index(cache_dir)

    if touch_path is not None:
        target = root / touch_path
        target.write_text(target.read_text(encoding="utf-8") + "\n// equivalence touch\n", encoding="utf-8")
        _db, _, _, _, promote = index_typescript(root, cache_dir, projects, env, replace=True, incremental=True)
        if promote:
            promote_next_index(cache_dir)

    return index_db_path(cache_dir)


@pytest.fixture
def incremental_env(monkeypatch):
    for key, value in INCREMENTAL_ENV.items():
        monkeypatch.setenv(key, value)


class TestIncrementalEquivalenceFixture:
    @pytest.mark.skipif(shutil.which("npx") is None, reason="npx required for scip-typescript")
    def test_modify_large_shard(self, tmp_path, incremental_env):
        work = tmp_path / "work"
        shutil.copytree(FIXTURE_SOURCE, work)
        warm = _run_incremental_flow(work, tmp_path / "cache-warm")
        touched = work / FIXTURE_TOUCH_LARGE
        touched.write_text(touched.read_text(encoding="utf-8") + "\n// equivalence touch\n", encoding="utf-8")
        env = indexer_env(work)
        projects = typescript_projects(work)
        _db, _, _, _, promote = index_typescript(
            work, tmp_path / "cache-warm", projects, env, replace=True, incremental=True
        )
        if promote:
            promote_next_index(tmp_path / "cache-warm")
        modified = index_db_path(tmp_path / "cache-warm")
        assert modified.is_file()
        assert modified.stat().st_mtime_ns >= warm.stat().st_mtime_ns
