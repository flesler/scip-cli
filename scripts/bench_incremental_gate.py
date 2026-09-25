#!/usr/bin/env python3
"""Incremental reindex smoke benchmarks on a local monorepo or the mini fixture.

Smoke monorepo paths live in scripts/smoke.local.json (gitignored).
See scripts/smoke.local.example.json.

scripts/bench_incremental_gate.sh --branch smoke    # warm + modify_large (~5 min)
scripts/bench_incremental_gate.sh --branch fixture  # mini fixture sanity (~2 min)
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Line-buffer when stdout is piped (tee gate-run.log).
print = functools.partial(print, flush=True)

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "tmp" / "benchmarks"
DECISIONS_PATH = BENCH_DIR / ".incremental-gate-decisions.json"
FIXTURE_SOURCE = ROOT / "tests" / "fixtures" / "incremental-bench"

BASE_ENV: dict[str, str] = {
    "SCIP_CLI_FILE_INCREMENTAL": "1",
}

FIXTURE_TOUCH_LARGE = ["packages/bulk/src/modules/module_25.ts"]
SMOKE_BASELINE_DIR = BENCH_DIR / "gate-smoke-baseline"
FIXTURE_BASELINE_DIR = BENCH_DIR / "gate-fixture-baseline"

SMOKE_LABEL = "default"


@dataclass
class BenchRow:
    branch: str
    label: str
    scenario: str
    seconds: float
    exit_code: int
    reused: int | None = None
    reindexed: int | None = None
    env: dict[str, str] = field(default_factory=dict)
    note: str = ""


@dataclass
class GateReport:
    started_at: str
    scip_cli_version: str
    rows: list[BenchRow]
    branch: str
    decisions: dict[str, str]


def _node_version_key(bin_dir: Path) -> tuple[int, ...]:
    name = bin_dir.parent.name.lstrip("v")
    parts: list[int] = []
    for piece in name.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _augment_path(env: dict[str, str]) -> dict[str, str]:
    """Prepend common Node install dirs so npx/scip-typescript resolve in gate subprocesses."""
    extra: list[str] = []
    nvm_root = Path.home() / ".nvm/versions/node"
    if nvm_root.is_dir():
        node_bins = sorted(nvm_root.glob("*/bin"), key=_node_version_key)
        if node_bins:
            extra.append(str(node_bins[-1]))
    for pattern in (Path("/usr/local/bin"),):
        if pattern.is_dir():
            extra.append(str(pattern))
    repo_bin = ROOT / "node_modules" / ".bin"
    if repo_bin.is_dir():
        extra.append(str(repo_bin))
    if extra:
        env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
    return env


def _require_tooling() -> None:
    env = _augment_path(os.environ.copy())
    if shutil.which("npx", path=env.get("PATH")) is None:
        raise SystemExit("npx not found — source nvm or add Node to PATH")
    if shutil.which("scip-cli", path=env.get("PATH")) is None:
        raise SystemExit("scip-cli not on PATH — pip install -e '.[dev]'")


def _scip_version() -> str:
    proc = subprocess.run(["scip-cli", "--version"], capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _cache_dir(work_root: Path) -> Path:
    sys.path.insert(0, str(ROOT))
    from scip_cli.cache import get_cache_dir

    return get_cache_dir(work_root)


def _ensure_smoke_cache(smoke_root: Path) -> Path:
    """Point canonical cache at <smoke_root>/cache when smoke data lives there."""
    project_cache = _cache_dir(smoke_root)
    legacy = smoke_root / "cache"
    if (project_cache / "metadata.json").is_file():
        return project_cache
    if not (legacy / "metadata.json").is_file():
        return project_cache
    project_cache.parent.mkdir(parents=True, exist_ok=True)
    if project_cache.is_symlink() or project_cache.is_file():
        project_cache.unlink()
    elif project_cache.is_dir():
        shutil.rmtree(project_cache)
    project_cache.symlink_to(legacy, target_is_directory=True)
    return project_cache


def _load_decisions() -> dict[str, str]:
    if not DECISIONS_PATH.is_file():
        return {}
    data = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    return {k: str(v) for k, v in data.items() if not k.startswith("_")}


def _parse_incremental(stderr: str) -> tuple[int | None, int | None]:
    match = re.search(r"Incremental: (\d+) shard\(s\) reused, (\d+) reindexed", stderr)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def _parse_index_timing(stderr: str) -> str | None:
    for line in reversed(stderr.splitlines()):
        if line.startswith("INDEX_TIMING:summary "):
            return line.removeprefix("INDEX_TIMING:summary ").strip()
    return None


def _run_reindex(work_root: Path, env_overrides: dict[str, str]) -> tuple[float, int, str]:
    env = _augment_path(os.environ.copy())
    env.setdefault("SCIP_CLI_INDEX_TIMING", "1")
    env.update(env_overrides)
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["scip-cli", "reindex", "--incremental"],
        cwd=work_root,
        capture_output=True,
        text=True,
        env=env,
    )
    return time.perf_counter() - t0, proc.returncode, proc.stderr


def _baseline_name(rel: str) -> str:
    return rel.replace("/", "__")


def _capture_baseline(work_root: Path, paths: list[str], baseline_dir: Path) -> None:
    """Store untouched source files (content + mtime) for scenario restore."""
    if baseline_dir.is_dir():
        shutil.rmtree(baseline_dir)
    baseline_dir.mkdir(parents=True)
    for rel in paths:
        src = work_root / rel
        if src.is_file():
            shutil.copy2(src, baseline_dir / _baseline_name(rel))


def _restore_baseline(work_root: Path, baseline_dir: Path) -> None:
    """Restore sources from baseline."""
    if not baseline_dir.is_dir():
        raise RuntimeError(f"missing baseline dir: {baseline_dir}")
    for backup in baseline_dir.iterdir():
        if not backup.is_file():
            continue
        rel = backup.name.replace("__", "/")
        dest = work_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, dest)


def _load_smoke_config():
    sys.path.insert(0, str(ROOT))
    from scip_cli.smoke_config import load_smoke_config as _load

    return _load()


def _smoke_config_hint() -> str:
    sys.path.insert(0, str(ROOT))
    from scip_cli.smoke_config import smoke_config_hint as _hint

    return _hint()


def _ensure_smoke_baseline(smoke, *, reset: bool = False) -> None:
    """Reset smoke touch files to a stable baseline for the whole gate run."""
    if reset and SMOKE_BASELINE_DIR.is_dir():
        shutil.rmtree(SMOKE_BASELINE_DIR)
    touch_paths = list(smoke.touch_large)
    if not SMOKE_BASELINE_DIR.is_dir() or not any(SMOKE_BASELINE_DIR.iterdir()):
        _capture_baseline(smoke.root, touch_paths, SMOKE_BASELINE_DIR)
    _restore_baseline(smoke.root, SMOKE_BASELINE_DIR)


def _modify_files(work_root: Path, paths: list[str], token: str) -> None:
    for rel in paths:
        path = work_root / rel
        path.write_text(path.read_text(encoding="utf-8") + f"\n// gate:{token}\n", encoding="utf-8")


def _clear_project_cache(cache: Path) -> None:
    for name in ("index.db", "index.db.next", "index.db-wal", "index.db-shm", "shards"):
        target = cache / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()
    build_info = cache / "tsbuildinfo"
    if build_info.is_dir():
        shutil.rmtree(build_info)


def _save_snapshot(snapshot: Path, cache: Path) -> None:
    if snapshot.is_dir():
        shutil.rmtree(snapshot)
    snapshot.mkdir(parents=True)
    if (cache / "index.db").is_file():
        shutil.copy2(cache / "index.db", snapshot / "index.db")
    if (cache / "shards").is_dir():
        shutil.copytree(cache / "shards", snapshot / "shards")


def _restore_snapshot(snapshot: Path, cache: Path) -> None:
    shutil.rmtree(cache / "shards", ignore_errors=True)
    if (cache / "index.db").is_file():
        (cache / "index.db").unlink()
    next_db = cache / "index.db.next"
    if next_db.is_file():
        next_db.unlink()
    if (snapshot / "shards").is_dir():
        shutil.copytree(snapshot / "shards", cache / "shards")
    if (snapshot / "index.db").is_file():
        shutil.copy2(snapshot / "index.db", cache / "index.db")


def _write_checkpoint(rows: list[BenchRow], started_at: str, branch: str, decisions: dict[str, str]) -> None:
    report = GateReport(
        started_at=started_at,
        scip_cli_version=_scip_version(),
        rows=rows,
        branch=branch,
        decisions=decisions,
    )
    latest = BENCH_DIR / ".incremental-gate-latest.json"
    latest.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")


def _append_row(
    rows: list[BenchRow],
    row: BenchRow,
    *,
    started_at: str,
    branch: str,
    decisions: dict[str, str],
) -> None:
    rows.append(row)
    _write_checkpoint(rows, started_at, branch, decisions)
    stats = "—"
    if row.reused is not None and row.reindexed is not None:
        stats = f"{row.reused}/{row.reindexed}"
    print(f"GATE_BENCH:{row.branch}:{row.label}:{row.scenario}:{row.seconds:.2f}:{stats}")


def _seed_warm_cache(
    work_root: Path,
    cache: Path,
    env_overrides: dict[str, str],
    *,
    branch: str,
    label: str,
    rows: list[BenchRow],
    started_at: str,
    decisions: dict[str, str],
) -> None:
    _clear_project_cache(cache)
    elapsed, code, stderr = _run_reindex(work_root, env_overrides)
    _append_row(
        rows,
        BenchRow(
            branch=branch,
            label=label,
            scenario="seed_cold",
            seconds=round(elapsed, 2),
            exit_code=code,
            env=dict(env_overrides),
            note="first incremental after cache clear",
        ),
        started_at=started_at,
        branch=branch,
        decisions=decisions,
    )
    if code != 0:
        raise RuntimeError(f"seed cold failed ({label}):\n{stderr[-800:]}")
    elapsed, code, stderr = _run_reindex(work_root, env_overrides)
    reused, reindexed = _parse_incremental(stderr)
    _append_row(
        rows,
        BenchRow(
            branch=branch,
            label=label,
            scenario="seed_warm",
            seconds=round(elapsed, 2),
            exit_code=code,
            reused=reused,
            reindexed=reindexed,
            env=dict(env_overrides),
        ),
        started_at=started_at,
        branch=branch,
        decisions=decisions,
    )
    if code != 0:
        raise RuntimeError(f"seed warm failed ({label}):\n{stderr[-800:]}")


def _bench_monorepo_smoke(
    smoke,
    rows: list[BenchRow],
    started_at: str,
    decisions: dict[str, str],
    scenarios: list[str],
) -> None:
    branch = "smoke"
    label = SMOKE_LABEL
    env = dict(BASE_ENV)
    smoke_root = smoke.root
    if not smoke_root.is_dir():
        _append_row(
            rows,
            BenchRow(
                branch=branch,
                label="—",
                scenario="skipped",
                seconds=0.0,
                exit_code=0,
                note=f"missing smoke root {smoke_root}",
            ),
            started_at=started_at,
            branch=branch,
            decisions=decisions,
        )
        return

    project_cache = _ensure_smoke_cache(smoke_root)
    snapshot = BENCH_DIR / "gate-smoke-snapshots" / "smoke"
    smoke_scenarios: dict[str, list[str] | None] = {
        "warm": None,
        "modify_large": list(smoke.touch_large),
    }

    _restore_baseline(smoke_root, SMOKE_BASELINE_DIR)
    _seed_warm_cache(
        smoke_root,
        project_cache,
        env,
        branch=branch,
        label=label,
        rows=rows,
        started_at=started_at,
        decisions=decisions,
    )
    _save_snapshot(snapshot, project_cache)
    for scenario in scenarios:
        paths = smoke_scenarios.get(scenario)
        _restore_baseline(smoke_root, SMOKE_BASELINE_DIR)
        _restore_snapshot(snapshot, project_cache)
        if paths:
            _modify_files(smoke_root, paths, f"{branch}-{scenario}")
        elapsed, code, stderr = _run_reindex(smoke_root, env)
        reused, reindexed = _parse_incremental(stderr)
        if code != 0:
            raise RuntimeError(f"smoke {branch}/{scenario} failed:\n{stderr[-800:]}")
        note = ""
        timing = _parse_index_timing(stderr)
        if timing:
            print(f"INDEX_TIMING:{branch}:{scenario}:{timing}")
        if scenario == "warm" and reindexed not in (None, 0):
            note = f"expected 0 reindexed on warm, got {reindexed}"
            print(f"GATE_WARN:{branch}:{scenario}:{note}")
        if timing and not note:
            note = timing
        _append_row(
            rows,
            BenchRow(
                branch=branch,
                label=label,
                scenario=scenario,
                seconds=round(elapsed, 2),
                exit_code=code,
                reused=reused,
                reindexed=reindexed,
                env=env,
                note=note,
            ),
            started_at=started_at,
            branch=branch,
            decisions=decisions,
        )


def _bench_fixture(rows: list[BenchRow], started_at: str, decisions: dict[str, str]) -> None:
    work = BENCH_DIR / "gate-fixture-work"
    if work.is_dir():
        shutil.rmtree(work)
    shutil.copytree(FIXTURE_SOURCE, work)
    _capture_baseline(work, FIXTURE_TOUCH_LARGE, FIXTURE_BASELINE_DIR)
    cache = _cache_dir(work)
    snapshot = BENCH_DIR / "gate-fixture-snapshots" / "default"
    env = dict(BASE_ENV)

    _restore_baseline(work, FIXTURE_BASELINE_DIR)
    _seed_warm_cache(
        work,
        cache,
        env,
        branch="fixture",
        label=SMOKE_LABEL,
        rows=rows,
        started_at=started_at,
        decisions=decisions,
    )
    _save_snapshot(snapshot, cache)
    _restore_baseline(work, FIXTURE_BASELINE_DIR)
    _restore_snapshot(snapshot, cache)
    elapsed, code, stderr = _run_reindex(work, env)
    reused, reindexed = _parse_incremental(stderr)
    if code != 0:
        raise RuntimeError(f"fixture warm failed:\n{stderr[-800:]}")
    note = ""
    if reindexed not in (None, 0):
        note = f"expected 0 reindexed on warm, got {reindexed}"
        print(f"GATE_WARN:fixture:warm:{note}")
    _append_row(
        rows,
        BenchRow(
            branch="fixture",
            label=SMOKE_LABEL,
            scenario="warm",
            seconds=round(elapsed, 2),
            exit_code=code,
            reused=reused,
            reindexed=reindexed,
            env=env,
            note=note,
        ),
        started_at=started_at,
        branch="fixture",
        decisions=decisions,
    )


def _print_summary(report: GateReport) -> None:
    print("\n=== Incremental gate summary ===")
    print(f"branch={report.branch}  version={report.scip_cli_version}")
    if report.decisions:
        print(f"decisions={report.decisions}")
    print(f"{'branch':<12} {'label':<10} {'scenario':<14} {'sec':>8}  stats")
    print("-" * 60)
    for row in report.rows:
        if row.scenario == "skipped":
            print(f"{row.branch:<12} {row.label:<10} {row.note}")
            continue
        stats = "—"
        if row.reused is not None and row.reindexed is not None:
            stats = f"{row.reused}/{row.reindexed}"
        print(f"{row.branch:<12} {row.label:<10} {row.scenario:<14} {row.seconds:>8.2f}  {stats}")

    if DECISIONS_PATH.is_file():
        print(f"\nDecisions file: {DECISIONS_PATH}")


@contextlib.contextmanager
def _exclusive_gate_lock():
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = BENCH_DIR / ".gate.lock"
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(
                "Another bench_incremental_gate run is active. Wait or remove the gate lock file."
            ) from None
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _resolve_scenarios(arg: str) -> list[str]:
    if arg == "both":
        return ["warm", "modify_large"]
    return [arg]


def _run_branches(args: argparse.Namespace) -> int:
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[BenchRow] = []
    started = datetime.now(timezone.utc).isoformat()
    decisions = _load_decisions()
    scenarios = _resolve_scenarios(args.scenario)

    if args.branch == "fixture":
        print("=== Fixture smoke ===")
        _bench_fixture(rows, started, decisions)
    else:
        smoke = _load_smoke_config()
        if smoke is None:
            print(f"=== Smoke skipped: {_smoke_config_hint()} ===")
            _append_row(
                rows,
                BenchRow(
                    branch="smoke",
                    label="—",
                    scenario="skipped",
                    seconds=0.0,
                    exit_code=0,
                    note="no smoke.local.json",
                ),
                started_at=started,
                branch="smoke",
                decisions=decisions,
            )
        else:
            print(f"=== Monorepo smoke (scenarios: {', '.join(scenarios)}) ===")
            _ensure_smoke_baseline(smoke, reset=args.reset_baseline)
            _bench_monorepo_smoke(smoke, rows, started, decisions, scenarios)

    report = GateReport(
        started_at=started,
        scip_cli_version=_scip_version(),
        rows=rows,
        branch=args.branch,
        decisions=decisions,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = BENCH_DIR / f"incremental-gate-{stamp}.json"
    out.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    latest = BENCH_DIR / ".incremental-gate-latest.json"
    latest.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    _print_summary(report)
    print(f"\nWrote {out}")
    print("GATE_DONE:0")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental reindex smoke benchmarks")
    parser.add_argument(
        "--branch",
        choices=("smoke", "fixture"),
        default="smoke",
        help="smoke = local monorepo (smoke.local.json); fixture = tests/fixtures/incremental-bench",
    )
    parser.add_argument(
        "--scenario",
        choices=("warm", "modify_large", "both"),
        default="both",
        help="Monorepo smoke scenarios (default both)",
    )
    parser.add_argument(
        "--reset-baseline",
        action="store_true",
        help="Recapture smoke touch-file baseline (use after a dirty prior gate run)",
    )
    args = parser.parse_args()

    _require_tooling()

    with _exclusive_gate_lock():
        return _run_branches(args)


if __name__ == "__main__":
    raise SystemExit(main())
