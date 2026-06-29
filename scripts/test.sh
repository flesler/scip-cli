#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Linting..."
ruff check .

echo "Formatting..."
ruff format --check .

echo "Type checking..."
basedpyright scip_cli/

echo "Running tests..."
pytest

echo "All checks passed!"
