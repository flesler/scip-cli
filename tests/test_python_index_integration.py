"""Integration tests for Python indexing orchestration (mocked indexers)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scip_cli.indexing import index_project
from scip_cli.project import Language


def _write_pyproject(path: Path, name: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n', encoding="utf-8")


@pytest.fixture
def python_monorepo(tmp_path):
    root = tmp_path / "repo"
    _write_pyproject(root, "root")
    _write_pyproject(root / "packages" / "api", "api")
    return root


def test_index_project_python_merges_nested_packages(python_monorepo, tmp_path, monkeypatch):
    """Two discovered packages produce one merged index.db."""
    cache_dir = tmp_path / "cache"
    calls: list[tuple[str, list[str]]] = []

    def fake_run(binary, args, cwd, env=None, **kwargs):
        calls.append((binary, list(args)))
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        output = next(arg for arg in args if arg.endswith(".scip"))
        Path(output).write_bytes(b"\x00")
        return result

    def fake_convert(scip_path, db_path, *, document_path_prefix=None):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, relative_path TEXT NOT NULL UNIQUE)")
        prefix = "" if document_path_prefix in (None, Path(".")) else f"{Path(document_path_prefix).as_posix()}/"
        conn.execute(
            "INSERT INTO documents (relative_path) VALUES (?)",
            (f"{prefix}pkg.py",),
        )
        conn.commit()
        conn.close()

    monkeypatch.setattr("scip_cli.indexing.languages.run_indexer_with_fallback", fake_run)
    monkeypatch.setattr("scip_cli.indexing.languages._convert_scip_to_db", fake_convert)
    monkeypatch.setattr(
        "scip_cli.indexing.orchestrate.merge_sqlite_indexes",
        lambda parts, out: _merge_fixture(parts, out),
    )

    output_db, skipped, total = index_project(
        python_monorepo,
        Language.PYTHON,
        cache_dir,
        replace=True,
        log=False,
    )

    assert total == 2
    assert skipped == 0
    assert output_db.is_file()
    assert len(calls) == 2
    assert all(call[0] == "scip-python" for call in calls)


def _merge_fixture(parts: list[Path], output_path: Path) -> None:
    import shutil
    import sqlite3

    output_path = Path(output_path)
    shutil.copyfile(parts[0], output_path)
    conn = sqlite3.connect(output_path)
    for part in parts[1:]:
        row = sqlite3.connect(part).execute("SELECT relative_path FROM documents").fetchone()
        if row:
            conn.execute("INSERT OR IGNORE INTO documents (relative_path) VALUES (?)", (row[0],))
    conn.commit()
    conn.close()
