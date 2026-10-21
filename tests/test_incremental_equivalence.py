"""Incremental index behavior on the shared fixture (git manifest + in-place upsert)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scip_cli.cache import index_db_path, promote_next_index
from scip_cli.indexing.core import indexer_env
from scip_cli.indexing.typescript import index_typescript, typescript_projects
from tests.fixture_cache import prepare_incremental_bench_warmed

FIXTURE_SOURCE = Path(__file__).parent / "fixtures" / "incremental-bench"
FIXTURE_TOUCH_LARGE = "packages/bulk/src/modules/module_25.ts"

INCREMENTAL_ENV: dict[str, str] = {}


@pytest.fixture(scope="session")
def incremental_bench_warmed():
    if shutil.which("npx") is None:
        pytest.skip("npx required for scip-typescript")
    return prepare_incremental_bench_warmed(FIXTURE_SOURCE)


@pytest.fixture
def incremental_env(monkeypatch):
    for key, value in INCREMENTAL_ENV.items():
        monkeypatch.setenv(key, value)


class TestIncrementalEquivalenceFixture:
    def test_modify_large_shard(self, tmp_path, incremental_bench_warmed, incremental_env):
        template_work, template_cache = incremental_bench_warmed
        work = tmp_path / "work"
        cache_dir = tmp_path / "cache"
        shutil.copytree(template_work, work)
        shutil.copytree(template_cache, cache_dir)

        warm = index_db_path(cache_dir)
        touched = work / FIXTURE_TOUCH_LARGE
        touched.write_text(touched.read_text(encoding="utf-8") + "\n// equivalence touch\n", encoding="utf-8")
        env = indexer_env(work)
        projects = typescript_projects(work)
        _db, _, _, _, promote = index_typescript(work, cache_dir, projects, env, replace=True, incremental=True)
        if promote:
            promote_next_index(cache_dir)
        modified = index_db_path(cache_dir)
        assert modified.is_file()
        assert modified.stat().st_mtime_ns >= warm.stat().st_mtime_ns
