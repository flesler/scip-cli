#!/bin/bash
set -e

cd "$(dirname "$0")/.."

# Use venv-local binaries (CI and local dev both use .venv)
RUFF=".venv/bin/ruff"
PYRIGHT=".venv/bin/basedpyright"
PYTEST=".venv/bin/pytest"

# Check venv binaries exist
if [ ! -f "$RUFF" ]; then
    echo "Error: ruff not found in .venv. Run: pip install -e '.[dev]'"
    exit 1
fi

echo "Linting..."
$RUFF check .

echo "Formatting..."
$RUFF format --check .

echo "Type checking..."
$PYRIGHT scip_cli/

echo "Running tests..."
$PYTEST

echo "All checks passed!"
