#!/usr/bin/env bash
# Optional: auto-fix lint/format then run the same gate as CI (minus duplicate ruff).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RUFF="$ROOT/.venv/bin/ruff"
if [[ ! -x "$RUFF" ]]; then
    echo "Error: ruff not found in .venv. Run: pip install -e '.[dev]'" >&2
    exit 1
fi

"$RUFF" check --fix .
"$RUFF" format .
exec "$ROOT/scripts/test.sh" --skip-lint
