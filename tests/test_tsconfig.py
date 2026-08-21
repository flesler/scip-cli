"""Tests for --tsconfig path expansion."""

from pathlib import Path

import pytest

from scip_cli.tsconfig import expand_tsconfig_patterns, scope_tsconfig_paths


def _write(path: Path, content: str = '{"include": ["src/**/*.ts"]}') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestExpandTsconfigPatterns:
    def test_literal_file(self, tmp_path):
        _write(tmp_path / "apps" / "api" / "tsconfig.build.json")
        got = expand_tsconfig_patterns(["apps/api/tsconfig.build.json"], tmp_path)
        assert got == [Path("apps/api/tsconfig.build.json")]

    def test_glob_same_directory(self, tmp_path):
        _write(tmp_path / "pkg" / "tsconfig.json")
        _write(tmp_path / "pkg" / "tsconfig.app.json")
        _write(tmp_path / "pkg" / "tsconfig.spec.json")
        _write(tmp_path / "pkg" / "notes.json", "{}")
        got = expand_tsconfig_patterns(["pkg/tsconfig.*.json"], tmp_path)
        assert got == [
            Path("pkg/tsconfig.app.json"),
            Path("pkg/tsconfig.spec.json"),
        ]

    def test_skips_node_modules_in_glob(self, tmp_path):
        _write(tmp_path / "pkg" / "tsconfig.app.json")
        _write(tmp_path / "node_modules" / "dep" / "tsconfig.app.json")
        got = expand_tsconfig_patterns(["**/tsconfig.app.json"], tmp_path)
        assert got == [Path("pkg/tsconfig.app.json")]

    def test_dedupes_repeat_args(self, tmp_path):
        _write(tmp_path / "tsconfig.app.json")
        got = expand_tsconfig_patterns(["tsconfig.app.json", "./tsconfig.app.json"], tmp_path)
        assert got == [Path("tsconfig.app.json")]

    def test_no_match(self, tmp_path):
        with pytest.raises(RuntimeError, match="No tsconfig files matched"):
            expand_tsconfig_patterns(["pkg/tsconfig.*.json"], tmp_path)

    def test_rejects_non_tsconfig_name(self, tmp_path):
        _write(tmp_path / "jsconfig.json")
        with pytest.raises(RuntimeError, match="expected tsconfig\\*\\.json"):
            expand_tsconfig_patterns(["jsconfig.json"], tmp_path)

    def test_rejects_missing_file(self, tmp_path):
        with pytest.raises(RuntimeError, match="is not a file"):
            expand_tsconfig_patterns(["tsconfig.app.json"], tmp_path)

    def test_rejects_empty(self, tmp_path):
        with pytest.raises(RuntimeError, match="empty"):
            expand_tsconfig_patterns([""], tmp_path)


class TestScopeTsconfigPaths:
    def test_all_files(self):
        assert scope_tsconfig_paths(("a/tsconfig.app.json", "b/tsconfig.json")) == [
            Path("a/tsconfig.app.json"),
            Path("b/tsconfig.json"),
        ]

    def test_directory_prefix(self):
        assert scope_tsconfig_paths(("packages/api",)) is None

    def test_mixed_rejected(self):
        with pytest.raises(RuntimeError, match="mixes"):
            scope_tsconfig_paths(("packages/api", "pkg/tsconfig.app.json"))
