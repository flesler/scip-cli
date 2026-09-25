"""Tests for git commit-anchored incremental change detection."""

import sqlite3
import subprocess
from pathlib import Path

from scip_cli.cache import get_cache_dir, index_db_path, promote_next_index
from scip_cli.exclude import filter_excluded_paths, save_persisted_exclude_globs
from scip_cli.indexing.git_delta import (
    clear_git_delta_cache,
    git_index_delta,
    shard_dirty_paths,
)
from scip_cli.indexing.incremental import index_typescript_incremental
from scip_cli.indexing.shards import (
    load_manifest_data,
    save_shard_manifest,
    shard_entry_for_project,
    shard_is_clean,
    shard_key,
)
from tests.test_incremental_shards import _MERGEABLE_SCHEMA, _write_mergeable_shard_db


def _write_index_db_with_symbols(path: Path, docs: dict[str, str]) -> None:
    """Minimal mergeable index.db: relative_path -> global symbol id string."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(_MERGEABLE_SCHEMA)
    for doc_id, (rel_path, symbol) in enumerate(docs.items(), start=1):
        conn.execute("INSERT INTO documents (id, relative_path) VALUES (?, ?)", (doc_id, rel_path))
        conn.execute(
            "INSERT INTO chunks (id, document_id, chunk_index, start_line, end_line, occurrences) "
            "VALUES (?, ?, 0, 0, 1, X'')",
            (doc_id, doc_id),
        )
        conn.execute(
            "INSERT INTO global_symbols (id, symbol, display_name, kind) VALUES (?, ?, ?, 0)",
            (doc_id, symbol, symbol),
        )
        conn.execute(
            "INSERT INTO defn_enclosing_ranges "
            "(id, document_id, symbol_id, start_line, start_char, end_line, end_char) "
            "VALUES (?, ?, ?, 0, 0, 1, 0)",
            (doc_id, doc_id, doc_id),
        )
        conn.execute("INSERT INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 1)", (doc_id, doc_id))
    conn.commit()
    conn.close()


def _db_paths_and_symbols(db_path: Path) -> tuple[set[str], set[str]]:
    conn = sqlite3.connect(db_path)
    paths = {row[0] for row in conn.execute("SELECT relative_path FROM documents")}
    symbols = {row[0] for row in conn.execute("SELECT symbol FROM global_symbols")}
    conn.close()
    return paths, symbols


def _init_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)


def _write_ts_project(root: Path, rel_dir: str, *, source: str = "export const x = 1;\n") -> Path:
    project = root / rel_dir
    project.mkdir(parents=True, exist_ok=True)
    (project / "tsconfig.json").write_text('{"include": ["src/**/*.ts"]}', encoding="utf-8")
    src = project / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "index.ts").write_text(source, encoding="utf-8")
    return Path(f"{rel_dir}/tsconfig.json")


def _seed_manifest(root: Path, project: Path) -> tuple[Path, str]:
    cache_dir = get_cache_dir(root)
    save_shard_manifest(
        cache_dir,
        {project.as_posix(): shard_entry_for_project(root, project)},
        project_root=root,
    )
    _, commit = load_manifest_data(cache_dir)
    assert commit is not None
    return cache_dir, commit


class TestGitDelta:
    def setup_method(self) -> None:
        clear_git_delta_cache()

    def test_delta_finds_untracked_file(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "packages/a")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        cache_dir, stored_commit = _seed_manifest(root, project)

        (root / "packages/a/src/new.ts").write_text("export const n = 1;\n", encoding="utf-8")
        delta = git_index_delta(root, stored_commit)
        modified, _removed = shard_dirty_paths(root, project, delta)
        assert "packages/a/src/new.ts" in modified

        manifest, commit = load_manifest_data(cache_dir)
        assert not shard_is_clean(root, project, manifest[project.as_posix()], commit, delta)

    def test_delta_finds_committed_file(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "packages/a")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        _cache_dir, stored_commit = _seed_manifest(root, project)

        (root / "packages/a/src/committed.ts").write_text("export const c = 1;\n", encoding="utf-8")
        subprocess.run(["git", "add", "packages/a/src/committed.ts"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add"], cwd=root, check=True, capture_output=True)

        delta = git_index_delta(root, stored_commit)
        modified, _ = shard_dirty_paths(root, project, delta)
        assert "packages/a/src/committed.ts" in modified

    def test_git_mv_without_no_renames_omits_old_path_from_deletions(self, tmp_path):
        """Default git rename folding hides the old path from --diff-filter=D."""
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        (root / "a.ts").write_text("export const x = 1;\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "mv", "a.ts", "b.ts"], cwd=root, check=True, capture_output=True)

        proc = subprocess.run(
            ["git", "-C", str(root), "diff", "--cached", "--name-only", "-z", "--diff-filter=D"],
            capture_output=True,
            check=True,
        )
        assert proc.stdout == b""
        proc_nr = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "diff",
                "--cached",
                "--name-only",
                "-z",
                "--no-renames",
                "--diff-filter=D",
            ],
            capture_output=True,
            check=True,
        )
        assert proc_nr.stdout == b"a.ts\x00"

    def test_rename_is_delete_plus_add(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "packages/a")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        _, stored_commit = _seed_manifest(root, project)

        subprocess.run(
            ["git", "mv", "packages/a/src/index.ts", "packages/a/src/renamed.ts"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        delta = git_index_delta(root, stored_commit)
        assert "packages/a/src/index.ts" in delta.removed
        assert "packages/a/src/renamed.ts" in delta.added_or_modified

    def test_deletion_tracked(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "packages/a")
        (root / "packages/a/src/extra.ts").write_text("export const e = 1;\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        _, stored_commit = _seed_manifest(root, project)

        (root / "packages/a/src/extra.ts").unlink()
        subprocess.run(["git", "add", "packages/a/src/extra.ts"], cwd=root, check=True, capture_output=True)

        delta = git_index_delta(root, stored_commit)
        modified, removed = shard_dirty_paths(root, project, delta)
        assert "packages/a/src/extra.ts" in removed
        assert "packages/a/src/extra.ts" not in modified

    def test_clean_shard_when_no_changes(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "packages/a")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        cache_dir, commit = _seed_manifest(root, project)
        manifest, _ = load_manifest_data(cache_dir)
        delta = git_index_delta(root, commit)
        assert shard_is_clean(root, project, manifest[project.as_posix()], commit, delta)

    def test_incremental_warm_reindexes_shard_when_new_file_added(self, tmp_path, monkeypatch):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "package.json").write_text("{}", encoding="utf-8")
        _init_git(root)
        project = _write_ts_project(root, "packages/a")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

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
            _write_mergeable_shard_db(db, "packages/a/src/index.ts")
            return batch[0].as_posix(), db, None

        monkeypatch.setattr("scip_cli.indexing.ts_projects.index_ts_projects", fake_index_ts_projects)

        from scip_cli.indexing.core import indexer_env

        env = indexer_env(root)
        projects = [project]
        _db, reindexed, _, _, promote = index_typescript_incremental(root, cache_dir, projects, env, replace=True)
        assert promote is True
        assert reindexed == 1
        promote_next_index(cache_dir)
        assert index_db_path(cache_dir).is_file()

        manifest, commit = load_manifest_data(cache_dir)
        delta = git_index_delta(root, commit)
        assert shard_is_clean(root, project, manifest[shard_key(project)], commit, delta)
        assert len(calls) == 1

        (root / "packages/a/src/new.ts").write_text("export const n = 1;\n", encoding="utf-8")
        clear_git_delta_cache()
        delta = git_index_delta(root, commit)
        assert not shard_is_clean(root, project, manifest[shard_key(project)], commit, delta)

        calls.clear()
        _db, reindexed, _, _, promote = index_typescript_incremental(root, cache_dir, projects, env, replace=False)
        assert reindexed == 1
        assert len(calls) == 1

    def test_incremental_removes_deleted_file_and_symbols(self, tmp_path, monkeypatch):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "package.json").write_text("{}", encoding="utf-8")
        _init_git(root)
        project = _write_ts_project(root, "packages/a")
        (root / "packages/a/src/extra.ts").write_text("export const extra = 1;\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        cache_dir = tmp_path / "cache"
        calls: list[tuple[tuple[str, ...] | None,]] = []

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
            calls.append((index_files,))
            db = Path(output_db) if output_db is not None else Path(work_dir) / "index.db"
            paths = index_files or (
                "packages/a/src/index.ts",
                "packages/a/src/extra.ts",
            )
            _write_index_db_with_symbols(
                db,
                {p: f"sym:{Path(p).stem}" for p in paths},
            )
            return batch[0].as_posix(), db, None

        monkeypatch.setattr("scip_cli.indexing.ts_projects.index_ts_projects", fake_index_ts_projects)

        from scip_cli.indexing.core import indexer_env

        env = indexer_env(root)
        projects = [project]
        index_typescript_incremental(root, cache_dir, projects, env, replace=True)
        promote_next_index(cache_dir)
        live = index_db_path(cache_dir)
        paths, symbols = _db_paths_and_symbols(live)
        assert paths == {"packages/a/src/index.ts", "packages/a/src/extra.ts"}
        assert symbols == {"sym:index", "sym:extra"}

        (root / "packages/a/src/extra.ts").unlink()
        subprocess.run(["git", "add", "packages/a/src/extra.ts"], cwd=root, check=True, capture_output=True)
        calls.clear()

        index_typescript_incremental(root, cache_dir, projects, env, replace=False)
        paths, symbols = _db_paths_and_symbols(live)
        assert paths == {"packages/a/src/index.ts"}
        assert symbols == {"sym:index"}
        assert calls == []

    def test_incremental_rename_removes_old_file_and_symbols(self, tmp_path, monkeypatch):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "package.json").write_text("{}", encoding="utf-8")
        _init_git(root)
        project = _write_ts_project(root, "packages/a")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        cache_dir = tmp_path / "cache"
        calls: list[tuple[tuple[str, ...] | None,]] = []

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
            calls.append((index_files,))
            db = Path(output_db) if output_db is not None else Path(work_dir) / "index.db"
            paths = index_files or ("packages/a/src/index.ts",)
            _write_index_db_with_symbols(
                db,
                {p: f"sym:{Path(p).stem}" for p in paths},
            )
            return batch[0].as_posix(), db, None

        monkeypatch.setattr("scip_cli.indexing.ts_projects.index_ts_projects", fake_index_ts_projects)

        from scip_cli.indexing.core import indexer_env

        env = indexer_env(root)
        projects = [project]
        index_typescript_incremental(root, cache_dir, projects, env, replace=True)
        promote_next_index(cache_dir)
        live = index_db_path(cache_dir)

        subprocess.run(
            ["git", "mv", "packages/a/src/index.ts", "packages/a/src/renamed.ts"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        calls.clear()

        index_typescript_incremental(root, cache_dir, projects, env, replace=False)
        paths, symbols = _db_paths_and_symbols(live)
        assert "packages/a/src/index.ts" not in paths
        assert "sym:index" not in symbols
        assert "packages/a/src/renamed.ts" in paths
        assert "sym:renamed" in symbols
        assert calls == [(("packages/a/src/renamed.ts",),)]

    def test_incremental_honors_exclude_globs_for_files_scope(self, tmp_path, monkeypatch):
        root = tmp_path / "repo"
        root.mkdir()
        (root / "package.json").write_text("{}", encoding="utf-8")
        _init_git(root)
        project = _write_ts_project(root, "packages/a")
        (root / "packages/a/src/widget.test.ts").write_text(
            "export const widget = 1;\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        save_persisted_exclude_globs(root, ["**/*.test.ts"])

        cache_dir = tmp_path / "cache"
        calls: list[tuple[tuple[str, ...] | None,]] = []
        exclude = ("**/*.test.ts",)

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
            calls.append((index_files, exclude_globs))
            db = Path(output_db) if output_db is not None else Path(work_dir) / "index.db"
            paths = filter_excluded_paths(
                index_files
                or (
                    "packages/a/src/index.ts",
                    "packages/a/src/widget.test.ts",
                ),
                exclude_globs,
            )
            _write_index_db_with_symbols(
                db,
                {p: f"sym:{Path(p).stem}" for p in paths},
            )
            return batch[0].as_posix(), db, None

        monkeypatch.setattr("scip_cli.indexing.ts_projects.index_ts_projects", fake_index_ts_projects)

        from scip_cli.indexing.core import indexer_env

        env = indexer_env(root)
        projects = [project]
        index_typescript_incremental(
            root,
            cache_dir,
            projects,
            env,
            replace=True,
            exclude_globs=exclude,
        )
        promote_next_index(cache_dir)
        live = index_db_path(cache_dir)
        paths, _symbols = _db_paths_and_symbols(live)
        assert "packages/a/src/widget.test.ts" not in paths

        (root / "packages/a/src/widget.test.ts").write_text(
            "export const widget = 2;\n",
            encoding="utf-8",
        )
        calls.clear()
        index_typescript_incremental(
            root,
            cache_dir,
            projects,
            env,
            replace=False,
            exclude_globs=exclude,
        )
        assert calls == []

        (root / "packages/a/src/index.ts").write_text("export const x = 2;\n", encoding="utf-8")
        calls.clear()
        index_typescript_incremental(
            root,
            cache_dir,
            projects,
            env,
            replace=False,
            exclude_globs=exclude,
        )
        assert calls == [(("packages/a/src/index.ts",), exclude)]
