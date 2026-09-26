#!/bin/bash
set -e

cd "$(dirname "$0")/.."

SKIP_LINT=0
for arg in "$@"; do
    if [ "$arg" = "--skip-lint" ]; then
        SKIP_LINT=1
    fi
done

# Use venv-local binaries (CI and local dev both use .venv)
RUFF=".venv/bin/ruff"
PYRIGHT=".venv/bin/basedpyright"
PYTEST=".venv/bin/pytest"

# Check venv binaries exist
if [ ! -f "$RUFF" ]; then
    echo "Error: ruff not found in .venv. Run: pip install -e '.[dev]'"
    exit 1
fi

if [ "$SKIP_LINT" = 0 ]; then
    echo "Linting..."
    $RUFF check .

    echo "Formatting..."
    $RUFF format --check .
fi

echo "Type checking..."
$PYRIGHT --warnings scip_cli/ scripts/

echo "Running tests..."
$PYTEST

echo "All checks passed!"
