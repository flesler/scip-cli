"""Tests for reindex command."""

import argparse
import contextlib
import sqlite3
from argparse import Namespace
from pathlib import Path

import pytest

from scip_cli.commands import reindex
from scip_cli.exclude import load_persisted_exclude_globs, save_persisted_exclude_globs
from scip_cli.indexing.shards import manifest_path
from scip_cli.project import Language
from scip_cli.scope import load_index_scope, save_index_scope


def _write_minimal_index_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        path.unlink()
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t(x)")
    conn.close()


def _reindex_namespace(**kwargs):
    defaults = {
        "path": None,
        "tsconfig": None,
        "exclude": None,
        "fresh": False,
        "no_incremental": False,
        "unversioned": False,
        "with_external": False,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


def test_reindex_exclude_argparse_bare_flag():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exclude", action="append", nargs="*", default=None)
    assert parser.parse_args([]).exclude is None
    assert parser.parse_args(["--exclude"]).exclude == [[]]
    assert parser.parse_args(["--exclude", "tests/**"]).exclude == [["tests/**"]]
    assert parser.parse_args(["--exclude", "a", "b"]).exclude == [["a", "b"]]
    assert parser.parse_args(["--exclude", "foo", "--exclude"]).exclude == [["foo"], []]


def test_reindex_preserves_persisted_metadata(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    save_index_scope(root, ["packages/api"])
    save_persisted_exclude_globs(root, ["tests/**"])

    def fake_get_cache_dir(project_root):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def fake_index_project(_root, _lang, cache_dir, *, replace=False, log=True, incremental=False):
        db = cache_dir / ("index.db.next" if replace else "index.db")
        _write_minimal_index_db(db)
        return db, 0, 1, True

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.TYPESCRIPT))
    monkeypatch.setattr(reindex, "get_cache_dir", fake_get_cache_dir)
    monkeypatch.setattr(reindex, "index_build_lock", lambda _cache: contextlib.nullcontext())
    monkeypatch.setattr(reindex, "cleanup_in_progress_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "index_project", fake_index_project)
    monkeypatch.setattr(reindex, "promote_next_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "log_index_complete", lambda *_a, **_k: None)

    reindex.main(_reindex_namespace())

    scope = load_index_scope(root)
    assert scope is not None
    assert scope.paths == ("packages/api",)
    assert load_persisted_exclude_globs(root) == ("tests/**",)


def test_fresh_reindex_with_path_clears_exclude(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    save_persisted_exclude_globs(root, ["tests/**"])

    _stub_index(tmp_path, monkeypatch, root, Language.TYPESCRIPT)
    reindex.main(_reindex_namespace(fresh=True, path=["packages/api"]))

    scope = load_index_scope(root)
    assert scope is not None
    assert scope.paths == ("packages/api",)
    assert load_persisted_exclude_globs(root) == ()


def test_fresh_reindex_clears_persisted_metadata(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    save_index_scope(root, ["packages/api"])
    save_persisted_exclude_globs(root, ["tests/**"])

    _stub_index(tmp_path, monkeypatch, root, Language.TYPESCRIPT)
    reindex.main(_reindex_namespace(fresh=True))

    assert load_index_scope(root) is None
    assert load_persisted_exclude_globs(root) == ()


def test_reindex_exclude_clears_persisted_exclude(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    save_persisted_exclude_globs(root, ["tests/**"])

    _stub_index(tmp_path, monkeypatch, root, Language.TYPESCRIPT)
    reindex.main(_reindex_namespace(exclude=[[]]))

    assert load_persisted_exclude_globs(root) == ()


def test_reindex_exclude_replaces_persisted_exclude(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    save_persisted_exclude_globs(root, ["tests/**"])

    _stub_index(tmp_path, monkeypatch, root, Language.TYPESCRIPT)
    reindex.main(_reindex_namespace(exclude=[["**/*.spec.ts"]]))

    assert load_persisted_exclude_globs(root) == ("**/*.spec.ts",)


def test_reindex_path_rejected_for_python(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.PYTHON))

    with pytest.raises(SystemExit) as exc:
        reindex.main(_reindex_namespace(path=["src"]))
    assert exc.value.code == 1


def test_reindex_rejects_empty_path(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.TYPESCRIPT))

    with pytest.raises(SystemExit) as exc:
        reindex.main(_reindex_namespace(path=[""]))
    assert exc.value.code == 1
    assert load_index_scope(root) is None


def _stub_index(tmp_path, monkeypatch, root, lang):
    def fake_get_cache_dir(project_root):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def fake_index_project(_root, _lang, cache_dir, *, replace=False, log=True, incremental=False):
        db = cache_dir / ("index.db.next" if replace else "index.db")
        _write_minimal_index_db(db)
        return db, 0, 1, True

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, lang))
    monkeypatch.setattr(reindex, "get_cache_dir", fake_get_cache_dir)
    monkeypatch.setattr(reindex, "index_build_lock", lambda _cache: contextlib.nullcontext())
    monkeypatch.setattr(reindex, "cleanup_in_progress_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "index_project", fake_index_project)
    monkeypatch.setattr(reindex, "promote_next_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "log_index_complete", lambda *_a, **_k: None)


def test_reindex_tsconfig_glob_persists_files(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    app = root / "pkg" / "tsconfig.app.json"
    app.parent.mkdir(parents=True)
    app.write_text('{"include": ["src/**/*.ts"]}', encoding="utf-8")
    (root / "pkg" / "tsconfig.spec.json").write_text('{"include": ["lib/**/*.ts"]}', encoding="utf-8")
    (root / "pkg" / "tsconfig.json").write_text('{"include": ["**/*.ts"]}', encoding="utf-8")
    (root / "package.json").write_text("{}", encoding="utf-8")

    _stub_index(tmp_path, monkeypatch, root, Language.TYPESCRIPT)
    reindex.main(_reindex_namespace(tsconfig=["pkg/tsconfig.*.json"]))

    scope = load_index_scope(root)
    assert scope is not None
    assert scope.paths == ("pkg/tsconfig.app.json", "pkg/tsconfig.spec.json")


def test_reindex_rejects_path_and_tsconfig(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.TYPESCRIPT))

    with pytest.raises(SystemExit) as exc:
        reindex.main(_reindex_namespace(path=["pkg"], tsconfig=["pkg/tsconfig.*.json"]))
    assert exc.value.code == 1


def test_reindex_defaults_to_incremental_in_git_ts_repo(tmp_path, monkeypatch):
    import subprocess

    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

    cache_dir = tmp_path / "cache"
    calls: list[bool] = []

    def fake_index_project(_root, _lang, cache, *, replace=False, log=True, incremental=False):
        calls.append(incremental)
        if incremental:
            db = cache / "index.db"
            promote = False
        else:
            db = cache / ("index.db.next" if replace else "index.db")
            promote = replace
        _write_minimal_index_db(db)
        return db, 0, 1, promote

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.TYPESCRIPT))
    monkeypatch.setattr(reindex, "get_cache_dir", lambda _root: cache_dir)
    monkeypatch.setattr(reindex, "index_build_lock", lambda _cache: contextlib.nullcontext())
    monkeypatch.setattr(reindex, "cleanup_in_progress_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "index_project", fake_index_project)
    monkeypatch.setattr(reindex, "promote_next_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "log_index_complete", lambda *_a, **_k: None)

    reindex.main(_reindex_namespace())
    assert calls == [True]


def test_reindex_incremental_clears_shards_on_full_reindex(tmp_path, monkeypatch):
    import subprocess

    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path(cache_dir).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(cache_dir).write_text('{"version": 1, "shards": {}}', encoding="utf-8")

    calls: list[bool] = []

    def fake_index_project(_root, _lang, cache, *, replace=False, log=True, incremental=False):
        calls.append(incremental)
        db = cache / ("index.db.next" if replace else "index.db")
        _write_minimal_index_db(db)
        return db, 0, 1, True

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.TYPESCRIPT))
    monkeypatch.setattr(reindex, "get_cache_dir", lambda _root: cache_dir)
    monkeypatch.setattr(reindex, "index_build_lock", lambda _cache: contextlib.nullcontext())
    monkeypatch.setattr(reindex, "cleanup_in_progress_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "index_project", fake_index_project)
    monkeypatch.setattr(reindex, "promote_next_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "log_index_complete", lambda *_a, **_k: None)

    reindex.main(_reindex_namespace(no_incremental=True))
    assert calls == [False]
    assert not manifest_path(cache_dir).exists()

    manifest_path(cache_dir).parent.mkdir(parents=True, exist_ok=True)
    manifest_path(cache_dir).write_text('{"version": 1, "shards": {}}', encoding="utf-8")
    reindex.main(_reindex_namespace())
    assert calls == [False, True]


def test_reindex_falls_back_to_full_without_git(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    calls: list[bool] = []

    cache_dir = tmp_path / "cache"

    def fake_index_project(_root, _lang, cache, *, replace=False, log=True, incremental=False):
        calls.append(incremental)
        db = cache / ("index.db.next" if replace else "index.db")
        db.parent.mkdir(parents=True, exist_ok=True)
        _write_minimal_index_db(db)
        return db, 0, 1, replace

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.TYPESCRIPT))
    monkeypatch.setattr(reindex, "get_cache_dir", lambda _root: cache_dir)
    monkeypatch.setattr(reindex, "index_build_lock", lambda _cache: contextlib.nullcontext())
    monkeypatch.setattr(reindex, "cleanup_in_progress_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "index_project", fake_index_project)
    monkeypatch.setattr(reindex, "promote_next_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "log_index_complete", lambda *_a, **_k: None)

    reindex.main(_reindex_namespace())
    assert calls == [False]


def test_reindex_falls_back_to_full_for_python(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    calls: list[bool] = []

    cache_dir = tmp_path / "cache"

    def fake_index_project(_root, _lang, cache, *, replace=False, log=True, incremental=False):
        calls.append(incremental)
        db = cache / ("index.db.next" if replace else "index.db")
        db.parent.mkdir(parents=True, exist_ok=True)
        _write_minimal_index_db(db)
        return db, 0, 1, replace

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.PYTHON))
    monkeypatch.setattr(reindex, "get_cache_dir", lambda _root: cache_dir)
    monkeypatch.setattr(reindex, "index_build_lock", lambda _cache: contextlib.nullcontext())
    monkeypatch.setattr(reindex, "cleanup_in_progress_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "index_project", fake_index_project)
    monkeypatch.setattr(reindex, "promote_next_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "log_index_complete", lambda *_a, **_k: None)

    reindex.main(_reindex_namespace())
    assert calls == [False]


def test_reindex_fresh_disables_incremental(tmp_path, monkeypatch):
    import subprocess

    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    calls: list[bool] = []

    cache_dir = tmp_path / "cache"

    def fake_index_project(_root, _lang, cache, *, replace=False, log=True, incremental=False):
        calls.append(incremental)
        db = cache / ("index.db.next" if replace else "index.db")
        db.parent.mkdir(parents=True, exist_ok=True)
        _write_minimal_index_db(db)
        return db, 0, 1, replace

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.TYPESCRIPT))
    monkeypatch.setattr(reindex, "get_cache_dir", lambda _root: cache_dir)
    monkeypatch.setattr(reindex, "index_build_lock", lambda _cache: contextlib.nullcontext())
    monkeypatch.setattr(reindex, "cleanup_in_progress_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "index_project", fake_index_project)
    monkeypatch.setattr(reindex, "promote_next_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "log_index_complete", lambda *_a, **_k: None)

    reindex.main(_reindex_namespace(fresh=True))
    assert calls == [False]


def test_reindex_tsconfig_rejected_for_python(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.PYTHON))

    with pytest.raises(SystemExit) as exc:
        reindex.main(_reindex_namespace(tsconfig=["tsconfig.app.json"]))
    assert exc.value.code == 1
