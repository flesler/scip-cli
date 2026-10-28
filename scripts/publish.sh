#!/bin/bash
set -euo pipefail

if [ ! -t 1 ]; then
    echo "Error: publish.sh must be run unfiltered (stdout is piped)" >&2
    echo "Run directly without | tail, | head, etc." >&2
    exit 1
fi

cd "$(dirname "$0")/.."

usage() {
    echo "Usage: $0"
    echo ""
    echo "PyPI: test → build → twine upload → pip smoke → editable dev install."
    echo "Expects scip_cli/__init__.py version to match an existing git tag vX.Y.Z"
    echo "(run ./scripts/release.sh first for a new version)."
    exit 1
}

case "${1:-}" in
    "" ) ;;
    -h | --help) usage ;;
    *)
        echo "Error: publish.sh takes no arguments (got '$1')"
        usage
        ;;
esac

./scripts/test.sh

VERSION=$(python -c "from scip_cli import __version__; print(__version__)")
echo "Publishing scip-cli $VERSION to PyPI..."

if ! git rev-parse "v$VERSION" >/dev/null 2>&1; then
    echo "Error: local git tag v$VERSION not found; run ./scripts/release.sh first" >&2
    exit 1
fi

./scripts/build.sh

echo "Uploading to PyPI..."
python -m twine upload dist/* --username __token__ --password "$(grep PYPI_TOKEN .env | cut -d= -f2 | tr -d '"')"

echo "Published to PyPI: https://pypi.org/project/scip-cli/$VERSION/"

echo "Smoke testing PyPI..."
PYPI_RETRY_MAX="${PYPI_RETRY_MAX:-12}"
PYPI_RETRY_SLEEP="${PYPI_RETRY_SLEEP:-10}"
for attempt in $(seq 1 "$PYPI_RETRY_MAX"); do
    if pip install "scip-cli==$VERSION"; then
        break
    fi
    if [[ "$attempt" -eq "$PYPI_RETRY_MAX" ]]; then
        echo "Error: scip-cli==$VERSION not on PyPI after $PYPI_RETRY_MAX attempts" >&2
        exit 1
    fi
    echo "PyPI propagation delay (attempt $attempt/$PYPI_RETRY_MAX), retrying in ${PYPI_RETRY_SLEEP}s..."
    sleep "$PYPI_RETRY_SLEEP"
done
scip-cli --version
pip install -e ".[dev]"
scip-cli --version

echo "All done!"
