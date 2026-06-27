"""Tests for indexer environment defaults."""

from scip_cli.indexing import DEFAULT_MAX_HEAP_MB
from scip_cli.indexing import indexer_env as _indexer_env


def test_default_heap_mb_without_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SCIP_CLI_MAX_HEAP_MB", raising=False)
    env = _indexer_env(tmp_path)
    assert env["NODE_OPTIONS"] == f"--max-old-space-size={DEFAULT_MAX_HEAP_MB}"


def test_default_heap_mb():
    env = _indexer_env()
    assert f"--max-old-space-size={DEFAULT_MAX_HEAP_MB}" in env["NODE_OPTIONS"]


def test_config_overrides_heap(tmp_path, monkeypatch):
    monkeypatch.delenv("SCIP_CLI_MAX_HEAP_MB", raising=False)
    (tmp_path / ".scip-cli.json").write_text('{"maxHeapMb": 12288}', encoding="utf-8")
    env = _indexer_env(tmp_path)
    assert "--max-old-space-size=12288" in env["NODE_OPTIONS"]


def test_env_overrides_config(tmp_path, monkeypatch):
    (tmp_path / ".scip-cli.json").write_text('{"maxHeapMb": 12288}', encoding="utf-8")
    monkeypatch.setenv("SCIP_CLI_MAX_HEAP_MB", "4096")
    env = _indexer_env(tmp_path)
    assert "--max-old-space-size=4096" in env["NODE_OPTIONS"]


def test_invalid_env_heap_raises(monkeypatch):
    import pytest

    monkeypatch.setenv("SCIP_CLI_MAX_HEAP_MB", "not-a-number")
    with pytest.raises(RuntimeError, match="SCIP_CLI_MAX_HEAP_MB"):
        _indexer_env()
