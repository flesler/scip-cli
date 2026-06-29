"""SCIP index building and SQLite database access."""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .cache import (
    cleanup_in_progress_index,
    find_db,
    get_cache_dir,
    index_build_lock,
    index_db_path,
    promote_next_index,
)
from .config import CONFIG_FILENAME, load_project_config, resolve_index_roots
from .debug import debug_log
from .discover import (
    discover_golang_modules,
    discover_python_projects,
    discover_rust_crates,
    discover_typescript_projects,
)
from .merge import merge_sqlite_indexes
from .scip_tool import ensure_scip_binary
from .scope import load_index_scope, projects_matching_scope

INDEX_TIMEOUT = 300
DEFAULT_MAX_HEAP_MB = 8192
PROGRESS_LOG_MIN_PROJECTS = 10
SCIP_INSTALL_URL = "https://github.com/scip-code/scip/releases"

# Pinned SCIP tool versions (minor version lock, patch bumps only).
# Revisit these periodically to confirm compatibility before bumping.
SCIP_TYPESCRIPT_VERSION = "0.4.0"
SCIP_PYTHON_VERSION = "0.6.6"
SCIP_GO_VERSION = "0.2.7"
# scip-typescript accepts many tsconfig paths per invocation (one .scip, one convert, no merge).
# Split only when SCIP_CLI_TS_INDEX_BATCH_SIZE is set (OOM/timeout tuning).
DEFAULT_TS_INDEX_BATCH_SIZE = None
MAX_TS_INDEX_BATCH_SIZE = 2_147_483_647


def default_index_workers() -> int:
    """Default parallel per-project indexers (merge stays single-threaded)."""
    return min(8, os.cpu_count() or 4)


def ts_index_batch_size() -> int | None:
    """Max TypeScript projects per scip-typescript invocation (None = all in one run)."""
    env_val = os.environ.get("SCIP_CLI_TS_INDEX_BATCH_SIZE")
    if env_val is not None:
        try:
            parsed = int(env_val)
        except ValueError:
            raise RuntimeError(
                f"Invalid SCIP_CLI_TS_INDEX_BATCH_SIZE: expected an integer, got {env_val!r}"
            ) from None
        if parsed < 1:
            raise RuntimeError(
                f"Invalid SCIP_CLI_TS_INDEX_BATCH_SIZE: expected a positive integer, got {parsed}"
            )
        if parsed > MAX_TS_INDEX_BATCH_SIZE:
            raise RuntimeError(
                f"SCIP_CLI_TS_INDEX_BATCH_SIZE={parsed} exceeds max ({MAX_TS_INDEX_BATCH_SIZE})"
            )
        return parsed
    return DEFAULT_TS_INDEX_BATCH_SIZE


def _batch_projects(projects: list[Path], batch_size: int | None) -> list[list[Path]]:
    if not projects:
        return []
    if batch_size is None:
        return [projects]
    return [projects[i : i + batch_size] for i in range(0, len(projects), batch_size)]


def _ts_batch_limit_display(batch_size: int | None, total: int) -> str:
    if batch_size is None or batch_size >= total:
        return "all tsconfigs per run"
    return f"up to {batch_size} tsconfigs per run"


def _project_label(project: Path) -> str:
    return "." if project == Path(".") else str(project)


def _project_batch_label(projects: list[Path]) -> str:
    if len(projects) == 1:
        return _project_label(projects[0])
    first = _project_label(projects[0])
    return f"{first} +{len(projects) - 1} more"


_scip_version_warned = False


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
    except subprocess.TimeoutExpired as err:
        print(f"Error: Command timed out after {INDEX_TIMEOUT} seconds", file=sys.stderr)
        raise RuntimeError("Indexing command timed out") from err


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


def typescript_projects(root: Path) -> list[Path]:
    """Resolve the TypeScript project list for a repository."""
    settings = load_project_config(root)
    scope = load_index_scope(root)

    if scope is not None:
        discovered = list(discover_typescript_projects(root))
        filtered = projects_matching_scope(discovered, scope.paths)
        if not filtered:
            joined = ", ".join(scope.paths)
            raise RuntimeError(f"No TypeScript projects found under index scope: {joined}")
        return sorted(filtered, key=str)

    configured = resolve_index_roots(root, settings) if settings.index_roots else []

    if settings.only_index_roots:
        if not configured:
            raise RuntimeError(f"onlyIndexRoots is true but no indexRoots are configured in {CONFIG_FILENAME}")
        return configured

    discovered = list(discover_typescript_projects(root))
    merged = {str(path): path for path in discovered}
    for path in configured:
        merged[str(path)] = path
    return sorted(merged.values(), key=str)


