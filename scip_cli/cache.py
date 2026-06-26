"""Index cache path resolution."""
import hashlib
import json
from pathlib import Path

from .config import load_project_config
from .project import find_project_root


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
