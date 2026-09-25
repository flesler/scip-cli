#!/bin/bash
# Incremental reindex smoke benchmarks.
#
#   scripts/bench_incremental_gate.sh --branch smoke    # local monorepo (~5 min)
#   scripts/bench_incremental_gate.sh --branch fixture    # mini fixture (~2 min)
#
# Faster: --scenario warm
# After a dirty prior run: --reset-baseline

set -e
cd "$(dirname "$0")/.."

if [ -d "$HOME/.nvm/versions/node" ]; then
    NODE_BIN="$(ls -d "$HOME/.nvm/versions/node"/*/bin 2>/dev/null | sort -V | tail -1)"
    if [ -n "$NODE_BIN" ]; then
        export PATH="$NODE_BIN:$PATH"
    fi
fi

if [ ! -d "tests/fixtures/incremental-bench" ]; then
    python3 scripts/generate_incremental_bench_fixture.py
fi

export PYTHONUNBUFFERED=1
exec python3 -u scripts/bench_incremental_gate.py "$@"
