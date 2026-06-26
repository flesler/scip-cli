"""SCIP index building and SQLite database access."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from .cache import find_db, get_cache_dir
from .config import CONFIG_FILENAME, load_project_config, resolve_index_roots
from .constants import DEFAULT_MAX_HEAP_MB, INDEX_TIMEOUT, SCIP_INSTALL_URL
from .discover import discover_typescript_projects
from .merge import merge_sqlite_indexes
from .project import detect_language, find_project_root
from .scip_tool import ensure_scip_binary

_scip_version_warned = False


def _run_subprocess(cmd, cwd, env=None):
    """Run subprocess with timeout; raise RuntimeError on timeout."""
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=INDEX_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(f"Error: Command timed out after {INDEX_TIMEOUT} seconds", file=sys.stderr)
        raise RuntimeError("Indexing command timed out")


def _parse_heap_mb(value, source: str) -> str:
    """Parse a positive integer heap size from config or environment."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise RuntimeError(
            f"Invalid {source}: expected a positive integer, got {value!r}"
        ) from None
    if type(value) is bool or parsed <= 0:
        raise RuntimeError(f"Invalid {source}: expected a positive integer")
    return str(parsed)


def indexer_env(project_root=None):
    """Return subprocess env with a generous Node heap for language indexers."""
    env = os.environ.copy()
    heap_mb = os.environ.get("SCIP_CLI_MAX_HEAP_MB")
    if heap_mb is not None:
        heap_mb = _parse_heap_mb(heap_mb, "SCIP_CLI_MAX_HEAP_MB")
    elif project_root is not None:
        config_heap = load_project_config(Path(project_root)).max_heap_mb
        heap_mb = (
            str(config_heap) if config_heap is not None else str(DEFAULT_MAX_HEAP_MB)
        )
    else:
        heap_mb = str(DEFAULT_MAX_HEAP_MB)
    flag = f"--max-old-space-size={heap_mb}"
    node_options = env.get("NODE_OPTIONS", "")
    if flag not in node_options:
        env["NODE_OPTIONS"] = f"{node_options} {flag}".strip()
    return env


def typescript_projects(root: Path) -> list[Path]:
    """Resolve the TypeScript project list for a repository."""
    settings = load_project_config(root)
    configured = resolve_index_roots(root, settings) if settings.index_roots else []

    if settings.only_index_roots:
        if not configured:
            raise RuntimeError(
                f"onlyIndexRoots is true but no indexRoots are configured in {CONFIG_FILENAME}"
            )
        return configured

    discovered = list(discover_typescript_projects(root))
    merged = {str(path): path for path in discovered}
    for path in configured:
        merged[str(path)] = path
    return sorted(merged.values(), key=str)


def run_with_fallback(binary, npx_package, cwd, args, env=None):
    """Try binary first, fallback to npx if not found."""
    run_env = env if env is not None else os.environ.copy()
    try:
        result = _run_subprocess([binary] + args, cwd, env=run_env)
        if result.returncode == 0:
            return result
        if "not found" in result.stderr.lower():
            print("Tool not found, trying npx (will download automatically)...", file=sys.stderr)
            return _run_subprocess(["npx", "-y", npx_package] + args, cwd, env=run_env)
        return result
    except FileNotFoundError:
        print("Tool not found, trying npx (will download automatically)...", file=sys.stderr)
        return _run_subprocess(["npx", "-y", npx_package] + args, cwd, env=run_env)


def _scip_version(binary):
    result = _run_subprocess([binary, "--version"], cwd=os.getcwd())
    if result.returncode != 0:
        return None
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", result.stdout + result.stderr)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _resolve_scip_binary():
    """Locate the scip CLI used to convert protobuf indexes to SQLite."""
    return str(ensure_scip_binary())


def _warn_old_scip(binary):
    global _scip_version_warned
    if _scip_version_warned:
        return
    version = _scip_version(binary)
    if version and version < (0, 8, 0):
        _scip_version_warned = True
        print(
            f"Warning: {binary} {'.'.join(map(str, version))} is older than 0.8.0; "
            "upgrade from "
            f"{SCIP_INSTALL_URL} if indexing fails.",
            file=sys.stderr,
        )


