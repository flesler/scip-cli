#!/usr/bin/env python3
"""Benchmark incremental reindex on the versioned multi-shard fixture.

Manual only — not part of pre-commit or scripts/test.sh. Requires Node.js + npx.

  scripts/bench_incremental.sh              # run, save latest results to gitignored bench dir
  scripts/bench_incremental.sh --baseline   # save baseline
  scripts/bench_incremental.sh --compare    # diff against baseline

Incremental reindex is the default in git repos (shard skip + partial --files).

Dirty-file cases modify content (append), not mtime-only touch.

Output lines: INCR_BENCH:<scenario>:<seconds>:<reused>/<reindexed>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SOURCE = ROOT / "tests" / "fixtures" / "incremental-bench"
WORK_ROOT = ROOT / "tmp" / "benchmarks" / "incremental-bench-work"
BENCH_DIR = ROOT / "tmp" / "benchmarks"
SNAPSHOT = BENCH_DIR / "incremental-bench-shard-snapshot"
BACKUP_DIR = BENCH_DIR / "incremental-bench-file-backups"

TOUCH_SMALL = ["packages/alpha/src/index.ts"]
TOUCH_LARGE = ["packages/bulk/src/modules/module_25.ts"]
TOUCH_BOTH = TOUCH_SMALL + TOUCH_LARGE

INCR_LINE = re.compile(r"^INCR_BENCH:(?P<scenario>[^:]+):(?P<seconds>[\d.]+):(?P<stats>.+)$")


@dataclass
class BenchRow:
    scenario: str
    seconds: float
    exit_code: int
    reused: int | None
    reindexed: int | None
    note: str


def _require_tooling() -> None:
    if shutil.which("npx") is None:
        raise SystemExit("npx not found — install Node.js to run incremental benchmarks")
    if shutil.which("scip-cli") is None:
        raise SystemExit("scip-cli not on PATH — run: pip install -e '.[dev]'")
    if not FIXTURE_SOURCE.is_dir():
        raise SystemExit(
            f"fixture missing at {FIXTURE_SOURCE} — run: python scripts/generate_incremental_bench_fixture.py"
        )


def _cache_dir(work_root: Path) -> Path:
    from scip_cli.cache import get_cache_dir

    return get_cache_dir(work_root)


def _prepare_work_tree() -> Path:
    if WORK_ROOT.is_dir():
        shutil.rmtree(WORK_ROOT)
    shutil.copytree(FIXTURE_SOURCE, WORK_ROOT)
    return WORK_ROOT


def _backup_touch_files(work_root: Path) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for rel in TOUCH_BOTH:
        src = work_root / rel
        if src.is_file():
            shutil.copy2(src, BACKUP_DIR / rel.replace("/", "__"))


def _restore_touch_files(work_root: Path) -> None:
    if not BACKUP_DIR.is_dir():
        return
    for backup in BACKUP_DIR.iterdir():
        rel = backup.name.replace("__", "/")
        dest = work_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, dest)


def _touch_files(work_root: Path, paths: list[str], token: str) -> None:
    for rel in paths:
        path = work_root / rel
        path.write_text(path.read_text(encoding="utf-8") + f"\n// bench:{token}\n", encoding="utf-8")


def _parse_stderr(stderr: str) -> tuple[int | None, int | None]:
    reused = reindexed = None
    match = re.search(r"Incremental: (\d+) shard\(s\) reused, (\d+) reindexed", stderr)
    if match:
        reused, reindexed = int(match.group(1)), int(match.group(2))
    return reused, reindexed


def _run_reindex(work_root: Path, args: list[str]) -> tuple[float, int, str]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["scip-cli", "reindex", *args],
        cwd=work_root,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    elapsed = time.perf_counter() - t0
    return elapsed, proc.returncode, proc.stderr


def _bench_row(
    work_root: Path,
    scenario: str,
    args: list[str],
    *,
    note: str,
    touch: list[str] | None = None,
) -> BenchRow:
    _restore_touch_files(work_root)
    if touch:
        _touch_files(work_root, touch, scenario)
    elapsed, exit_code, stderr = _run_reindex(work_root, args)
    reused, reindexed = _parse_stderr(stderr)
    if exit_code != 0:
        raise RuntimeError(f"{scenario} failed (exit {exit_code}):\n{stderr}")
    return BenchRow(
        scenario=scenario,
        seconds=round(elapsed, 2),
        exit_code=exit_code,
        reused=reused,
        reindexed=reindexed,
        note=note,
    )


def _save_snapshot(cache: Path) -> None:
    if SNAPSHOT.is_dir():
        shutil.rmtree(SNAPSHOT)
    shutil.copytree(cache / "shards", SNAPSHOT / "shards")


def _restore_snapshot(cache: Path) -> None:
    shutil.rmtree(cache / "shards", ignore_errors=True)
    shutil.copytree(SNAPSHOT / "shards", cache / "shards")


def _reset_to_warm(work_root: Path, cache: Path) -> None:
    _restore_touch_files(work_root)
    _restore_snapshot(cache)


def run_benchmarks() -> list[BenchRow]:
    work_root = _prepare_work_tree()
    cache = _cache_dir(work_root)
    _backup_touch_files(work_root)
    rows: list[BenchRow] = []

    seed = _bench_row(work_root, "seed_warm", [], note="build warm shard cache")
    rows.append(seed)
    _save_snapshot(cache)

    def bench(
        scenario: str,
        args: list[str],
        *,
        note: str,
        touch: list[str] | None = None,
    ) -> None:
        _reset_to_warm(work_root, cache)
        rows.append(_bench_row(work_root, scenario, args, note=note, touch=touch))

    bench("warm_all_cached", [], note="no file changes")
    bench(
        "touch_small_shard",
        [],
        note="packages/alpha (~4 files)",
        touch=TOUCH_SMALL,
    )
    bench(
        "touch_large_shard",
        [],
        note=f"packages/bulk (~{len(list((FIXTURE_SOURCE / 'packages/bulk/src').rglob('*.ts')))} files)",
        touch=TOUCH_LARGE,
    )
    bench(
        "touch_small_and_large",
        [],
        note="alpha + bulk (2 shards)",
        touch=TOUCH_BOTH,
    )

    _reset_to_warm(work_root, cache)
    shutil.rmtree(cache / "shards", ignore_errors=True)
    rows.append(
        _bench_row(
            work_root,
            "cold_incremental",
            [],
            note="empty shard cache",
        )
    )

    _reset_to_warm(work_root, cache)
    rows.append(
        _bench_row(
            work_root,
            "full_reindex",
            ["--no-incremental"],
            note="non-incremental baseline",
        )
    )

    _restore_touch_files(work_root)
    return rows


def _format_lines(rows: list[BenchRow]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        if row.scenario == "seed_warm":
            continue
        stats = "—"
        if row.reused is not None and row.reindexed is not None:
            stats = f"{row.reused}/{row.reindexed}"
        lines.append(f"INCR_BENCH:{row.scenario}:{row.seconds}:{stats}")
    return lines


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _compare(baseline: Path, current: Path) -> None:
    if not baseline.is_file():
        raise SystemExit(f"No baseline at {baseline} — run: scripts/bench_incremental.sh --baseline")

    baseline_rows = {}
    for line in baseline.read_text(encoding="utf-8").splitlines():
        match = INCR_LINE.match(line.strip())
        if match:
            baseline_rows[match.group("scenario")] = float(match.group("seconds"))

    current_rows = {}
    for line in current.read_text(encoding="utf-8").splitlines():
        match = INCR_LINE.match(line.strip())
        if match:
            current_rows[match.group("scenario")] = float(match.group("seconds"))

    print("")
    print("=== Incremental benchmark comparison ===")
    print(f"{'Scenario':<28} {'Baseline':>10} {'Current':>10} {'Ratio':>8}")
    print("-" * 60)
    for scenario in sorted(baseline_rows):
        base = baseline_rows[scenario]
        cur = current_rows.get(scenario)
        if cur is None:
            print(f"{scenario:<28} {base:>9.2f}s  {'—':>10}  {'—':>8}")
            continue
        ratio = cur / base if base else 0.0
        print(f"{scenario:<28} {base:>9.2f}s  {cur:>9.2f}s  {ratio:>7.2f}x")


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental reindex benchmark")
    parser.add_argument("--baseline", action="store_true", help="Save results as baseline")
    parser.add_argument("--compare", action="store_true", help="Compare latest against baseline")
    parser.add_argument("--json", action="store_true", help="Also print full JSON rows to stdout")
    args = parser.parse_args()

    _require_tooling()
    rows = run_benchmarks()
    lines = _format_lines(rows)

    latest = BENCH_DIR / ".incr-bench-latest"
    baseline = BENCH_DIR / ".incr-bench-baseline"
    _write_lines(latest, lines)

    for line in lines:
        print(line)

    if args.json:
        payload = [asdict(row) for row in rows if row.scenario != "seed_warm"]
        print(json.dumps(payload, indent=2))

    if args.baseline:
        _write_lines(baseline, lines)
        print(f"Saved baseline to {baseline}")

    if args.compare:
        _compare(baseline, latest)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
