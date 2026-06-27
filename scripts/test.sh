#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Running tests..."
python -m pytest tests/ -v

echo "Tests passed!"