def _convert_scip_to_db(scip_path, cache_dir):
    """Convert a SCIP protobuf file to SQLite in cache_dir/index.db."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    db_path = cache_dir / "index.db"
    if db_path.exists():
        db_path.unlink()

    scip_binary = _resolve_scip_binary()
    _warn_old_scip(scip_binary)

    result = _run_subprocess(
        [scip_binary, "expt-convert", str(scip_path), "--output", "index.db"],
        cwd=str(cache_dir),
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Failed to convert index")
    if not db_path.exists():
        raise RuntimeError("Failed to convert index")


def _typescript_index_args(root, output_scip, projects):
    args = ["index", "--output", str(output_scip)]
    root = Path(root)
    if not (root / "tsconfig.json").exists():
        args.insert(1, "--infer-tsconfig")
    args.extend(str(project) for project in projects)
    return args


def _index_typescript(root, cache_dir, projects, env):
    """Index one or more TypeScript projects and write cache_dir/index.db."""
    root = Path(root)
    cache_dir = Path(cache_dir)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        part_dbs: list[Path] = []
        skipped = 0

        for index, project in enumerate(projects, start=1):
            label = "." if project == Path(".") else str(project)
            if len(projects) > 1:
                print(
                    f"Indexing TypeScript project {index}/{len(projects)}: {label}",
                    file=sys.stderr,
                )

            part_scip = tmpdir_path / f"part-{index}.scip"
            index_args = _typescript_index_args(root, part_scip, [project])
            result = run_with_fallback(
                "scip-typescript",
                "@sourcegraph/scip-typescript",
                str(root),
                index_args,
                env=env,
            )
            if result.returncode != 0:
                skipped += 1
                print(
                    f"Warning: skipped {label}: {result.stderr.strip() or 'indexing failed'}",
                    file=sys.stderr,
                )
                continue

            part_cache = tmpdir_path / f"part-{index}"
            _convert_scip_to_db(part_scip, part_cache)
            part_dbs.append(part_cache / "index.db")

        if not part_dbs:
            raise RuntimeError("Failed to index project")

        indexed = len(part_dbs)
        total = len(projects)
        if total > 1:
            print(
                f"Indexed {indexed}/{total} TypeScript projects"
                + (f" ({skipped} skipped)" if skipped else ""),
                file=sys.stderr,
            )

        if len(part_dbs) == 1:
            shutil.copy2(part_dbs[0], cache_dir / "index.db")
            return

        merge_sqlite_indexes(part_dbs, cache_dir / "index.db")


def _index_project(root, lang, cache_dir):
    """Run the language-specific indexer and convert to DB."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    root = Path(root).resolve()
    env = indexer_env(root)

    if lang == "typescript":
        projects = typescript_projects(root)
        if len(projects) > 1:
            print(
                f"Indexing {len(projects)} TypeScript projects",
                file=sys.stderr,
            )
        _index_typescript(root, cache_dir, projects, env)
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        index_scip = os.path.join(tmpdir, "index.scip")
        if lang == "python":
            result = run_with_fallback(
                "scip-python",
                "@sourcegraph/scip-python",
                str(root),
                ["index", ".", "--output", index_scip],
                env=env,
            )
        else:
            raise RuntimeError(f"Unsupported language '{lang}'")

        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            raise RuntimeError("Failed to index project")

        _convert_scip_to_db(index_scip, cache_dir)


def get_db(project_root=None):
    """Get a sqlite3 connection to the index.db.

    If no index exists, auto-index the project with the detected language.
    Raises RuntimeError on failure.
    """
    db_path = find_db(project_root)
    if not db_path:
        root = project_root or find_project_root()
        if not root:
            raise RuntimeError("Could not find project root")

        lang = detect_language(root)
        if lang is None:
            raise RuntimeError(f"No supported project markers found in {root}")

        print(f"Auto-indexing {root} ({lang})...", file=sys.stderr)
        cache_dir = get_cache_dir(root)
        _index_project(root, lang, cache_dir)

        db_path = find_db(project_root)
        if not db_path:
            raise RuntimeError("No index.db found after indexing")

    return sqlite3.connect(str(db_path))
