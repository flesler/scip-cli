"""Tests for unified reindex metadata.json."""

import json

from scip_cli.exclude import load_persisted_exclude_globs, save_persisted_exclude_globs
from scip_cli.metadata import (
    METADATA_FILENAME,
    IndexMetadata,
    apply_metadata_updates,
    load_metadata,
    metadata_path,
    save_metadata,
)
from scip_cli.scope import load_index_scope, save_index_scope


class TestMetadata:
    def test_save_and_load_round_trip(self, tmp_path):
        save_metadata(
            tmp_path,
            IndexMetadata(
                scope_paths=("packages/api",),
                exclude_globs=("**/*.test.ts",),
            ),
        )
        metadata = load_metadata(tmp_path)
        assert metadata == IndexMetadata(
            scope_paths=("packages/api",),
            exclude_globs=("**/*.test.ts",),
        )
        data = json.loads(metadata_path(tmp_path).read_text(encoding="utf-8"))
        assert data == {
            "scope": {"paths": ["packages/api"]},
            "exclude": {"globs": ["**/*.test.ts"]},
        }

    def test_empty_metadata_deletes_file(self, tmp_path):
        save_index_scope(tmp_path, ["packages/api"])
        save_metadata(tmp_path, IndexMetadata())
        assert not metadata_path(tmp_path).is_file()

    def test_apply_metadata_updates_preserves_unchanged_slices(self, tmp_path):
        save_index_scope(tmp_path, ["packages/api"])
        save_persisted_exclude_globs(tmp_path, ["tests/**"])

        apply_metadata_updates(tmp_path, exclude_globs=["**/*.spec.ts"])

        scope = load_index_scope(tmp_path)
        assert scope is not None
        assert scope.paths == ("packages/api",)
        assert load_persisted_exclude_globs(tmp_path) == ("**/*.spec.ts",)

    def test_fresh_clears_metadata(self, tmp_path):
        save_index_scope(tmp_path, ["packages/api"])
        save_persisted_exclude_globs(tmp_path, ["tests/**"])

        apply_metadata_updates(tmp_path, fresh=True)

        assert load_index_scope(tmp_path) is None
        assert load_persisted_exclude_globs(tmp_path) == ()
        assert not metadata_path(tmp_path).is_file()

    def test_fresh_with_exclude_only(self, tmp_path):
        save_index_scope(tmp_path, ["packages/api"])

        apply_metadata_updates(tmp_path, fresh=True, exclude_globs=["tests/**"])

        assert load_index_scope(tmp_path) is None
        assert load_persisted_exclude_globs(tmp_path) == ("tests/**",)

    def test_unversioned_round_trip(self, tmp_path):
        save_metadata(tmp_path, IndexMetadata(unversioned=True))
        assert load_metadata(tmp_path).unversioned is True
        data = json.loads(metadata_path(tmp_path).read_text(encoding="utf-8"))
        assert data == {"unversioned": True}

    def test_apply_unversioned_flag(self, tmp_path):
        apply_metadata_updates(tmp_path, unversioned=True)
        assert load_metadata(tmp_path).unversioned is True

    def test_fresh_clears_unversioned(self, tmp_path):
        apply_metadata_updates(tmp_path, unversioned=True)
        apply_metadata_updates(tmp_path, fresh=True)
        assert load_metadata(tmp_path).unversioned is False

    def test_bare_exclude_clears_slice(self, tmp_path):
        save_index_scope(tmp_path, ["packages/api"])
        save_persisted_exclude_globs(tmp_path, ["tests/**"])

        apply_metadata_updates(tmp_path, exclude_globs=[])

        scope = load_index_scope(tmp_path)
        assert scope is not None
        assert scope.paths == ("packages/api",)
        assert load_persisted_exclude_globs(tmp_path) == ()
        assert METADATA_FILENAME in metadata_path(tmp_path).name
