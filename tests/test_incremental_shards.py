"""Tests for git-anchored shard manifest and incremental reindex."""

import sqlite3
import subprocess
from pathlib import Path

from scip_cli.indexing.core import indexer_env
from scip_cli.indexing.git_delta import clear_git_delta_cache, git_index_delta
from scip_cli.indexing.shards import (
    clear_shard_cache,
    load_manifest_data,
    load_shard_manifest,
    manifest_path,
    save_shard_manifest,
    shard_entry_for_project,
    shard_is_clean,
    shard_key,
    tsconfig_chain_digest,
)
from scip_cli.tsconfig import tsconfig_for_project


def _init_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)


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
    return Path(f"{rel_dir}/tsconfig.json")


class TestShardManifest:
    def test_save_and_load_round_trip(self, tmp_path):
        cache_dir = tmp_path / "cache"
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "pkg")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        entry = shard_entry_for_project(root, project)
        save_shard_manifest(cache_dir, {"pkg/tsconfig.json": entry}, project_root=root)
        loaded = load_shard_manifest(cache_dir)
        assert loaded["pkg/tsconfig.json"]["tsconfig_digest"] == entry["tsconfig_digest"]
        _, commit = load_manifest_data(cache_dir)
        assert commit is not None

    def test_save_merges_with_existing_manifest(self, tmp_path):
        cache_dir = tmp_path / "cache"
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        _write_ts_project(root, "a")
        _write_ts_project(root, "b")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        save_shard_manifest(
            cache_dir,
            {"a/tsconfig.json": shard_entry_for_project(root, Path("a/tsconfig.json"))},
            project_root=root,
        )
        save_shard_manifest(
            cache_dir,
            {"b/tsconfig.json": shard_entry_for_project(root, Path("b/tsconfig.json"))},
            project_root=root,
        )
        manifest = load_shard_manifest(cache_dir)
        assert "a/tsconfig.json" in manifest
        assert "b/tsconfig.json" in manifest

    def test_clear_shard_cache_removes_manifest(self, tmp_path):
        cache_dir = tmp_path / "cache"
        save_shard_manifest(cache_dir, {"a/tsconfig.json": {"tsconfig_digest": "x"}})
        clear_shard_cache(cache_dir)
        assert not manifest_path(cache_dir).exists()


class TestTsconfigDigest:
    def test_digest_changes_when_tsconfig_changes(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        project = _write_ts_project(root, "pkg")
        tsconfig = tsconfig_for_project(root, project)
        before = tsconfig_chain_digest(project, tsconfig)
        (root / "pkg/tsconfig.json").write_text(
            '{"include": ["src/**/*.ts"], "exclude": ["src/api/**"]}',
            encoding="utf-8",
        )
        after = tsconfig_chain_digest(project, tsconfig_for_project(root, project))
        assert before != after

    def test_shard_dirty_when_tsconfig_changes(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "pkg")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        entry = shard_entry_for_project(root, project)
        cache_dir = tmp_path / "cache"
        save_shard_manifest(cache_dir, {shard_key(project): entry}, project_root=root)
        _, commit = load_manifest_data(cache_dir)
        delta = git_index_delta(root, commit)
        assert shard_is_clean(root, project, entry, commit, delta)
        (root / "pkg/tsconfig.json").write_text(
            '{"include": ["src/**/*.ts"], "exclude": ["src/legacy/**"]}',
            encoding="utf-8",
        )
        assert not shard_is_clean(root, project, entry, commit, delta)

    def test_tsconfig_only_change_marks_shard_dirty(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "pkg")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        entry = shard_entry_for_project(root, project)
        cache_dir = tmp_path / "cache"
        save_shard_manifest(cache_dir, {shard_key(project): entry}, project_root=root)
        _, commit = load_manifest_data(cache_dir)
        delta = git_index_delta(root, commit)
        assert shard_is_clean(root, project, entry, commit, delta)

        (root / "pkg/tsconfig.json").write_text(
            '{"include": ["src/**/*.ts"], "exclude": ["src/legacy/**"]}',
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "pkg/tsconfig.json"], cwd=root, check=True, capture_output=True)
        clear_git_delta_cache()
        delta = git_index_delta(root, commit)
        assert not shard_is_clean(root, project, entry, commit, delta)


_MERGEABLE_SCHEMA = """
CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE
);
CREATE TABLE global_symbols (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    display_name TEXT,
    kind INTEGER
);
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    occurrences BLOB NOT NULL
);
CREATE TABLE mentions (
    chunk_id INTEGER NOT NULL,
    symbol_id INTEGER NOT NULL,
    role INTEGER NOT NULL
);
CREATE TABLE defn_enclosing_ranges (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    symbol_id INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    start_char INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    end_char INTEGER NOT NULL
);
"""


def _write_mergeable_shard_db(path: Path, doc_path: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_MERGEABLE_SCHEMA)
    conn.execute("INSERT INTO documents (relative_path) VALUES (?)", (doc_path,))
    conn.commit()
    conn.close()


class TestIndexTypescriptIncremental:
    def test_warm_run_skips_indexer_and_promote(self, tmp_path, monkeypatch):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "package.json").write_text("{}", encoding="utf-8")
        _init_git(root)
        _write_ts_project(root, "packages/a")
        _write_ts_project(root, "packages/b", source="export const y = 1;\n")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        projects = [
            Path("packages/a/tsconfig.json"),
            Path("packages/b/tsconfig.json"),
        ]
        cache_dir = tmp_path / "cache"
        calls: list[list[Path]] = []

        def fake_index_ts_projects(
            _root,
            batch,
            work_dir,
            _env,
            *,
            output_db=None,
            exclude_globs=(),
            index_files=None,
        ):
            calls.append(list(batch))
            db = Path(output_db) if output_db is not None else Path(work_dir) / "index.db"
            label = batch[0].as_posix()
            _write_mergeable_shard_db(db, f"{label}/src/index.ts")
            return label, db, None

        monkeypatch.setattr(
            "scip_cli.indexing.ts_projects.index_ts_projects",
            fake_index_ts_projects,
        )
        from scip_cli.cache import index_db_path, promote_next_index
        from scip_cli.indexing.typescript import index_typescript

        env = indexer_env(root)
        _db, _, _, _, promote = index_typescript(root, cache_dir, projects, env, replace=True, incremental=True)
        assert promote is True
        assert len(calls) == 2
        promote_next_index(cache_dir)
        assert index_db_path(cache_dir).is_file()

        calls.clear()
        db, _, _, _, promote = index_typescript(root, cache_dir, projects, env, replace=True, incremental=True)
        assert calls == []
        assert promote is False
        assert db == index_db_path(cache_dir)