def _run_indexer_command(binary, args, cwd, env):
    """Try to run an indexer binary. Returns (success, result)."""
    try:
        result = _run_subprocess([binary, *args], cwd, env=env)
        if result.returncode == 0:
            return True, result
        if "not found" in result.stderr.lower():
            return False, result
        return True, result  # Command ran but failed - return the error
    except FileNotFoundError:
        return False, None


def _install_via_npx(package, version, args, cwd, env):
    """Install and run via npx."""
    npx_spec = f"{package}@~{version}" if version else package
    debug_log("Tool not found, trying npx (will download automatically)...")
    return _run_subprocess(["npx", "-y", npx_spec, *args], cwd, env=env)


def _install_via_go_install(package, binary, args, cwd, env):
    """Install via go install and run from ~/go/bin."""
    go_bin_dir = Path.home() / "go" / "bin"
    go_env = env.copy()
    go_env["PATH"] = f"{go_bin_dir}:{go_env.get('PATH', '')}"

    go_binary = go_bin_dir / binary
    if go_binary.exists():
        debug_log(f"Found {binary} at {go_binary}")
        go_toolchain = (
            Path.home() / "go" / "pkg" / "mod" / "golang.org" / "toolchain@v0.0.1-go1.25.11.linux-amd64" / "bin"
        )
        if go_toolchain.exists():
            go_env["PATH"] = f"{go_toolchain}:{go_env['PATH']}"
        return _run_subprocess([str(go_binary), *args], cwd, env=go_env)

    debug_log("Tool not found, installing via go install (will download to ~/go/bin)...")
    install_result = _run_subprocess(
        ["go", "install", f"{package}@latest"],
        cwd,
        env=go_env,
    )
    if install_result.returncode != 0:
        raise RuntimeError(f"Failed to install {binary} via go install: {install_result.stderr}")
    debug_log(f"{binary} installed, retrying...")
    return _run_subprocess([str(go_binary), *args], cwd, env=go_env)


def _install_via_rustup(component, binary, args, cwd, env):
    """Install via rustup component add and run."""
    debug_log(f"Tool not found, installing rustup component {component}...")
    install_result = _run_subprocess(
        ["rustup", "component", "add", component],
        cwd,
        env=env,
    )
    if install_result.returncode != 0:
        raise RuntimeError(f"Failed to install {component} via rustup: {install_result.stderr}")
    debug_log(f"{binary} installed via rustup, retrying...")
    return _run_subprocess([binary, *args], cwd, env=env)


def run_indexer_with_fallback(
    binary, args, cwd, env=None, npx_package=None, npx_version=None, go_package=None, rustup_component=None
) -> subprocess.CompletedProcess[str]:
    """Run an indexer, installing it automatically if not found."""
    run_env = env if env is not None else os.environ.copy()

    success, result = _run_indexer_command(binary, args, cwd, run_env)
    if success:
        assert result is not None
        return result

    # Binary not found - use appropriate fallback
    if go_package:
        return _install_via_go_install(go_package, binary, args, cwd, run_env)
    if rustup_component:
        return _install_via_rustup(rustup_component, binary, args, cwd, run_env)
    if npx_package:
        return _install_via_npx(npx_package, npx_version, args, cwd, run_env)

    # No fallback available - return the original error or raise if None
    if result is None:
        raise RuntimeError(f"Binary '{binary}' not found and no fallback available")
    return result


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
            + "upgrade from "
            + f"{SCIP_INSTALL_URL} if indexing fails.",
            file=sys.stderr,
        )


def _convert_scip_to_db(scip_path, db_path, *, document_path_prefix: Path | str | None = None):
    """Convert a SCIP protobuf file to a SQLite index at db_path."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    scip_binary = _resolve_scip_binary()
    _warn_old_scip(scip_binary)

    result = _run_subprocess(
        [scip_binary, "expt-convert", str(scip_path), "--output", db_path.name],
        cwd=str(db_path.parent),
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Failed to convert index")
    if not db_path.exists():
        raise RuntimeError("Failed to convert index")

    _postprocess_index(db_path)
    prefix = _document_path_prefix(document_path_prefix)
    if prefix is not None:
        _prefix_document_paths(db_path, prefix)


def _document_path_prefix(project: Path | str | None) -> str | None:
    if project is None:
        return None
    path = Path(project)
    if path == Path("."):
        return None
    return path.as_posix()


def _prefix_document_paths(db_path: Path, prefix: str) -> None:
    """Rewrite document paths to be relative to the repository root."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE documents SET relative_path = ? || '/' || relative_path",
            (prefix,),
        )
        conn.commit()
    finally:
        conn.close()


