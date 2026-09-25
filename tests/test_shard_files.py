"""Tests for git-delta partial reindex scope."""

import sqlite3
import subprocess
from pathlib import Path

from scip_cli.indexing.git_delta import git_index_delta
from scip_cli.indexing.shard_files import (
    PartialReindexPlan,
    expand_reindex_paths,
    resolve_partial_reindex_plan,
)
from scip_cli.indexing.shards import shard_entry_for_project
from tests.analyze_db import AnalyzeDbBuilder


def _init_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)


def _write_ts_project(root: Path, rel_dir: str) -> Path:
    project = root / rel_dir
    project.mkdir(parents=True, exist_ok=True)
    (project / "tsconfig.json").write_text('{"include": ["src/**/*.ts"]}', encoding="utf-8")
    src = project / "src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "lib.ts").write_text("export const lib = 1;\n", encoding="utf-8")
    (src / "main.ts").write_text("import { lib } from './lib';\nexport const main = lib;\n", encoding="utf-8")
    return Path(f"{rel_dir}/tsconfig.json")


class TestPartialReindexPlan:
    def test_resolve_from_git_delta(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "pkg")
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        from scip_cli.indexing.git_delta import git_head

        entry = shard_entry_for_project(root, project)
        commit = git_head(root)
        builder = AnalyzeDbBuilder()
        builder.add_file("pkg/src/lib.ts")
        builder.add_file("pkg/src/main.ts")
        builder.conn.commit()
        index_db = tmp_path / "index.db"
        disk = sqlite3.connect(index_db)
        builder.conn.backup(disk)
        disk.close()
        (root / "pkg/src/lib.ts").write_text("export const lib = 2;\n", encoding="utf-8")
        delta = git_index_delta(root, commit)
        plan = resolve_partial_reindex_plan(root, project, entry, index_db, delta)
        assert plan is not None
        assert "pkg/src/lib.ts" in plan.index_paths

    def test_expand_reindex_paths_includes_importers(self, tmp_path):
        builder = AnalyzeDbBuilder()
        lib_sym = builder.define("pkg/src/lib.ts", "lib")
        _main_doc, main_chunk = builder.add_file("pkg/src/main.ts")
        builder.conn.execute(
            "INSERT INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 0)",
            (main_chunk, lib_sym),
        )
        builder.conn.commit()
        db_path = tmp_path / "shard.db"
        disk = sqlite3.connect(db_path)
        builder.conn.backup(disk)
        disk.close()

        scope = expand_reindex_paths(
            db_path,
            dirty_paths=("pkg/src/lib.ts",),
            shard_paths=frozenset({"pkg/src/lib.ts", "pkg/src/main.ts"}),
        )
        assert scope == ("pkg/src/lib.ts", "pkg/src/main.ts")

    def test_resolve_partial_skips_excluded_dirty_and_importers(self, tmp_path):
        root = tmp_path / "repo"
        root.mkdir()
        _init_git(root)
        project = _write_ts_project(root, "pkg")
        (root / "pkg/src/lib.test.ts").write_text(
            "import { lib } from './lib';\nexport const t = lib;\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
        from scip_cli.indexing.git_delta import git_head

        entry = shard_entry_for_project(root, project)
        commit = git_head(root)
        builder = AnalyzeDbBuilder()
        lib_sym = builder.define("pkg/src/lib.ts", "lib")
        _main_doc, main_chunk = builder.add_file("pkg/src/main.ts")
        _test_doc, test_chunk = builder.add_file("pkg/src/lib.test.ts")
        builder.conn.execute(
            "INSERT INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 0)",
            (main_chunk, lib_sym),
        )
        builder.conn.execute(
            "INSERT INTO mentions (chunk_id, symbol_id, role) VALUES (?, ?, 0)",
            (test_chunk, lib_sym),
        )
        builder.conn.commit()
        index_db = tmp_path / "index.db"
        disk = sqlite3.connect(index_db)
        builder.conn.backup(disk)
        disk.close()

        (root / "pkg/src/lib.ts").write_text("export const lib = 2;\n", encoding="utf-8")
        delta = git_index_delta(root, commit)
        plan = resolve_partial_reindex_plan(
            root,
            project,
            entry,
            index_db,
            delta,
            exclude_globs=("**/*.test.ts",),
        )
        assert plan is not None
        assert plan.index_paths == ("pkg/src/lib.ts", "pkg/src/main.ts")

        subprocess.run(["git", "add", "pkg/src/lib.ts"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "lib"], cwd=root, check=True, capture_output=True)
        from scip_cli.indexing.git_delta import clear_git_delta_cache, git_head

        commit = git_head(root)
        clear_git_delta_cache()
        (root / "pkg/src/lib.test.ts").write_text(
            "import { lib } from './lib';\nexport const t = lib + 1;\n",
            encoding="utf-8",
        )
        delta = git_index_delta(root, commit)
        plan = resolve_partial_reindex_plan(
            root,
            project,
            entry,
            index_db,
            delta,
            exclude_globs=("**/*.test.ts",),
        )
        assert plan == PartialReindexPlan(index_paths=(), remove_paths=frozenset())
