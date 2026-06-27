#!/bin/bash
set -e

cd "$(dirname "$0")/.."

# Run tests first
./scripts/test.sh

# Build
./scripts/build.sh

# Get version from package
VERSION=$(python -c "from scip_cli import __version__; print(__version__)")
echo "Publishing version $VERSION..."

# Check if tag already exists
if git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "Error: Tag v$VERSION already exists"
    exit 1
fi

# Create and push tag
echo "Creating git tag v$VERSION..."
git tag -a "v$VERSION" -m "Release $VERSION"
git push origin "v$VERSION"

# Upload to PyPI
echo "Uploading to PyPI..."
python -m twine upload dist/* --username __token__ --password "$(grep PYPI_TOKEN .env | cut -d= -f2 | tr -d '"')"

echo "Published v$VERSION successfully!"
echo "View at: https://pypi.org/project/scip-cli/$VERSION/"