def _postprocess_index(db_path):
    """Shrink index: drop unused columns and omit prunable symbol rows (copy-filter, no DELETE)."""
    from .sql import configure_bulk_write_connection

    conn = sqlite3.connect(str(db_path))
    try:
        configure_bulk_write_connection(conn)
        # Rebuild tables first; indexes are recreated once at the end (expt-convert indexes
        # are dropped with table swaps — avoid maintaining them during bulk inserts).
        _trim_unused_columns(conn)
        _trim_mentions_to_known_symbols(conn)
        _trim_defn_to_known_symbols(conn)
        _recreate_postprocess_indexes(conn)
        conn.commit()
    finally:
        conn.close()


def _replace_table(conn, old_name: str, new_name: str) -> None:
    conn.execute(f"DROP TABLE {old_name}")
    conn.execute(f"ALTER TABLE {new_name} RENAME TO {old_name}")


def _trim_unused_columns(conn):
    """Remove columns we never use; omit variable symbols while rebuilding global_symbols."""
    conn.execute("""
        CREATE TABLE documents_new (
            id INTEGER PRIMARY KEY,
            relative_path TEXT NOT NULL UNIQUE
        )
    """)
    conn.execute("INSERT INTO documents_new (id, relative_path) SELECT id, relative_path FROM documents")
    _replace_table(conn, "documents", "documents_new")

    from .symbols import sql_exclude_variable_symbols

    exclude = sql_exclude_variable_symbols("symbol")
    conn.execute("""
        CREATE TABLE global_symbols_new (
            id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL UNIQUE,
            display_name TEXT,
            kind INTEGER
        )
    """)
    conn.execute(f"""
        INSERT INTO global_symbols_new (id, symbol, display_name, kind)
        SELECT id, symbol, display_name, kind FROM global_symbols
        WHERE {exclude}
    """)
    _replace_table(conn, "global_symbols", "global_symbols_new")


def _trim_mentions_to_known_symbols(conn):
    """Copy mentions that reference retained symbols (drops variable refs without DELETE)."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mentions' LIMIT 1").fetchone():
        return
    conn.execute("""
        CREATE TABLE mentions_new (
            chunk_id INTEGER NOT NULL,
            symbol_id INTEGER NOT NULL,
            role INTEGER NOT NULL,
            PRIMARY KEY (chunk_id, symbol_id, role)
        )
    """)
    conn.execute("""
        INSERT INTO mentions_new (chunk_id, symbol_id, role)
        SELECT m.chunk_id, m.symbol_id, m.role
        FROM mentions m
        JOIN global_symbols g ON g.id = m.symbol_id
    """)
    _replace_table(conn, "mentions", "mentions_new")


def _trim_defn_to_known_symbols(conn):
    """Copy defn rows for retained symbols only."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='defn_enclosing_ranges' LIMIT 1"
    ).fetchone():
        return
    conn.execute("""
        CREATE TABLE defn_enclosing_ranges_new (
            id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL,
            symbol_id INTEGER NOT NULL,
            start_line INTEGER NOT NULL,
            start_char INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            end_char INTEGER NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO defn_enclosing_ranges_new (
            id, document_id, symbol_id, start_line, start_char, end_line, end_char
        )
        SELECT d.id, d.document_id, d.symbol_id, d.start_line, d.start_char, d.end_line, d.end_char
        FROM defn_enclosing_ranges d
        JOIN global_symbols g ON g.id = d.symbol_id
    """)
    _replace_table(conn, "defn_enclosing_ranges", "defn_enclosing_ranges_new")


def _recreate_postprocess_indexes(conn: sqlite3.Connection) -> None:
    """expt-convert indexes are dropped when tables are rebuilt."""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_global_symbols_symbol ON global_symbols(symbol)")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mentions' LIMIT 1").fetchone():
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mentions_symbol_id_role ON mentions(symbol_id, role)"
        )


def _typescript_index_args(root, output_scip, projects):
    args = ["index", "--output", str(output_scip)]
    root = Path(root)
    if not (root / "tsconfig.json").exists():
        args.insert(1, "--infer-tsconfig")
    args.extend(str(project) for project in projects)
    return args


def _index_workers():
    """Parallel workers for per-project indexer runs (merge stays serial)."""
    env_val = os.environ.get("SCIP_CLI_INDEX_WORKERS")
    if env_val is not None:
        try:
            return max(1, int(env_val))
        except ValueError:
            raise RuntimeError(f"Invalid SCIP_CLI_INDEX_WORKERS: expected an integer, got {env_val!r}") from None
    return default_index_workers()


