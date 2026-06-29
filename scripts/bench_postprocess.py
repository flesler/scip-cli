#!/usr/bin/env python3
"""Benchmark scip-cli-owned index steps (expt-convert + postprocess).

Skips scip-typescript. Use a saved .scip fixture for fast iteration.

  # One-time: capture fixture (scip-typescript; run from repo root)
  python scripts/bench_postprocess.py --capture path/to/tsconfig/dir

  # Iterate on postprocess / convert (our code only)
  python scripts/bench_postprocess.py /tmp/scip-bench-fixture/index.scip
  python scripts/bench_postprocess.py --runs 5 /path/to/fixture.scip

  # Reuse a saved raw expt-convert DB to benchmark postprocess only
  python scripts/bench_postprocess.py --postprocess-only --raw-db /tmp/scip-raw.db --runs 10
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scip_cli.indexing import (  # noqa: E402
    _convert_scip_to_db,
    _postprocess_index,
    _resolve_scip_binary,
    _run_subprocess,
)

DEFAULT_FIXTURE = Path("/tmp/scip-bench-fixture/index.scip")
DEFAULT_RAW_DB = Path("/tmp/scip-bench-raw.db")


def _table_counts(db: Path) -> dict[str, int]:
    conn = sqlite3.connect(db)
    try:
        tables = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        ]
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in sorted(tables)}
    finally:
        conn.close()


def _mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def _time_convert(scip: Path, work: Path) -> float:
    raw = work / "raw.db"
    if raw.exists():
        raw.unlink()
    t0 = time.perf_counter()
    result = _run_subprocess(
        [_resolve_scip_binary(), "expt-convert", str(scip), "--output", raw.name],
        cwd=str(work),
    )
    elapsed = time.perf_counter() - t0
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "expt-convert failed")
    return elapsed


def _time_postprocess(raw: Path, out: Path) -> float:
    shutil.copy2(raw, out)
    t0 = time.perf_counter()
    _postprocess_index(out)
    return time.perf_counter() - t0


def _time_full_pipeline(scip: Path, out: Path) -> float:
    if out.exists():
        out.unlink()
    t0 = time.perf_counter()
    _convert_scip_to_db(scip, out)
    return time.perf_counter() - t0


def capture_fixture(tsconfig_path: str, output: Path, *, raw_db: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    repo = Path.cwd()
    if not (repo / "package.json").exists() and not (repo / "tsconfig.json").exists():
        raise SystemExit("Run --capture from a TypeScript project root (package.json or tsconfig.json)")

    env = os.environ.copy()
    heap = env.get("SCIP_CLI_MAX_HEAP_MB", "8192")
    flag = f"--max-old-space-size={heap}"
    if flag not in env.get("NODE_OPTIONS", ""):
        env["NODE_OPTIONS"] = f"{env.get('NODE_OPTIONS', '')} {flag}".strip()

    cmd = [
        "npx",
        "-y",
        "@sourcegraph/scip-typescript",
        "index",
        "--output",
        str(output),
        tsconfig_path,
    ]
    print(f"Running scip-typescript -> {output}", file=sys.stderr)
    subprocess.run(cmd, cwd=str(repo), env=env, check=True)
    print(f"Captured {_mb(output):.1f} MB scip at {output}", file=sys.stderr)

    print(f"Converting to raw SQLite -> {raw_db}", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="scip-capture-") as tmp:
        work = Path(tmp)
        _time_convert(output, work)
        raw_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(work / "raw.db", raw_db)
    print(f"Saved raw expt-convert DB ({_mb(raw_db):.1f} MB) at {raw_db}", file=sys.stderr)


def run_postprocess_only(raw: Path, runs: int) -> None:
    print(f"Raw DB: {raw} ({_mb(raw):.1f} MB)")
    print(f"Runs: {runs}\n")

    times: list[float] = []
    post_db: Path | None = None
    for i in range(runs):
        with tempfile.TemporaryDirectory(prefix="scip-bench-") as tmp:
            out = Path(tmp) / "post.db"
            times.append(_time_postprocess(raw, out))
            if i == 0:
                post_db = out
                print("First-run table counts:")
                print(f"  raw:  {_table_counts(raw)}")
                print(f"  post: {_table_counts(out)}")
                raw_mb = _mb(raw)
                post_mb = _mb(out)
                print()

    avg = sum(times) / len(times)
    print(
        f"postprocess (ours)     avg={avg * 1000:7.0f}ms  "
        f"min={min(times) * 1000:7.0f}ms  max={max(times) * 1000:7.0f}ms"
    )
    if post_db is not None:
        print(f"\nSize: raw {raw_mb:.1f} MB -> post {post_mb:.1f} MB")


def run_benchmark(scip: Path, runs: int, *, raw_db: Path | None) -> None:
    if not scip.is_file():
        raise SystemExit(f"Fixture not found: {scip}")

    print(f"Fixture: {scip} ({_mb(scip):.1f} MB scip)")
    print(f"Runs: {runs}\n")

    convert_times: list[float] = []
    post_times: list[float] = []
    full_times: list[float] = []
    raw_mb = post_mb = 0.0

    with tempfile.TemporaryDirectory(prefix="scip-bench-") as tmp:
        work = Path(tmp)
        raw = work / "raw.db"

        for i in range(runs):
            convert_times.append(_time_convert(scip, work))
            post_times.append(_time_postprocess(raw, work / f"post-{i}.db"))
            full_times.append(_time_full_pipeline(scip, work / f"full-{i}.db"))
            if i == 0:
                print("First-run table counts (raw -> post):")
                print(f"  raw:  {_table_counts(raw)}")
                print(f"  post: {_table_counts(work / 'post-0.db')}")
                raw_mb = _mb(raw)
                post_mb = _mb(work / "post-0.db")
                print()

        if raw_db is not None:
            raw_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(raw, raw_db)
            print(f"Saved raw expt-convert DB to {raw_db} ({_mb(raw_db):.1f} MB)\n")

    def summary(name: str, values: list[float]) -> None:
        avg = sum(values) / len(values)
        print(f"{name:22} avg={avg * 1000:7.0f}ms  min={min(values) * 1000:7.0f}ms  max={max(values) * 1000:7.0f}ms")

    summary("expt-convert (3rd party)", convert_times)
    summary("postprocess (ours)", post_times)
    summary("convert+postprocess", full_times)
    print(f"\nSize: raw {raw_mb:.1f} MB -> post {post_mb:.1f} MB (fixture scip {_mb(scip):.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scip", nargs="?", type=Path, help="Path to index.scip fixture")
    parser.add_argument("--runs", type=int, default=3, help="Benchmark iterations (default: 3)")
    parser.add_argument(
        "--capture",
        metavar="TSCONFIG_PATH",
        help="Run scip-typescript once and save fixture (path to tsconfig project dir)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_FIXTURE,
        help=f"Output path for --capture (default: {DEFAULT_FIXTURE})",
    )
    parser.add_argument(
        "--raw-db",
        type=Path,
        help="Save or load raw expt-convert DB (skip convert when benchmarking postprocess)",
    )
    parser.add_argument(
        "--postprocess-only",
        action="store_true",
        help="Benchmark postprocess only (requires --raw-db)",
    )
    args = parser.parse_args()

    raw_db = args.raw_db or DEFAULT_RAW_DB

    if args.capture:
        capture_fixture(args.capture, args.output, raw_db=raw_db)
        return

    if args.postprocess_only:
        if not raw_db.is_file():
            raise SystemExit(f"Raw DB not found: {raw_db} (run with --capture or --raw-db after full benchmark)")
        run_postprocess_only(raw_db.resolve(), args.runs)
        return

    scip = args.scip or args.output
    run_benchmark(scip.resolve(), args.runs, raw_db=raw_db if args.raw_db else None)


if __name__ == "__main__":
    main()
