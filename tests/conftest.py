"""Shared pytest fixtures."""

import shutil

import pytest

from tests.e2e_harness import FIXTURE_ROOT, CliRunner, IndexedFixture, index_fixture_project


@pytest.fixture(scope="session")
def indexed_fixture(tmp_path_factory):
    """Copy typescript-project, index once with real tooling, reuse for all e2e tests."""
    root = tmp_path_factory.mktemp("scip-fixture")
    shutil.copytree(FIXTURE_ROOT, root, dirs_exist_ok=True)
    try:
        db_path = index_fixture_project(root)
    except RuntimeError as exc:
        pytest.skip(str(exc))
    return IndexedFixture(root=root, db_path=db_path)


@pytest.fixture
def cli(indexed_fixture):
    """In-process CLI runner backed by the session index."""
    return CliRunner(indexed_fixture)
