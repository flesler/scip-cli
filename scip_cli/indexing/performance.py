"""Optional indexing performance tracing (SCIP_CLI_INDEX_TIMING=1).

When disabled, phase/metric helpers are no-ops (no timers, no stderr).
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager

_PHASES: dict[str, float] = {}
_METRICS: dict[str, int] = {}
_NOTES: list[str] = []


def enabled() -> bool:
    """True when SCIP_CLI_INDEX_TIMING requests per-phase stderr output."""
    return os.environ.get("SCIP_CLI_INDEX_TIMING", "0").lower() not in {"0", "false", "no"}


def metric(name: str, value: int) -> None:
    """Record a counter included in the summary line (e.g. shards_reused=16)."""
    if not enabled():
        return
    _METRICS[name] = value


def note(message: str) -> None:
    """Append a diagnostic note to the summary line."""
    if not enabled():
        return
    _NOTES.append(message)
    print(f"INDEX_TIMING:note {message}", file=sys.stderr, flush=True)


@contextmanager
def phase(label: str) -> Generator[None, None, None]:
    """Time a block; emit INDEX_TIMING:<label>=Nms when enabled."""
    if not enabled():
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        _PHASES[label] = _PHASES.get(label, 0.0) + elapsed_ms
        print(f"INDEX_TIMING:{label}={elapsed_ms:.0f}ms", file=sys.stderr, flush=True)


def flush_summary() -> None:
    """Print aggregated INDEX_TIMING:summary and reset collectors."""
    if not enabled():
        return
    if not _PHASES and not _METRICS and not _NOTES:
        return
    parts: list[str] = [f"{key}={int(ms)}ms" for key, ms in sorted(_PHASES.items())]
    parts.extend(f"{key}={value}" for key, value in sorted(_METRICS.items()))
    if _NOTES:
        parts.append("notes=" + ";".join(_NOTES))
    print(f"INDEX_TIMING:summary {' '.join(parts)}", file=sys.stderr, flush=True)
    _PHASES.clear()
    _METRICS.clear()
    _NOTES.clear()