def _index_ts_projects(root, projects, work_dir, env, *, output_db: Path | None = None):
    """Index one or more TypeScript projects into work_dir/index.db (or output_db when set)."""
    root = Path(root)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = _project_batch_label(projects)
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    index_args = _typescript_index_args(root, part_scip, projects)
    result = run_indexer_with_fallback(
        "scip-typescript",
        index_args,
        str(root),
        env=env,
        npx_package="@sourcegraph/scip-typescript",
        npx_version=SCIP_TYPESCRIPT_VERSION,
    )
    if result.returncode != 0:
        return label, None, result.stderr.strip() or "indexing failed"
    try:
        _convert_scip_to_db(part_scip, db_path)
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None


def _finalize_part_dbs(part_dbs: list[Path], output_db: Path) -> None:
    if len(part_dbs) == 1:
        if part_dbs[0] != output_db:
            shutil.move(str(part_dbs[0]), str(output_db))
    else:
        merge_sqlite_indexes(part_dbs, output_db)


def _index_discovered_projects(
    root: Path,
    cache_dir: Path,
    projects: list[Path],
    env,
    *,
    replace: bool,
    progress_noun: str,
    index_one,
) -> tuple[Path, int, int, int]:
    """Index one SCIP unit per project path; merge when multiple part DBs."""
    output_db = index_db_path(cache_dir, replace=replace)
    workers = _index_workers()
    total = len(projects)
    use_parallel = total > 1 and workers > 1
    show_progress = total > PROGRESS_LOG_MIN_PROJECTS

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        part_dbs: list[Path] = []
        skipped = 0

        if show_progress and use_parallel:
            print(
                f"Indexing {total} {progress_noun} ({workers} workers; merge is serial)...",
                file=sys.stderr,
            )

        if use_parallel:
            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        index_one,
                        root,
                        project,
                        tmpdir_path / f"part-{index}",
                        env,
                    ): (index, project)
                    for index, project in enumerate(projects, start=1)
                }
                indexed_parts: list[tuple[int, Path]] = []
                for future in as_completed(futures):
                    part_index, project = futures[future]
                    label, db_path, error = future.result()
                    completed += 1
                    if db_path is None:
                        skipped += 1
                        print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                    else:
                        indexed_parts.append((part_index, db_path))
                        if show_progress:
                            print(f"Indexed {completed}/{total}: {label}", file=sys.stderr)
            part_dbs = [db for _, db in sorted(indexed_parts, key=lambda item: item[0])]
        else:
            for index, project in enumerate(projects, start=1):
                label = _project_label(project)
                if show_progress:
                    print(f"Indexing {index}/{total}: {label}", file=sys.stderr)
                direct_output = output_db if total == 1 else None
                label, db_path, error = index_one(
                    root,
                    project,
                    cache_dir if direct_output else tmpdir_path / f"part-{index}",
                    env,
                    output_db=direct_output,
                )
                if db_path is None:
                    skipped += 1
                    print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                    continue
                part_dbs.append(db_path)

        if not part_dbs:
            raise RuntimeError("Failed to index project")

        _finalize_part_dbs(part_dbs, output_db)
        return output_db, len(part_dbs), skipped, total


def _project_cwd(root: Path, project: Path) -> Path:
    return root if project == Path(".") else root / project


def _index_python_project(root, project, work_dir, env, *, output_db=None):
    """Index one Python package directory into work_dir/index.db (or output_db when set)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = _project_label(Path(project))
    cwd = _project_cwd(Path(root), Path(project))
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    result = run_indexer_with_fallback(
        "scip-python",
        ["index", ".", "--output", str(part_scip)],
        str(cwd),
        env=env,
        npx_package="@sourcegraph/scip-python",
        npx_version=SCIP_PYTHON_VERSION,
    )
    if result.returncode != 0:
        return label, None, result.stderr.strip() or "indexing failed"
    try:
        _convert_scip_to_db(part_scip, db_path, document_path_prefix=project)
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None


def _index_golang_module(root, module, work_dir, env, *, output_db=None):
    """Index one Go module directory into work_dir/index.db (or output_db when set)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = _project_label(Path(module))
    cwd = _project_cwd(Path(root), Path(module))
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    result = run_indexer_with_fallback(
        "scip-go",
        ["--output", str(part_scip)],
        str(cwd),
        env=env,
        go_package="github.com/scip-code/scip-go/cmd/scip-go",
    )
    if result.returncode != 0:
        return label, None, result.stderr.strip() or "indexing failed"
    try:
        _convert_scip_to_db(part_scip, db_path, document_path_prefix=module)
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None


