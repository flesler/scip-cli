"""Relative timing guard for project analyze checks on the in-memory mini DB."""

from __future__ import annotations

from functools import partial

from scip_cli.analyze import project as project_checks
from tests.analyze_db import mini_codebase_db
from tests.perf_util import median_elapsed, outliers_vs_median

# Mini DB is tiny — generous ratio; still catches runaway SQL (e.g. recursive blowups).
CHECK_RATIO = 25.0
BASELINE_CHECKS = ("hotspots", "coupling", "stale_types", "dead_exports")


class TestAnalyzeCheckPerf:
    def test_project_checks_not_dramatically_slower_than_peers(self):
        db = mini_codebase_db()
        checks = {
            "hotspots": project_checks.hotspots,
            "coupling": project_checks.top_coupling,
            "stale_types": project_checks.stale_types,
            "cycles": project_checks.cycles,
            "bottlenecks": project_checks.bottlenecks,
            "dead_exports": project_checks.dead_exports,
            "unreferenced": project_checks.unreferenced_symbols,
            "same_file": project_checks.same_file_only,
            "test_only": project_checks.symbols_test_only_consumers,
        }
        timings = {}
        for name, fn in checks.items():
            timings[name] = median_elapsed(partial(fn, db, limit=20), runs=5, warmup=2)

        baseline = {k: timings[k] for k in BASELINE_CHECKS if k in timings}
        slow = outliers_vs_median(timings, ratio=CHECK_RATIO)
        baseline_slow = {k: v for k, v in slow.items() if k not in baseline}
        assert not baseline_slow, (
            f"Analyze check(s) >{CHECK_RATIO:.0f}x mini-DB peer median: "
            + ", ".join(f"{k}={v * 1000:.2f}ms" for k, v in sorted(baseline_slow.items()))
            + f" (peer median {sorted(baseline.values())[len(baseline) // 2] * 1000:.2f}ms)"
        )
