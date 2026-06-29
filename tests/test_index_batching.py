"""Tests for TypeScript indexing batch helpers."""

from pathlib import Path

import pytest

from scip_cli.indexing import (
    DEFAULT_TS_INDEX_BATCH_SIZE,
    MAX_TS_INDEX_BATCH_SIZE,
    ts_index_batch_size,
)
from scip_cli.indexing.orchestrate import batch_projects, project_batch_label
from scip_cli.merge import MAX_MERGE_BATCH_SIZE, merge_batch_size


class TestTsIndexBatching:
    def test_batch_projects_chunks(self):
        projects = [Path(f"p{i}") for i in range(23)]
        batches = batch_projects(projects, 10)
        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 3

    def test_default_batches_all_projects(self, monkeypatch):
        monkeypatch.delenv("SCIP_CLI_TS_INDEX_BATCH_SIZE", raising=False)
        projects = [Path(f"p{i}") for i in range(23)]
        batches = batch_projects(projects, ts_index_batch_size())
        assert len(batches) == 1
        assert len(batches[0]) == 23

    def test_project_batch_label_single(self):
        assert project_batch_label([Path("lib/a")]) == "lib/a"

    def test_project_batch_label_multi(self):
        label = project_batch_label([Path("lib/a"), Path("lib/b")])
        assert label == "lib/a +1 more"

    def test_default_batch_size_is_unlimited(self, monkeypatch):
        monkeypatch.delenv("SCIP_CLI_TS_INDEX_BATCH_SIZE", raising=False)
        assert ts_index_batch_size() is DEFAULT_TS_INDEX_BATCH_SIZE
        assert DEFAULT_TS_INDEX_BATCH_SIZE is None
        assert MAX_TS_INDEX_BATCH_SIZE > 0

    def test_env_batch_size_rejects_above_max(self, monkeypatch):
        monkeypatch.setenv("SCIP_CLI_TS_INDEX_BATCH_SIZE", str(MAX_TS_INDEX_BATCH_SIZE + 1))
        with pytest.raises(RuntimeError, match="exceeds max"):
            ts_index_batch_size()


class TestMergeBatchSize:
    def test_default_merge_batch_size(self, monkeypatch):
        monkeypatch.delenv("SCIP_CLI_MERGE_BATCH_SIZE", raising=False)
        assert merge_batch_size() == MAX_MERGE_BATCH_SIZE

    def test_merge_batch_size_rejects_above_sqlite_limit(self, monkeypatch):
        monkeypatch.setenv("SCIP_CLI_MERGE_BATCH_SIZE", "10")
        with pytest.raises(RuntimeError, match="exceeds SQLite limit"):
            merge_batch_size()