def _index_rust_crate(root, crate, work_dir, env, *, output_db=None):
    """Index one Rust crate directory into work_dir/index.db (or output_db when set)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = _project_label(Path(crate))
    cwd = _project_cwd(Path(root), Path(crate))
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    result = run_indexer_with_fallback(
        "rust-analyzer",
        ["scip", str(cwd), "--output", str(part_scip)],
        str(cwd),
        env=env,
        rustup_component="rust-analyzer",
    )
    if result.returncode != 0:
        return label, None, result.stderr.strip() or "indexing failed"
    try:
        _convert_scip_to_db(part_scip, db_path, document_path_prefix=crate)
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None


def _index_typescript(root, cache_dir, projects, env, *, replace=False):
    """Index one or more TypeScript projects and write the merged index.db."""
    root = Path(root)
    cache_dir = Path(cache_dir)
    output_db = index_db_path(cache_dir, replace=replace)
    workers = _index_workers()
    batches = _batch_projects(projects, ts_index_batch_size())
    use_parallel = len(batches) > 1 and workers > 1

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        part_dbs: list[Path] = []
        skipped = 0
        total = len(projects)
        show_progress = total > PROGRESS_LOG_MIN_PROJECTS

        if show_progress and use_parallel:
            batch_size = ts_index_batch_size()
            batch_desc = _ts_batch_limit_display(batch_size, total)
            print(
                f"Indexing {total} TypeScript projects "
                f"({workers} workers, {batch_desc}; merge is serial)...",
                file=sys.stderr,
            )

        if use_parallel:
            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(
                        _index_ts_projects,
                        root,
                        batch,
                        tmpdir_path / f"part-{index}",
                        env,
                    ): (index, batch)
                    for index, batch in enumerate(batches, start=1)
                }
                indexed_parts: list[tuple[int, Path]] = []
                for future in as_completed(futures):
                    batch_index, batch = futures[future]
                    label, db_path, error = future.result()
                    completed += len(batch)
                    if db_path is None:
                        skipped += len(batch)
                        print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                    else:
                        indexed_parts.append((batch_index, db_path))
                        if show_progress:
                            print(f"Indexed {completed}/{total}: {label}", file=sys.stderr)
            part_dbs = [db for _, db in sorted(indexed_parts, key=lambda item: item[0])]
        else:
            indexed = 0
            for index, batch in enumerate(batches, start=1):
                label = _project_batch_label(batch)
                if show_progress:
                    end = indexed + len(batch)
                    print(f"Indexing {indexed + 1}-{end}/{total}: {label}", file=sys.stderr)
                direct_output = output_db if len(batches) == 1 else None
                label, db_path, error = _index_ts_projects(
                    root,
                    batch,
                    cache_dir if direct_output else tmpdir_path / f"part-{index}",
                    env,
                    output_db=direct_output,
                )
                indexed += len(batch)
                if db_path is None:
                    skipped += len(batch)
                    print(f"Warning: skipped {label}: {error}", file=sys.stderr)
                    continue
                part_dbs.append(db_path)

        if not part_dbs:
            raise RuntimeError("Failed to index project")

        _finalize_part_dbs(part_dbs, output_db)

        return output_db, len(part_dbs), skipped, total


def index_project(root, lang, cache_dir, *, replace=False, log=True):
    """Run the language-specific indexer and convert to DB."""
    from .project import Language

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    root = Path(root).resolve()
    env = indexer_env(root)

    if lang == Language.TYPESCRIPT:
        projects = typescript_projects(root)
        output_db, _indexed, skipped, total = _index_typescript(root, cache_dir, projects, env, replace=replace)
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
        output_db, _indexed, skipped, total = _index_discovered_projects(
            root,
            cache_dir,
            projects,
            env,
            replace=replace,
            progress_noun="Python packages",
            index_one=_index_python_project,
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
        output_db, _indexed, skipped, total = _index_discovered_projects(
            root,
            cache_dir,
            modules,
            env,
            replace=replace,
            progress_noun="Go modules",
            index_one=_index_golang_module,
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
        output_db, _indexed, skipped, total = _index_discovered_projects(
            root,
            cache_dir,
            crates,
            env,
            replace=replace,
            progress_noun="Rust crates",
            index_one=_index_rust_crate,
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
        from .project import find_project_root_and_language

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

    from .sql import configure_read_connection

    conn = sqlite3.connect(str(db_path))
    configure_read_connection(conn)
    return conn
