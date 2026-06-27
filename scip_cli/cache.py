"""Index cache path resolution."""

import re
from pathlib import Path

from .project import find_project_root
from .scope import project_root_hash

INDEX_DB = "index.db"
INDEX_DB_NEXT = "index.db.next"
CACHE_SLUG_MAX_LEN = 48


def index_db_path(cache_dir: Path, *, replace: bool = False) -> Path:
    return Path(cache_dir) / (INDEX_DB_NEXT if replace else INDEX_DB)


def _unlink_sqlite_sidecars(db_path: Path) -> None:
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.is_file():
            sidecar.unlink()


def cleanup_in_progress_index(cache_dir: Path) -> None:
    """Remove a failed or abandoned index.db.next build."""
    next_db = index_db_path(cache_dir, replace=True)
    if next_db.is_file():
        next_db.unlink()
    _unlink_sqlite_sidecars(next_db)


def promote_next_index(cache_dir: Path) -> None:
    """Atomically swap index.db.next over the live index.db."""
    cache_dir = Path(cache_dir)
    next_db = index_db_path(cache_dir, replace=True)
    live_db = index_db_path(cache_dir, replace=False)
    if not next_db.is_file():
        raise RuntimeError("index.db.next is missing")

    _unlink_sqlite_sidecars(live_db)
    if live_db.is_file():
        live_db.unlink()
    next_db.rename(live_db)


def project_cache_slug(project_root: Path) -> str:
    """Human-readable cache directory name for a project root."""
    root = Path(project_root).resolve()
    parts = root.parts
    slug_base = root.name or (parts[-1] if parts else "project")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug_base).strip("-") or "project"
    if len(slug) > CACHE_SLUG_MAX_LEN:
        slug = slug[:CACHE_SLUG_MAX_LEN].rstrip("-")
    digest = project_root_hash(root)[:6]
    return f"{slug}-{digest}"


def get_cache_dir(project_root):
    """Get the cache directory for a project (one dir per repo root)."""
    root = Path(project_root).resolve()
    return Path.home() / ".cache" / "scip-cli" / "projects" / project_cache_slug(root)


def find_db(project_root=None):
    """Find the index.db for the given project (or cwd)."""
    root = project_root or find_project_root()
    if not root:
        return None
    cache = index_db_path(get_cache_dir(root), replace=False)
    return cache if cache.is_file() else None
