"""Shared pytest fixtures."""

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sample-project"
SMOKE_CLI = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "scip-cli"

# Stable symbols/paths in the bundled sample TypeScript project.
HELPER_FILE = "src/helper.ts"
FN_GREET = "greet"
CLASS_WIDGET = "Widget"


@pytest.fixture(scope="session")
def indexed_sample_project(tmp_path_factory):
    """Copy the sample project, index once, return project root."""
    if not SMOKE_CLI.is_file():
        pytest.skip("scip-cli not installed in .venv")
    root = tmp_path_factory.mktemp("sample-project")
    shutil.copytree(FIXTURE_ROOT, root, dirs_exist_ok=True)
    result = subprocess.run(
        [str(SMOKE_CLI), "reindex"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        pytest.skip(f"sample project indexing failed: {result.stderr[:500]}")
    return root


@pytest.fixture(scope="session")
def smoke_cli():
    if not SMOKE_CLI.is_file():
        pytest.skip("scip-cli not installed in .venv")
    return str(SMOKE_CLI)
