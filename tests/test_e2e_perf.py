"""Coarse e2e timing guard — fixture is tiny; catches gross CLI regressions only."""

from __future__ import annotations

import pytest

from tests.e2e_harness import CliRunner
from tests.fixture_catalog import CLASS_WIDGET, FN_GREET, HELPER_FILE
from tests.perf_util import median_elapsed, outliers_vs_median

pytestmark = pytest.mark.integration

# Whole-command smoke: nothing should be orders of magnitude slower than peers.
FAST_RATIO = 5.0
ANALYZE_FULL_VS_HIGH_RATIO = 6.0


def _time_cli(cli: CliRunner, *argv: str) -> float:
    return median_elapsed(lambda: cli.run(*argv))


class TestE2eCommandPerf:
    def test_command_timings_no_dramatic_outliers(self, cli):
        """On the small fixture all commands finish in a few ms — flag huge skew only."""
        fast = {
            "search": _time_cli(cli, "search", FN_GREET, "--limit", "3"),
            "symbols": _time_cli(cli, "symbols", HELPER_FILE, "--limit", "10"),
            "code": _time_cli(cli, "code", FN_GREET, "--limit", "1"),
            "refs": _time_cli(cli, "refs", FN_GREET, "--paths-only", "--limit", "10"),
            "members": _time_cli(cli, "members", CLASS_WIDGET, "--names-only"),
            "rdeps": _time_cli(cli, "rdeps", HELPER_FILE, "--limit", "10"),
        }
        analyze_high = _time_cli(cli, "analyze", "--priority", "high", "--limit", "5")
        analyze_all = _time_cli(cli, "analyze", "--limit", "5")

        fast_outliers = outliers_vs_median(fast, ratio=FAST_RATIO)
        assert not fast_outliers, f"Fast commands skewed vs peers on fixture (>{FAST_RATIO:.0f}x median): " + ", ".join(
            f"{k}={v * 1000:.1f}ms" for k, v in sorted(fast_outliers.items())
        )

        fast_peer = sorted(fast.values())[len(fast) // 2]
        analyze_high_limit = max(fast_peer * FAST_RATIO, analyze_high)
        assert analyze_high <= analyze_high_limit, (
            f"analyze --priority high too slow on fixture: {analyze_high * 1000:.1f}ms "
            f"(limit {analyze_high_limit * 1000:.1f}ms)"
        )

        analyze_all_limit = max(analyze_high * ANALYZE_FULL_VS_HIGH_RATIO, analyze_high)
        assert analyze_all <= analyze_all_limit, (
            f"analyze (all priorities) too slow vs high-only on fixture: "
            f"{analyze_all * 1000:.1f}ms vs high {analyze_high * 1000:.1f}ms "
            f"(limit {analyze_all_limit * 1000:.1f}ms)"
        )
