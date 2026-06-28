#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

BUMP="${1:-}"

usage() {
    echo "Usage: $0 [patch|minor|major]"
    echo ""
    echo "  patch|minor|major  Bump scip_cli/__init__.py __version__, commit, then publish"
    echo "  (no argument)      Publish the current __version__ without bumping"
    exit 1
}

case "$BUMP" in
    "" | patch | minor | major) ;;
    -h | --help) usage ;;
    *)
        echo "Error: unknown bump level '$BUMP' (expected patch, minor, or major)"
        usage
        ;;
esac

# Run tests first
./scripts/test.sh

# Build
./scripts/build.sh

if [[ -n "$BUMP" ]]; then
    if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
        echo "Error: working tree has uncommitted changes; commit or stash before bumping"
        git status --short
        exit 1
    fi

    echo "Bumping $BUMP version..."
    NEW_VERSION="$(
        BUMP_LEVEL="$BUMP" python <<'PY'
import os
import re
import sys

bump = os.environ["BUMP_LEVEL"]
path = "scip_cli/__init__.py"
with open(path) as f:
    text = f.read()
match = re.search(r'__version__ = "(\d+)\.(\d+)\.(\d+)"', text)
if not match:
    sys.exit("Could not parse __version__ in scip_cli/__init__.py")
major, minor, patch = (int(x) for x in match.groups())
if bump == "patch":
    patch += 1
elif bump == "minor":
    minor += 1
    patch = 0
elif bump == "major":
    major += 1
    minor = 0
    patch = 0
else:
    sys.exit(f"Invalid bump level: {bump}")
new = f"{major}.{minor}.{patch}"
updated = re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new}"', text, count=1)
open(path, "w").write(updated)
print(new)
PY
    )"
    echo "New version: $NEW_VERSION"

    git add scip_cli/__init__.py
    git commit -m "Release $NEW_VERSION."
fi

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
git push origin HEAD "v$VERSION"

# Upload to PyPI
echo "Uploading to PyPI..."
python -m twine upload dist/* --username __token__ --password "$(grep PYPI_TOKEN .env | cut -d= -f2 | tr -d '"')"

echo "Published v$VERSION successfully!"
echo "View at: https://pypi.org/project/scip-cli/$VERSION/"
