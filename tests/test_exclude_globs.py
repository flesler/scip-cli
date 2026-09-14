"""Tests for index-time exclude globs."""

import json
import shutil
import sqlite3

import pytest

from scip_cli.exclude import (
    path_matches_any_glob,
    path_matches_glob,
    resolve_exclude_globs,
    save_persisted_exclude_globs,
)
from scip_cli.indexing.postprocess import postprocess_index
from tests.e2e_harness import FIXTURE_ROOT, IndexedFixture, index_fixture_project, open_index_db, run_cli
from tests.fixture_catalog import (
    DEFAULT_TEST_EXCLUDE_GLOBS,
    EXCLUDE_SPEC_FILE,
    FN_FIXTURE_ONLY_HELPER,
    FN_GREET,
    HELPER_FILE,
)

pytestmark_integration = pytest.mark.integration


class TestPathMatchesGlob:
    def test_basename_pattern(self):
        assert path_matches_glob("src/foo.test.ts", "*.test.ts")
        assert path_matches_glob("src/foo.ts", "*.test.ts") is False

    def test_recursive_directory(self):
        assert path_matches_glob("src/__tests__/fixtureOnly.spec.ts", "**/__tests__/**")
        assert path_matches_glob("src/helper.ts", "**/__tests__/**") is False

    def test_full_path_pattern(self):
        assert path_matches_glob("tests/unit/a.ts", "tests/**")
        assert path_matches_glob("src/tests/unit/a.ts", "tests/**") is False

    def test_any_glob(self):
        patterns = ("**/*.spec.ts", "**/*.test.ts")
        assert path_matches_any_glob("src/widget.spec.ts", patterns)
        assert path_matches_any_glob("src/widget.ts", patterns) is False


class TestResolveExcludeGlobs:
    def test_merges_config_and_persisted(self, tmp_path):
        (tmp_path / ".scip-cli.json").write_text(
            json.dumps({"excludeGlobs": ["**/*.test.ts"]}),
            encoding="utf-8",
        )
        save_persisted_exclude_globs(tmp_path, ["**/__tests__/**"])
        assert resolve_exclude_globs(tmp_path) == ("**/*.test.ts", "**/__tests__/**")


class TestPruneExcludedDocuments:
    def test_removes_matching_documents_and_orphan_symbols(self, tmp_path):
        db_path = tmp_path / "index.db"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE
            );
            CREATE TABLE chunks (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                occurrences BLOB NOT NULL
            );
            CREATE TABLE global_symbols (
                id INTEGER PRIMARY KEY,
                symbol TEXT NOT NULL UNIQUE,
                display_name TEXT,
                kind INTEGER
            );
            CREATE TABLE mentions (
                chunk_id INTEGER NOT NULL,
                symbol_id INTEGER NOT NULL,
                role INTEGER NOT NULL,
                PRIMARY KEY (chunk_id, symbol_id, role)
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
            INSERT INTO documents VALUES (1, 'src/helper.ts'), (2, 'src/__tests__/fixtureOnly.spec.ts');
            INSERT INTO chunks VALUES (1, 1, 0, 0, 10, X''), (2, 2, 0, 0, 10, X'');
            INSERT INTO global_symbols VALUES
                (1, 'sym-greet', 'greet', 12),
                (2, 'sym-fixture', 'fixtureOnlyHelper', 12);
            INSERT INTO mentions VALUES (1, 1, 1), (2, 2, 1);
            INSERT INTO defn_enclosing_ranges VALUES
                (1, 1, 1, 0, 0, 5, 0),
                (2, 2, 2, 0, 0, 5, 0);
        """)
        conn.commit()
        conn.close()

        postprocess_index(db_path, exclude_globs=DEFAULT_TEST_EXCLUDE_GLOBS)

        conn = open_index_db(db_path)
        paths = {row[0] for row in conn.execute("SELECT relative_path FROM documents").fetchall()}
        symbols = {row[0] for row in conn.execute("SELECT display_name FROM global_symbols").fetchall()}
        conn.close()

        assert paths == {"src/helper.ts"}
        assert "greet" in symbols
        assert "fixtureOnlyHelper" not in symbols


@pytest.fixture
def excluded_fixture(tmp_path):
    root = tmp_path / "typescript-project"
    shutil.copytree(FIXTURE_ROOT, root)
    try:
        db_path = index_fixture_project(root, exclude_globs=DEFAULT_TEST_EXCLUDE_GLOBS)
    except RuntimeError as exc:
        pytest.skip(str(exc))
    return IndexedFixture(root=root, db_path=db_path)


class TestExcludeGlobsE2e:
    @pytestmark_integration
    def test_default_fixture_still_indexes_spec_file(self, indexed_fixture):
        conn = open_index_db(indexed_fixture.db_path)
        rows = conn.execute(
            "SELECT 1 FROM documents WHERE relative_path = ?",
            (EXCLUDE_SPEC_FILE,),
        ).fetchall()
        conn.close()
        assert rows

    @pytestmark_integration
    def test_excluded_index_omits_spec_file(self, excluded_fixture):
        conn = open_index_db(excluded_fixture.db_path)
        rows = conn.execute(
            "SELECT 1 FROM documents WHERE relative_path = ?",
            (EXCLUDE_SPEC_FILE,),
        ).fetchall()
        conn.close()
        assert not rows

    @pytestmark_integration
    def test_excluded_index_keeps_production_symbols(self, excluded_fixture):
        result = run_cli(["symbols", HELPER_FILE, "--limit", "10"], excluded_fixture)
        assert result.returncode == 0
        assert FN_GREET in result.stdout

    @pytestmark_integration
    def test_excluded_symbol_not_searchable(self, excluded_fixture):
        result = run_cli(["search", FN_FIXTURE_ONLY_HELPER, "--limit", "5"], excluded_fixture)
        assert result.returncode == 1
        assert FN_FIXTURE_ONLY_HELPER in result.stderr
