"""Tests for per-tsconfig shard fingerprints and incremental reindex."""

import sqlite3
from pathlib import Path

from scip_cli.indexing.core import indexer_env
from scip_cli.indexing.shards import (
    clear_shard_cache,
    compute_shard_fingerprint,
    load_shard_manifest,
    manifest_path,
    resolve_cached_shard_db,
    save_shard_manifest,
    shard_db_path,
    shard_key,
    ts_build_info_dir,
)


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


class TestTsBuildInfoDir:
    def test_lives_under_cache_dir(self, tmp_path):
        cache_dir = tmp_path / "cache"
        assert ts_build_info_dir(cache_dir) == cache_dir / "tsbuildinfo"


class TestTypescriptIndexArgs:
    def test_incremental_passes_tsc_flags(self, tmp_path):
        from scip_cli.indexing.typescript import _typescript_index_args

        cache_dir = tmp_path / "cache"
        args = _typescript_index_args(
            tmp_path,
            tmp_path / "out.scip",
            [Path("pkg/tsconfig.json")],
            cache_dir=cache_dir,
            tsc_incremental=True,
        )
        assert "--incremental" in args
        assert "--ts-build-info-dir" in args
        assert str(ts_build_info_dir(cache_dir)) in args

    def test_full_reindex_omits_tsc_flags(self, tmp_path):
        from scip_cli.indexing.typescript import _typescript_index_args

        args = _typescript_index_args(
            tmp_path,
            tmp_path / "out.scip",
            [Path("pkg/tsconfig.json")],
            tsc_incremental=False,
        )
        assert "--incremental" not in args
        assert "--ts-build-info-dir" not in args


class TestShardFingerprint:
    def test_fingerprint_stable_for_same_tree(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        project = _write_ts_project(root, "packages/a")
        first = compute_shard_fingerprint(root, project)
        second = compute_shard_fingerprint(root, project)
        assert first == second

    def test_fingerprint_changes_when_source_changes(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        project = _write_ts_project(root, "packages/a")
        before = compute_shard_fingerprint(root, project)
        (root / "packages/a/src/index.ts").write_text("export const x = 2;\n", encoding="utf-8")
        after = compute_shard_fingerprint(root, project)
        assert before != after

    def test_fingerprint_changes_with_exclude_globs(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        project = _write_ts_project(root, "packages/a")
        plain = compute_shard_fingerprint(root, project)
        with_exclude = compute_shard_fingerprint(root, project, exclude_globs=("**/*.test.ts",))
        assert plain != with_exclude


class TestShardManifest:
    def test_save_and_load_round_trip(self, tmp_path):
        cache_dir = tmp_path / "cache"
        shards = {
            "pkg/tsconfig.json": {
                "fingerprint": "abc",
                "part_db": "shards/pkg__tsconfig.json.db",
            }
        }
        save_shard_manifest(cache_dir, shards)
        assert load_shard_manifest(cache_dir) == shards

    def test_save_merges_with_existing_manifest(self, tmp_path):
        cache_dir = tmp_path / "cache"
        save_shard_manifest(
            cache_dir,
            {
                "a/tsconfig.json": {"fingerprint": "1", "part_db": "shards/a.db"},
            },
        )
        save_shard_manifest(
            cache_dir,
            {
                "b/tsconfig.json": {"fingerprint": "2", "part_db": "shards/b.db"},
            },
        )
        manifest = load_shard_manifest(cache_dir)
        assert manifest["a/tsconfig.json"]["fingerprint"] == "1"
        assert manifest["b/tsconfig.json"]["fingerprint"] == "2"

    def test_clear_shard_cache_removes_manifest(self, tmp_path):
        cache_dir = tmp_path / "cache"
        save_shard_manifest(cache_dir, {"a": {"fingerprint": "x", "part_db": "shards/a.db"}})
        shard_db_path(cache_dir, Path("a")).parent.mkdir(parents=True, exist_ok=True)
        shard_db_path(cache_dir, Path("a")).write_text("db", encoding="utf-8")
        clear_shard_cache(cache_dir)
        assert not manifest_path(cache_dir).exists()
        assert not shard_db_path(cache_dir, Path("a")).exists()


class TestResolveCachedShard:
    def test_returns_db_when_fingerprint_matches(self, tmp_path):
        cache_dir = tmp_path / "cache"
        project = Path("pkg/tsconfig.json")
        db = shard_db_path(cache_dir, project)
        db.parent.mkdir(parents=True, exist_ok=True)
        db.write_bytes(b"sqlite")
        manifest = {
            shard_key(project): {
                "fingerprint": "deadbeef",
                "part_db": f"shards/{db.name}",
            }
        }
        resolved = resolve_cached_shard_db(cache_dir, project, "deadbeef", manifest)
        assert resolved == db

    def test_returns_none_when_fingerprint_differs(self, tmp_path):
        cache_dir = tmp_path / "cache"
        project = Path("pkg/tsconfig.json")
        db = shard_db_path(cache_dir, project)
        db.parent.mkdir(parents=True, exist_ok=True)
        db.write_bytes(b"sqlite")
        manifest = {
            shard_key(project): {
                "fingerprint": "old",
                "part_db": f"shards/{db.name}",
            }
        }
        assert resolve_cached_shard_db(cache_dir, project, "new", manifest) is None


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
    def test_warm_run_skips_indexer(self, tmp_path, monkeypatch):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "package.json").write_text("{}", encoding="utf-8")
        _write_ts_project(root, "packages/a")
        _write_ts_project(root, "packages/b", source="export const y = 1;\n")
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
            cache_dir=None,
            tsc_incremental=False,
        ):
            calls.append(list(batch))
            db = Path(output_db) if output_db is not None else Path(work_dir) / "index.db"
            label = batch[0].as_posix()
            _write_mergeable_shard_db(db, f"{label}/src/index.ts")
            return label, db, None

        monkeypatch.setattr(
            "scip_cli.indexing.typescript.index_ts_projects",
            fake_index_ts_projects,
        )
        from scip_cli.indexing.typescript import index_typescript

        env = indexer_env(root)
        index_typescript(root, cache_dir, projects, env, replace=True, incremental=True)
        assert len(calls) == 2

        calls.clear()
        index_typescript(root, cache_dir, projects, env, replace=True, incremental=True)
        assert calls == []
