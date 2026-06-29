"""E2e analyze checks against real scip-typescript index of typescript-project patterns."""

import sqlite3

import pytest

from scip_cli.analyze import file as file_checks
from scip_cli.analyze import project as project_checks
from scip_cli.analyze.common import short_name
from tests.e2e_harness import open_index_db, run_cli
from tests.fixture_catalog import (
    CLASS_INFERENCE_CLIENT,
    FN_EVICT_ITEM,
    FN_LAZY_PANEL,
    FN_ORPHAN_WIDGET,
    FN_SEND,
    HOOK_A_FILE,
    HOOK_B_FILE,
    I18N_EN_FILE,
    I18N_INDEX_FILE,
    LAZY_PANEL_FILE,
    TYPE_A_FILE,
    TYPE_B_FILE,
    TYPE_BASE_STREAM,
    TYPE_BUTTON_PROPS,
    TYPE_LABEL_FUNC,
    TYPE_OPTS,
)

pytestmark = pytest.mark.integration


def _db(fixture) -> sqlite3.Connection:
    return open_index_db(fixture.db_path)


def _contains(lines: list[str], name: str) -> bool:
    return any(name in line for line in lines)


def _contains_path(lines: list[str], path: str) -> bool:
    return any(path in line for line in lines)


class TestAnalyzePatternsE2E:
    def test_lazy_default_export_not_dead(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            dead = project_checks.dead_exports(db, limit=50)
            assert not _contains(dead, FN_LAZY_PANEL)
            in_file = file_checks.dead_in_file(db, LAZY_PANEL_FILE, limit=20)
            assert not _contains(in_file, FN_LAZY_PANEL)
        finally:
            db.close()

    def test_object_alias_export_not_dead(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            dead = project_checks.dead_exports(db, limit=50)
            assert not _contains(dead, FN_EVICT_ITEM)
        finally:
            db.close()

    def test_default_object_export_not_dead(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            dead = project_checks.dead_exports(db, limit=50)
            same = project_checks.same_file_only(db, limit=50)
            assert not _contains(dead, FN_SEND)
            assert not _contains(same, FN_SEND)
        finally:
            db.close()

    def test_default_class_instance_not_dead(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            dead = project_checks.dead_exports(db, limit=50)
            unref = project_checks.unreferenced_symbols(db, limit=50)
            stale = project_checks.stale_types(db, limit=50)
            assert not _contains(dead, CLASS_INFERENCE_CLIENT)
            assert not _contains(unref, CLASS_INFERENCE_CLIENT)
            assert not _contains(stale, CLASS_INFERENCE_CLIENT)
        finally:
            db.close()

    def test_truly_dead_export_still_flagged(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            dead = project_checks.dead_exports(db, limit=50)
            assert _contains(dead, FN_ORPHAN_WIDGET)
        finally:
            db.close()

    def test_stale_type_same_file_extends_not_listed(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            stale = project_checks.stale_types(db, limit=50)
            assert not _contains(stale, TYPE_BASE_STREAM)
        finally:
            db.close()

    def test_stale_type_union_same_file_not_listed(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            stale = project_checks.stale_types(db, limit=50)
            assert not _contains(stale, TYPE_LABEL_FUNC)
        finally:
            db.close()

    def test_component_props_not_stale(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            stale = project_checks.stale_types(db, limit=50)
            assert not _contains(stale, TYPE_BUTTON_PROPS)
        finally:
            db.close()

    def test_opts_in_hooks_not_stale(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            stale = project_checks.stale_types(db, limit=50, scope=HOOK_A_FILE)
            assert not _contains(stale, TYPE_OPTS)
            stale_b = project_checks.stale_types(db, limit=50, scope=HOOK_B_FILE)
            assert not _contains(stale_b, TYPE_OPTS)
        finally:
            db.close()

    def test_type_only_cycle_ignored(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            cycles = project_checks.cycles(db, limit=50)
            assert not any(TYPE_A_FILE in line and TYPE_B_FILE in line for line in cycles)
        finally:
            db.close()

    def test_barrel_module_cycle_ignored(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            cycles = project_checks.cycles(db, limit=50)
            assert not any(I18N_EN_FILE in line and I18N_INDEX_FILE in line for line in cycles)
        finally:
            db.close()

    def test_module_symbol_shows_module_label(self, indexed_fixture):
        db = _db(indexed_fixture)
        try:
            row = db.execute(
                """
                SELECT gs.symbol FROM global_symbols gs
                JOIN defn_enclosing_ranges der ON der.symbol_id = gs.id
                JOIN documents d ON der.document_id = d.id
                WHERE d.relative_path = 'src/ui/menuModule.ts' AND gs.symbol LIKE '%/'
                LIMIT 1
                """
            ).fetchone()
            assert row is not None
            assert short_name(row[0]) == "(module)"
        finally:
            db.close()


class TestRefsAmbiguityE2E:
    def test_opts_ambiguous_refs_warns_with_counts(self, indexed_fixture):
        result = run_cli(["refs", TYPE_OPTS, "--limit", "5"], indexed_fixture)
        assert result.returncode == 0
        assert "Ambiguous symbol" in result.stderr
        assert "ext_refs=" in result.stderr
        assert HOOK_A_FILE in result.stderr or HOOK_B_FILE in result.stderr
