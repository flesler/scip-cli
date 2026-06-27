"""Timing helpers for coarse perf regression guards."""

from __future__ import annotations

import statistics
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_RUNS = 3
DEFAULT_WARMUP = 1
# Ignore sub-millisecond noise; require both ratio and floor before flagging.
MIN_REPORT_MS = 5.0


def median_elapsed(
    fn: Callable[[], T],
    *,
    runs: int = DEFAULT_RUNS,
    warmup: int = DEFAULT_WARMUP,
) -> float:
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def outliers_vs_median(
    timings: dict[str, float],
    *,
    ratio: float,
    floor_s: float = MIN_REPORT_MS / 1000.0,
) -> dict[str, float]:
    """Names where timing exceeds max(ratio x peer median, floor_s)."""
    if not timings:
        return {}
    peer = statistics.median(timings.values())
    threshold = max(peer * ratio, floor_s)
    return {name: elapsed for name, elapsed in timings.items() if elapsed > threshold}
