"""Tests for shard source discovery (glob with skip dirs, git-aware)."""

import subprocess
import time
from pathlib import Path

from scip_cli.indexing.source_discovery import (
    _walk_glob_source_files,
    clear_git_index_cache,
    is_versioned_repo,
    list_project_source_files,
    path_matches_tsconfig_shard,
)
from scip_cli.metadata import apply_metadata_updates


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True, capture_output=True)


def _write_ts_project(root: Path, rel_dir: str, *, source: str = "export const x = 1;\n") -> Path:
    project = root / rel_dir
    project.mkdir(parents=True, exist_ok=True)
    (project / "tsconfig.json").write_text(
        '{"include": ["src/**/*.ts"]}',
        encoding="utf-8",
    )
    src = project / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "index.ts").write_text(source, encoding="utf-8")
    return Path(rel_dir)


class TestSkipDirGlob:
    def test_skips_node_modules_during_glob(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        pkg = root / "pkg"
        (pkg / "src").mkdir(parents=True)
        (pkg / "src" / "app.ts").write_text("export const app = 1;\n", encoding="utf-8")
        nm = pkg / "node_modules" / "huge" / "lib"
        nm.mkdir(parents=True)
        for index in range(500):
            (nm / f"file{index}.ts").write_text(f"export const f{index} = {index};\n", encoding="utf-8")

        t0 = time.perf_counter()
        found = _walk_glob_source_files(pkg, ["src/**/*.ts"])
        elapsed = time.perf_counter() - t0

        assert [path.name for path in found] == ["app.ts"]
        assert elapsed < 0.5


class TestGitDiscovery:
    def setup_method(self) -> None:
        clear_git_index_cache()

    def test_git_lists_sources_in_repo(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git_repo(root)
        project = _write_ts_project(root, "packages/a")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        files = list_project_source_files(root, project)
        rels = {path.relative_to(root).as_posix() for path in files}
        assert "packages/a/src/index.ts" in rels

    def test_unversioned_uses_glob_in_git_repo(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git_repo(root)
        project = _write_ts_project(root, "packages/a")
        apply_metadata_updates(root, unversioned=True)
        assert is_versioned_repo(root)
        files = list_project_source_files(root, project)
        assert any(path.name == "index.ts" for path in files)

    def test_includes_untracked_non_ignored_file(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git_repo(root)
        project = _write_ts_project(root, "packages/a")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        (root / "packages/a/src/new.ts").write_text("export const n = 1;\n", encoding="utf-8")

        files = list_project_source_files(root, project)
        rels = {path.relative_to(root).as_posix() for path in files}
        assert "packages/a/src/new.ts" in rels

    def test_path_matches_tsconfig_for_deleted_file(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        tsconfig = root / "pkg" / "tsconfig.json"
        tsconfig.parent.mkdir(parents=True)
        tsconfig.write_text('{"include": ["src/**/*.ts"]}', encoding="utf-8")
        assert path_matches_tsconfig_shard(root, tsconfig, "pkg/src/gone.ts")
