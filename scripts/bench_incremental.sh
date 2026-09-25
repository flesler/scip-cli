#!/bin/bash
# Incremental reindex benchmark (manual; requires Node.js + scip-cli on PATH).
#
#   scripts/bench_incremental.sh              # run, save latest
#   scripts/bench_incremental.sh --baseline     # save baseline
#   scripts/bench_incremental.sh --compare      # compare latest vs baseline

set -e

cd "$(dirname "$0")/.."

if [ ! -d "tests/fixtures/incremental-bench" ]; then
    echo "Generating incremental bench fixture..."
    python3 scripts/generate_incremental_bench_fixture.py
fi

ARGS=()
if [ "$1" = "--baseline" ]; then
    ARGS+=(--baseline)
elif [ "$1" = "--compare" ]; then
    ARGS+=(--compare)
elif [ -n "$1" ]; then
    echo "Usage: $0 [--baseline | --compare]"
    exit 1
fi

python3 scripts/bench_incremental.py "${ARGS[@]}"
