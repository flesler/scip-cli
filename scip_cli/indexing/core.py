"""Index entry points and SQLite database access."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from ..cache import (
    cleanup_in_progress_index,
    find_db,
    get_cache_dir,
    index_build_lock,
    index_db_path,
    promote_next_index,
)
from ..config import load_project_config
from ..discover import discover_golang_modules, discover_python_projects, discover_rust_crates
from .constants import DEFAULT_MAX_HEAP_MB
from .languages import index_golang_module, index_python_project, index_rust_crate
from .orchestrate import index_discovered_projects
from .typescript import index_typescript, typescript_projects


def format_db_size(db_path: Path) -> str:
    """Human-readable SQLite file size."""
    nbytes = Path(db_path).stat().st_size
    if nbytes < 1024:
        return f"{nbytes} B"
    if nbytes < 1024 * 1024:
        return f"{nbytes / 1024:.1f} KB"
    return f"{nbytes / (1024 * 1024):.1f} MB"


def log_index_complete(
    db_path: Path,
    lang: str,
    *,
    projects: int | None = None,
    skipped: int = 0,
) -> None:
    """One-line stderr summary after a successful index write."""
    size = format_db_size(db_path)
    suffix = ""
    if projects is not None and projects > 1:
        suffix = f", {projects} projects"
        if skipped:
            suffix += f", {skipped} skipped"
    print(f"Indexed {db_path} ({size}, {lang}{suffix})", file=sys.stderr)


def _parse_heap_mb(value, source: str) -> str:
    """Parse a positive integer heap size from config or environment."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise RuntimeError(f"Invalid {source}: expected a positive integer, got {value!r}") from None
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
        heap_mb = str(config_heap) if config_heap is not None else str(DEFAULT_MAX_HEAP_MB)
    else:
        heap_mb = str(DEFAULT_MAX_HEAP_MB)
    flag = f"--max-old-space-size={heap_mb}"
    node_options = env.get("NODE_OPTIONS", "")
    if flag not in node_options:
        env["NODE_OPTIONS"] = f"{node_options} {flag}".strip()
    return env


def index_project(root, lang, cache_dir, *, replace=False, log=True):
    """Run the language-specific indexer and convert to DB."""
    from ..project import Language

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    root = Path(root).resolve()
    env = indexer_env(root)

    if lang == Language.TYPESCRIPT:
        projects = typescript_projects(root)
        output_db, _indexed, skipped, total = index_typescript(root, cache_dir, projects, env, replace=replace)
        if log:
            log_index_complete(
                output_db,
                lang.value,
                projects=total if total > 1 else None,
                skipped=skipped,
            )
        return output_db, skipped, total

    if lang == Language.PYTHON:
        projects = discover_python_projects(root)
        output_db, _indexed, skipped, total = index_discovered_projects(
            root,
            cache_dir,
            projects,
            env,
            replace=replace,
            progress_noun="Python packages",
            index_one=index_python_project,
        )
        if log:
            log_index_complete(
                output_db,
                lang.value,
                projects=total if total > 1 else None,
                skipped=skipped,
            )
        return output_db, skipped, total

    if lang == Language.GOLANG:
        modules = discover_golang_modules(root)
        output_db, _indexed, skipped, total = index_discovered_projects(
            root,
            cache_dir,
            modules,
            env,
            replace=replace,
            progress_noun="Go modules",
            index_one=index_golang_module,
        )
        if log:
            log_index_complete(
                output_db,
                lang.value,
                projects=total if total > 1 else None,
                skipped=skipped,
            )
        return output_db, skipped, total

    if lang == Language.RUST:
        crates = discover_rust_crates(root)
        output_db, _indexed, skipped, total = index_discovered_projects(
            root,
            cache_dir,
            crates,
            env,
            replace=replace,
            progress_noun="Rust crates",
            index_one=index_rust_crate,
        )
        if log:
            log_index_complete(
                output_db,
                lang.value,
                projects=total if total > 1 else None,
                skipped=skipped,
            )
        return output_db, skipped, total

    raise RuntimeError(f"Unsupported language '{lang}'")


def get_db(project_root=None):
    """Get a sqlite3 connection to the index.db.

    If no index exists, auto-index the project with the detected language.
    Raises RuntimeError on failure.
    """
    db_path = find_db(project_root)
    if not db_path:
        from ..project import find_project_root_and_language

        root, lang = find_project_root_and_language(project_root)
        if not root:
            raise RuntimeError("Could not find project root")
        if lang is None:
            raise RuntimeError(f"No supported project markers found in {root}")

        cache_dir = get_cache_dir(root)
        with index_build_lock(cache_dir):
            db_path = find_db(project_root)
            if db_path:
                pass
            else:
                cleanup_in_progress_index(cache_dir)
                try:
                    _output_db, skipped, total = index_project(root, lang, cache_dir, replace=True, log=False)
                    promote_next_index(cache_dir)
                    log_index_complete(
                        index_db_path(cache_dir),
                        lang.value,
                        projects=total if total > 1 else None,
                        skipped=skipped,
                    )
                except RuntimeError:
                    cleanup_in_progress_index(cache_dir)
                    raise

        db_path = find_db(project_root)
        if not db_path:
            raise RuntimeError("No index.db found after indexing")

    from ..sql import configure_read_connection

    conn = sqlite3.connect(str(db_path))
    configure_read_connection(conn)
    return conn
