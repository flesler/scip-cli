"""Tests for reindex command."""

import contextlib
from argparse import Namespace

import pytest

from scip_cli.commands import reindex
from scip_cli.project import Language
from scip_cli.scope import load_index_scope, save_index_scope


def test_full_reindex_clears_persisted_scope(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")
    save_index_scope(root, ["packages/api"])

    def fake_get_cache_dir(project_root):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def fake_index_project(_root, _lang, cache_dir, *, replace=False, log=True):
        db = cache_dir / ("index.db.next" if replace else "index.db")
        db.write_text("sqlite", encoding="utf-8")
        return db, 0, 1

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.TYPESCRIPT))
    monkeypatch.setattr(reindex, "get_cache_dir", fake_get_cache_dir)
    monkeypatch.setattr(reindex, "index_build_lock", lambda _cache: contextlib.nullcontext())
    monkeypatch.setattr(reindex, "cleanup_in_progress_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "index_project", fake_index_project)
    monkeypatch.setattr(reindex, "promote_next_index", lambda _cache: None)
    monkeypatch.setattr(reindex, "log_index_complete", lambda *_a, **_k: None)

    reindex.main(Namespace(path=None))

    assert load_index_scope(root) is None


def test_reindex_path_rejected_for_python(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.PYTHON))

    with pytest.raises(SystemExit) as exc:
        reindex.main(Namespace(path=["src"]))
    assert exc.value.code == 1


def test_reindex_rejects_empty_path(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "package.json").write_text("{}", encoding="utf-8")

    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.TYPESCRIPT))

    with pytest.raises(SystemExit) as exc:
        reindex.main(Namespace(path=[""]))
    assert exc.value.code == 1
    assert load_index_scope(root) is None


def _stub_index(tmp_path, monkeypatch, root, lang):
    def fake_get_cache_dir(project_root):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def fake_index_project(_root, _lang, cache_dir, *, replace=False, log=True):
        db = cache_dir / ("index.db.next" if replace else "index.db")
        db.write_text("sqlite", encoding="utf-8")
        return db, 0, 1

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
    reindex.main(Namespace(path=None, tsconfig=["pkg/tsconfig.*.json"]))

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
        reindex.main(Namespace(path=["pkg"], tsconfig=["pkg/tsconfig.*.json"]))
    assert exc.value.code == 1


def test_reindex_tsconfig_rejected_for_python(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(reindex, "find_project_root_and_language", lambda: (root, Language.PYTHON))

    with pytest.raises(SystemExit) as exc:
        reindex.main(Namespace(path=None, tsconfig=["tsconfig.app.json"]))
    assert exc.value.code == 1
