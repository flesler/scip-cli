#!/bin/bash
# Query benchmark runner with before/after comparison
#
# Usage:
#   scripts/bench.sh              # Run benchmarks, save to .bench-latest
#   scripts/bench.sh --save foo   # Save as .bench-foo
#   scripts/bench.sh --compare    # Compare .bench-latest with .bench-baseline
#   scripts/bench.sh --baseline   # Save current as .bench-baseline

set -e

BENCH_DIR="tmp/benchmarks"
mkdir -p "$BENCH_DIR"

run_bench() {
    pytest tests/test_bench_queries.py -s 2>&1 | grep -o 'BENCH:[^ ]*' | tee "$1"
}

if [ "$1" = "--save" ]; then
    if [ -z "$2" ]; then
        echo "Usage: $0 --save <name>"
        exit 1
    fi
    echo "Running benchmarks, saving as .bench-$2..."
    run_bench "$BENCH_DIR/.bench-$2"
    echo "Saved to $BENCH_DIR/.bench-$2"
elif [ "$1" = "--baseline" ]; then
    echo "Running benchmarks, saving as baseline..."
    run_bench "$BENCH_DIR/.bench-baseline"
    echo "Saved baseline to $BENCH_DIR/.bench-baseline"
elif [ "$1" = "--compare" ]; then
    BASELINE="$BENCH_DIR/.bench-baseline"
    LATEST="$BENCH_DIR/.bench-latest"

    if [ ! -f "$BASELINE" ]; then
        echo "No baseline found. Run: $0 --baseline"
        exit 1
    fi

    echo "Running current benchmarks..."
    run_bench "$LATEST"

    echo ""
    echo "=== Comparison ==="
    echo "Query                          Baseline    Current     Ratio"
    echo "-----------------------------------------------------------"

    while IFS=: read -r _ query baseline_ms; do
        current_line=$(grep "^BENCH:$query:" "$LATEST")
        if [ -n "$current_line" ]; then
            current_ms=$(echo "$current_line" | cut -d: -f3)
            ratio=$(echo "scale=2; $current_ms / $baseline_ms" | bc -l)
            printf "%-30s %8.2fms  %8.2fms  %5.2fx\n" "$query" "$baseline_ms" "$current_ms" "$ratio"
        fi
    done < "$BASELINE"
else
    echo "Running benchmarks..."
    run_bench "$BENCH_DIR/.bench-latest"
    echo "Saved to $BENCH_DIR/.bench-latest"
fi
