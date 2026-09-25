#!/usr/bin/env python3
"""Monorepo git incremental benchmarks (warm shard skip + modify_large).

Requires scripts/smoke.local.json (gitignored) — see scripts/smoke.local.example.json.

  python3 scripts/bench_fingerprint_smoke.py
  python3 scripts/bench_fingerprint_smoke.py --ratio
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "tmp" / "benchmarks"
SNAPSHOT_DIR = BENCH_DIR / "gate-smoke-snapshots" / "smoke"


def _load_smoke_config():
    sys.path.insert(0, str(ROOT))
    from scip_cli.smoke_config import load_smoke_config as _load

    return _load()


def _smoke_config_hint() -> str:
    sys.path.insert(0, str(ROOT))
    from scip_cli.smoke_config import smoke_config_hint as _hint

    return _hint()


def _restore_snapshot(cache_dir: Path) -> None:
    if not (SNAPSHOT_DIR / "index.db").is_file():
        raise SystemExit(f"missing snapshot {SNAPSHOT_DIR} — run gate smoke first")
    shutil.copy2(SNAPSHOT_DIR / "index.db", cache_dir / "index.db")
    shards = SNAPSHOT_DIR / "shards"
    if shards.is_dir():
        dest = cache_dir / "shards"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(shards, dest)


def _run_reindex(smoke_root: Path, env: dict[str, str]) -> tuple[float, str, str]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["scip-cli", "reindex"],
        cwd=smoke_root,
        capture_output=True,
        text=True,
        env=env,
    )
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    summary = next((line for line in proc.stderr.splitlines() if line.startswith("INDEX_TIMING:summary")), "")
    incremental = next((line for line in proc.stderr.splitlines() if "Incremental:" in line), "")
    return wall, incremental, summary


def _git_delta_scan(smoke_root: Path) -> float:
    sys.path.insert(0, str(ROOT))
    from scip_cli.cache import get_cache_dir
    from scip_cli.indexing.git_delta import clear_git_delta_cache, git_index_delta, git_is_ancestor
    from scip_cli.indexing.shards import load_manifest_data, shard_is_clean
    from scip_cli.indexing.typescript import typescript_projects

    clear_git_delta_cache()
    cache_dir = get_cache_dir(smoke_root)
    manifest, commit = load_manifest_data(cache_dir)
    delta = git_index_delta(smoke_root, commit) if commit and git_is_ancestor(smoke_root, commit) else None
    t0 = time.perf_counter()
    for project in typescript_projects(smoke_root):
        entry = manifest.get(project.as_posix())
        shard_is_clean(smoke_root, project, entry, commit, delta)
    return time.perf_counter() - t0


def bench_incremental(smoke_root: Path) -> None:
    env = os.environ.copy()
    env["SCIP_CLI_INDEX_TIMING"] = "1"
    _restore_snapshot(get_cache_dir_from_root(smoke_root))
    warm_wall, warm_line, warm_summary = _run_reindex(smoke_root, env)
    delta_s = _git_delta_scan(smoke_root)
    print(f"BENCH:git_delta_scan:{delta_s:.3f}s")
    print(f"BENCH:warm_reindex:{warm_wall:.3f}s")
    print(warm_line)
    print(warm_summary)

    touch = smoke_root / "packages/bulk/src/modules/module_25.ts"
    if touch.is_file():
        touch.write_text(touch.read_text(encoding="utf-8") + "\n// bench touch\n", encoding="utf-8")
        mod_wall, mod_line, mod_summary = _run_reindex(smoke_root, env)
        print(f"BENCH:modify_large:{mod_wall:.3f}s")
        print(mod_line)
        print(mod_summary)


def get_cache_dir_from_root(smoke_root: Path) -> Path:
    sys.path.insert(0, str(ROOT))
    from scip_cli.cache import get_cache_dir

    return get_cache_dir(smoke_root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ratio", action="store_true", help="(reserved) partial vs full-shard ratio bench")
    parser.parse_args()
    try:
        config = _load_smoke_config()
    except RuntimeError as exc:
        raise SystemExit(f"{exc}\n{_smoke_config_hint()}") from exc
    if config is None:
        raise SystemExit(_smoke_config_hint())
    bench_incremental(config.root)


if __name__ == "__main__":
    main()
