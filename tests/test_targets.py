"""Tests for file vs symbol target heuristics."""

from scip_cli.targets import looks_like_file_target


class TestLooksLikeFileTarget:
    def test_qualified_symbol_is_not_file(self):
        assert looks_like_file_target("Transcriber.getMatch") is False
        assert looks_like_file_target("Widget.run") is False

    def test_source_extensions_are_files(self):
        assert looks_like_file_target("helper.ts") is True
        assert looks_like_file_target("index.tsx") is True
        assert looks_like_file_target("module.py") is True

    def test_paths_are_files(self):
        assert looks_like_file_target("src/util/transcriber/index.ts") is True
