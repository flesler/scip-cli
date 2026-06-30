#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/.."

BUMP="${1:-}"
GH_SCRIPTS="${GH_SCRIPTS:-${HOME}/.claude/skills/gh/scripts}"
SYNC_RELEASE="${GH_SCRIPTS}/sync-github-release.sh"

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
    git commit -m "v${NEW_VERSION}"
fi

# Build (after version bump so dist/ has correct version)
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
git tag -a "v$VERSION" -m "v$VERSION"
git push origin HEAD "v$VERSION"

REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
if [[ -z "$REPO" ]]; then
    REPO="flesler/scip-cli"
fi

"$SYNC_RELEASE" "$REPO" "$VERSION" --install "$(cat <<EOF
\`\`\`bash
pip install scip-cli=={{VERSION}}
\`\`\`
EOF
)" --execute

# Upload to PyPI
echo "Uploading to PyPI..."
python -m twine upload dist/* --username __token__ --password "$(grep PYPI_TOKEN .env | cut -d= -f2 | tr -d '"')"

echo "Published v$VERSION successfully!"
echo "View at: https://pypi.org/project/scip-cli/$VERSION/"
echo "Release: https://github.com/$REPO/releases/tag/v$VERSION"

echo "Smoke testing PyPI..."
pip install "scip-cli==$VERSION"
scip-cli --version
pip install -e ".[dev]"
scip-cli --version
