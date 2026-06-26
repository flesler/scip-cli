"""Force re-indexing of the current project."""
import shutil
import sys

from ..cache import get_cache_dir
from ..indexing import get_db
from ..project import find_project_root


def main(args):
    root = find_project_root()
    if not root:
        print("Error: Could not find project root", file=sys.stderr)
        sys.exit(1)

    cache_dir = get_cache_dir(root)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        print(f"Cleared cache at {cache_dir}", file=sys.stderr)

    print(f"Re-indexing {root}...", file=sys.stderr)
    try:
        db = get_db(root)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    db.close()
    print("Re-indexing complete", file=sys.stderr)
