"""Benchmark key queries on scaled :memory: DB.

Usage:
    pytest tests/test_bench_queries.py -s -v

Output format (for scripts/bench.sh comparison):
    BENCH:query_name:elapsed_ms
"""

from __future__ import annotations

import time

import pytest

from scip_cli.analyze import project as project_checks
from scip_cli.queries import (
    get_file_symbols,
    get_importer_paths,
    resolve_file,
    resolve_symbol,
)
from tests.bench_db import scaled_bench_db


@pytest.fixture(scope="module")
def bench_db():
    """Scaled :memory: DB for benchmarks (1000 files, ~15K symbols, ~100K mentions)."""
    return scaled_bench_db()


def bench_query(name: str, fn, *args, runs: int = 3, warmup: int = 1, **kwargs):
    """Run a query multiple times and report median elapsed time."""
    for _ in range(warmup):
        fn(*args, **kwargs)

    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn(*args, **kwargs)
        elapsed = time.perf_counter() - start
        times.append(elapsed)

    median = sorted(times)[len(times) // 2]
    print(f"BENCH:{name}:{median * 1000:.2f}")
    return median


class TestQueryBenchmarks:
    """Benchmark all major query paths on scaled DB."""

    def test_resolve_symbol_bare(self, bench_db):
        """resolve_symbol with bare name (no qualifier)."""
        bench_query("resolve_symbol_bare", resolve_symbol, bench_db, "func0", limit=10)

    def test_resolve_symbol_qualified(self, bench_db):
        """resolve_symbol with qualified name."""
        bench_query(
            "resolve_symbol_qualified",
            resolve_symbol,
            bench_db,
            "Class0.method0",
            limit=10,
        )

    def test_resolve_file_exact(self, bench_db):
        """resolve_file with exact path."""
        bench_query("resolve_file_exact", resolve_file, bench_db, "src/module00/file000.ts")

    def test_resolve_file_basename(self, bench_db):
        """resolve_file with basename only."""
        bench_query("resolve_file_basename", resolve_file, bench_db, "file000.ts")

    def test_resolve_file_fuzzy(self, bench_db):
        """resolve_file with fuzzy pattern."""
        bench_query("resolve_file_fuzzy", resolve_file, bench_db, "file000")

    def test_get_file_symbols(self, bench_db):
        """get_file_symbols for a file with 15 symbols."""
        bench_query("get_file_symbols", get_file_symbols, bench_db, "src/module00/file000.ts")

    def test_get_importer_paths(self, bench_db):
        """get_importer_paths for a symbol with many refs."""
        # Get a symbol ID first
        symbols = get_file_symbols(bench_db, "src/module00/file000.ts")
        if symbols:
            sym_id = symbols[0][0]
            bench_query("get_importer_paths", get_importer_paths, bench_db, [sym_id], "src/module00/file000.ts")

    def test_analyze_hotspots(self, bench_db):
        """project.hotspots — top referenced symbols."""
        bench_query("analyze_hotspots", project_checks.hotspots, bench_db, limit=25)

    def test_analyze_bottlenecks(self, bench_db):
        """project.bottlenecks — fan-in x fan-out."""
        bench_query("analyze_bottlenecks", project_checks.bottlenecks, bench_db, limit=25)

    def test_analyze_cycles(self, bench_db):
        """project.cycles — file dependency cycles."""
        bench_query("analyze_cycles", project_checks.cycles, bench_db, limit=25)

    def test_analyze_dead_exports(self, bench_db):
        """project.dead_exports — symbols with no external refs."""
        bench_query("analyze_dead_exports", project_checks.dead_exports, bench_db, limit=25)

    def test_analyze_stale_types(self, bench_db):
        """project.stale_types — type symbols with 0 consumers."""
        bench_query("analyze_stale_types", project_checks.stale_types, bench_db, limit=25)

    def test_analyze_unreferenced(self, bench_db):
        """project.unreferenced_symbols — no refs at all."""
        bench_query("analyze_unreferenced", project_checks.unreferenced_symbols, bench_db, limit=25)

    def test_analyze_same_file_only(self, bench_db):
        """project.same_file_only — in-file use only."""
        bench_query("analyze_same_file_only", project_checks.same_file_only, bench_db, limit=25)

    def test_analyze_top_coupling(self, bench_db):
        """project.top_coupling — file pairs with most shared symbols."""
        bench_query("analyze_top_coupling", project_checks.top_coupling, bench_db, limit=25)

    def test_analyze_run_all(self, bench_db):
        """project.run_all — all checks combined."""
        bench_query("analyze_run_all", project_checks.run_all, bench_db, limit=25)
