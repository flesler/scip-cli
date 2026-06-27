"""Tests for cache directory naming."""
import json

from scip_cli.cache import (
    find_db,
    get_cache_dir,
    index_db_path,
    project_cache_slug,
    promote_next_index,
)
from scip_cli.scope import save_index_scope


class TestGetCacheDir:
    def test_slug_is_human_readable(self, tmp_path):
        cache = get_cache_dir(tmp_path)
        assert cache.parent.name == "projects"
        slug = cache.name
        assert "-" in slug
        assert slug.endswith(project_cache_slug(tmp_path).split("-")[-1])

    def test_same_dir_for_index_roots_and_scope(self, tmp_path):
        default = get_cache_dir(tmp_path)
        (tmp_path / ".scip-cli.json").write_text(
            json.dumps({"indexRoots": ["packages/api"]}),
            encoding="utf-8",
        )
        assert get_cache_dir(tmp_path) == default
        save_index_scope(tmp_path, ["packages/api"])
        assert get_cache_dir(tmp_path) == default

    def test_monorepo_slug_uses_basename(self, tmp_path):
        repo = tmp_path / "Code" / "my-monorepo"
        repo.mkdir(parents=True)
        assert project_cache_slug(repo).startswith("my-monorepo-")

    def test_find_db_returns_existing_index(self, tmp_path):
        cache_dir = get_cache_dir(tmp_path)
        cache_dir.mkdir(parents=True)
        (cache_dir / "index.db").write_text("x", encoding="utf-8")
        save_index_scope(tmp_path, ["packages/api"])
        assert find_db(tmp_path) == cache_dir / "index.db"

    def test_promote_next_index(self, tmp_path):
        cache_dir = get_cache_dir(tmp_path)
        cache_dir.mkdir(parents=True)
        (cache_dir / "index.db").write_text("live", encoding="utf-8")
        (index_db_path(cache_dir, replace=True)).write_text("next", encoding="utf-8")

        promote_next_index(cache_dir)

        assert (cache_dir / "index.db").read_text(encoding="utf-8") == "next"
        assert not index_db_path(cache_dir, replace=True).exists()
