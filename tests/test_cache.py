"""Tests for cache directory naming."""
import json
from pathlib import Path

from scip_cli.cache import get_cache_dir


class TestGetCacheDir:
    def test_default_config_suffix(self, tmp_path):
        cache = get_cache_dir(tmp_path)
        assert cache.parent.name == "projects"
        assert "-" in cache.name
        assert len(cache.name.split("-", 1)[0]) == 12

    def test_index_roots_change_cache_dir(self, tmp_path):
        default = get_cache_dir(tmp_path)
        (tmp_path / ".scip-cli.json").write_text(
            json.dumps({"indexRoots": ["packages/api"]}),
            encoding="utf-8",
        )
        configured = get_cache_dir(tmp_path)
        assert configured != default
