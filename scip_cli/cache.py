"""Index cache path resolution."""
import hashlib
import json
import sys
import time
from pathlib import Path

from .config import load_project_config
from .constants import INDEX_STALE_WARN_SECONDS
from .project import find_project_root

INDEX_META_FILENAME = "index.meta.json"


def get_cache_dir(project_root):
    """Get the cache directory for a project."""
    root = Path(project_root).resolve()
    h = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    settings = load_project_config(root)
    config_key = json.dumps(
        {
            "indexRoots": settings.index_roots,
            "onlyIndexRoots": settings.only_index_roots,
        },
        sort_keys=True,
    )
    config_hash = hashlib.sha256(config_key.encode()).hexdigest()[:8]
    return Path.home() / ".cache" / "scip-cli" / "projects" / f"{h}-{config_hash}"


def find_db(project_root=None):
    """Find the index.db for the given project (or cwd)."""
    root = project_root or find_project_root()
    if not root:
        return None
    cache = get_cache_dir(root) / "index.db"
    if cache.exists():
        return cache
    return None


def write_index_meta(cache_dir, **fields):
    """Write index build metadata next to index.db."""
    cache_dir = Path(cache_dir)
    payload = {"indexed_at": time.time(), **fields}
    (cache_dir / INDEX_META_FILENAME).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )


def warn_if_stale_index(cache_dir):
    """Warn on stderr when the cached index is older than INDEX_STALE_WARN_SECONDS."""
    meta_path = Path(cache_dir) / INDEX_META_FILENAME
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        indexed_at = float(meta.get("indexed_at", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return
    if indexed_at <= 0:
        return
    age_seconds = time.time() - indexed_at
    if age_seconds >= INDEX_STALE_WARN_SECONDS:
        days = int(age_seconds // 86400)
        print(
            f"Warning: index is {days} day(s) old; run `scip-cli reindex` if results seem stale.",
            file=sys.stderr,
        )
