"""Tests for --tsconfig path expansion."""

import json
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


class TestAllowJsOverlay:
    def test_extends_allow_js_adds_js_include(self, tmp_path):
        from scip_cli.tsconfig import allow_js_overlay, resolved_allow_js

        _write(
            tmp_path / "tsconfig.base.json",
            json.dumps({"compilerOptions": {"allowJs": True}}),
        )
        child = tmp_path / "pkg" / "tsconfig.app.json"
        _write(
            child,
            json.dumps(
                {
                    "extends": "../tsconfig.base.json",
                    "include": ["src/**/*.ts", "src/**/*.tsx"],
                }
            ),
        )
        assert resolved_allow_js(child) is True
        overlay = allow_js_overlay(child)
        assert overlay is not None
        include = overlay["include"]
        assert any(item.endswith("src/**/*.js") for item in include)
        assert any(item.endswith("src/**/*.jsx") for item in include)
        assert overlay["extends"] == child.resolve().as_posix()

    def test_allow_js_false_skips_overlay(self, tmp_path):
        from scip_cli.tsconfig import allow_js_overlay

        child = tmp_path / "tsconfig.app.json"
        _write(
            child,
            json.dumps(
                {
                    "compilerOptions": {"allowJs": False},
                    "include": ["src/**/*.ts"],
                }
            ),
        )
        assert allow_js_overlay(child) is None

    def test_js_already_in_include_skips_overlay(self, tmp_path):
        from scip_cli.tsconfig import allow_js_overlay

        child = tmp_path / "tsconfig.app.json"
        _write(
            child,
            json.dumps(
                {
                    "compilerOptions": {"allowJs": True},
                    "include": ["src/**/*.ts", "src/**/*.js"],
                }
            ),
        )
        overlay = allow_js_overlay(child)
        assert overlay is None

    def test_d_ts_not_mapped_to_js(self, tmp_path):
        from scip_cli.tsconfig import extra_js_patterns

        assert extra_js_patterns(["src/index.d.ts", "src/**/*.ts"]) == ["src/**/*.js"]
