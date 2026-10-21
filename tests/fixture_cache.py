"""Reuse indexed TS fixture trees across pytest runs (stable path under $TMPDIR)."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from scip_cli.cache import find_db, index_db_path, promote_next_index
from scip_cli.indexing.core import indexer_env
from scip_cli.indexing.typescript import index_typescript, typescript_projects
from tests.e2e_harness import IndexedFixture, index_fixture_project


@lru_cache(maxsize=16)
def _fixture_tree_digest(fixture_root: Path) -> str:
    root = fixture_root.resolve()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _exclude_tag(exclude_globs: tuple[str, ...]) -> str:
    if not exclude_globs:
        return "none"
    payload = "\n".join(exclude_globs).encode()
    return hashlib.sha256(payload).hexdigest()[:8]


def _tmpdir_fixture_base() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / "scip-fixture"


def cached_fixture_workspace(
    fixture_root: Path,
    *,
    cache_key: str,
    exclude_globs: tuple[str, ...] = (),
) -> Path:
    """Stable workspace under $TMPDIR/scip-fixture (same area pytest used for session copies)."""
    digest = _fixture_tree_digest(fixture_root)
    tag = _exclude_tag(exclude_globs)
    return _tmpdir_fixture_base() / f"{cache_key}-{digest}-{tag}"


def prepare_cached_indexed_fixture(
    fixture_root: Path,
    *,
    cache_key: str,
    exclude_globs: tuple[str, ...] = (),
) -> IndexedFixture:
    """Copy fixture once per content/exclude variant; index once per stable workspace root."""
    workspace = cached_fixture_workspace(fixture_root, cache_key=cache_key, exclude_globs=exclude_globs)
    ready = workspace / ".ready"
    db_path = find_db(workspace)
    if ready.is_file() and db_path is not None:
        return IndexedFixture(root=workspace, db_path=db_path)

    if workspace.is_dir():
        shutil.rmtree(workspace)
    shutil.copytree(fixture_root, workspace)
    try:
        db_path = index_fixture_project(workspace, exclude_globs=exclude_globs)
    except RuntimeError:
        if workspace.is_dir():
            shutil.rmtree(workspace, ignore_errors=True)
        raise
    ready.write_text("1", encoding="utf-8")
    return IndexedFixture(root=workspace, db_path=db_path)


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def prepare_incremental_bench_warmed(fixture_source: Path) -> tuple[Path, Path]:
    """Git + two warm incremental indexes under $TMPDIR/scip-fixture (read-only template for tests)."""
    digest = _fixture_tree_digest(fixture_source)
    base = _tmpdir_fixture_base()
    work = base / f"incremental-bench-{digest}"
    cache_dir = base / f"incremental-bench-cache-{digest}"
    ready = cache_dir / ".incremental-warm-ready"
    if ready.is_file() and work.is_dir() and index_db_path(cache_dir).is_file():
        return work, cache_dir

    if work.is_dir():
        shutil.rmtree(work)
    if cache_dir.is_dir():
        shutil.rmtree(cache_dir)
    shutil.copytree(fixture_source, work)
    _init_git_repo(work)

    env = indexer_env(work)
    projects = typescript_projects(work)
    for _ in range(2):
        _db, _, _, _, promote = index_typescript(work, cache_dir, projects, env, replace=True, incremental=True)
        if promote:
            promote_next_index(cache_dir)

    ready.write_text("1", encoding="utf-8")
    return work, cache_dir
