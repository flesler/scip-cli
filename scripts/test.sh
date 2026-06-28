#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Type checking..."
basedpyright scip_cli/

echo "Running tests..."
python -m pytest tests/ -v

echo "All checks passed!"
