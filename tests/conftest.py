"""Shared pytest fixtures."""

import pytest

from tests.e2e_harness import FIXTURE_ROOT, CliRunner
from tests.fixture_cache import prepare_cached_indexed_fixture
from tests.fixture_catalog import DEFAULT_TEST_EXCLUDE_GLOBS


@pytest.fixture(scope="session")
def indexed_fixture():
    """typescript-project indexed once per fixture content (stable $TMPDIR/scip-fixture workspace)."""
    try:
        return prepare_cached_indexed_fixture(FIXTURE_ROOT, cache_key="typescript-default")
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="session")
def excluded_fixture():
    """Same fixture with default test exclude globs persisted at index time."""
    try:
        return prepare_cached_indexed_fixture(
            FIXTURE_ROOT,
            cache_key="typescript-excluded",
            exclude_globs=DEFAULT_TEST_EXCLUDE_GLOBS,
        )
    except RuntimeError as exc:
        pytest.skip(str(exc))


@pytest.fixture
def cli(indexed_fixture):
    """In-process CLI runner backed by the session index."""
    return CliRunner(indexed_fixture)
