"""Tests for project configuration."""
import json
from pathlib import Path

import pytest

from scip_cli.config import load_project_config, resolve_index_roots


class TestLoadProjectConfig:
    def test_defaults_when_missing(self, tmp_path):
        settings = load_project_config(tmp_path)
        assert settings.max_heap_mb is None
        assert settings.index_roots == []
        assert settings.only_index_roots is False

    def test_rejects_non_positive_heap(self, tmp_path):
        (tmp_path / ".scip-cli.json").write_text('{"maxHeapMb": 0}', encoding="utf-8")
        with pytest.raises(RuntimeError, match="maxHeapMb"):
            load_project_config(tmp_path)

    def test_rejects_boolean_heap(self, tmp_path):
        (tmp_path / ".scip-cli.json").write_text('{"maxHeapMb": true}', encoding="utf-8")
        with pytest.raises(RuntimeError, match="maxHeapMb"):
            load_project_config(tmp_path)

    def test_reads_values(self, tmp_path):
        (tmp_path / ".scip-cli.json").write_text(
            json.dumps(
                {
                    "maxHeapMb": 12288,
                    "indexRoots": ["packages/api"],
                    "onlyIndexRoots": True,
                }
            ),
            encoding="utf-8",
        )
        settings = load_project_config(tmp_path)
        assert settings.max_heap_mb == 12288
        assert settings.index_roots == ["packages/api"]
        assert settings.only_index_roots is True


class TestResolveIndexRoots:
    def test_resolves_relative_paths(self, tmp_path):
        (tmp_path / "packages" / "api").mkdir(parents=True)
        settings = load_project_config(tmp_path)
        settings.index_roots = ["packages/api"]
        roots = resolve_index_roots(tmp_path, settings)
        assert roots == [Path("packages/api")]

    def test_rejects_missing_path(self, tmp_path):
        settings = load_project_config(tmp_path)
        settings.index_roots = ["missing"]
        with pytest.raises(RuntimeError, match="does not exist"):
            resolve_index_roots(tmp_path, settings)
