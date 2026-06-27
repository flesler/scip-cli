#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "Cleaning old builds..."
rm -rf dist/ build/ *.egg-info/

echo "Building package..."
python -m build

echo "Build complete!"
ls -la dist/
