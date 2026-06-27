"""rdeps command - find reverse dependencies of a file."""

import sys

from ..cli_args import path_scope_from_args
from ..output import limit_and_warn
from ..paths import path_in_scope
from ..queries import get_file_symbols, get_importer_paths
from ..session import resolve_one_file, setup


def main(args):
    """Find all files that import from this file."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        limit = args.limit
        file_path = resolve_one_file(db, args.file, path_scope=path_scope)

        symbols = get_file_symbols(db, file_path)
        if not symbols:
            print(f"No symbols found in '{file_path}'", file=sys.stderr)
            sys.exit(1)

        symbol_ids = [s[0] for s in symbols]
        importers = get_importer_paths(db, symbol_ids, file_path, limit=limit + 1)
        rdeps = [path for path in importers if path_in_scope(path, path_scope)]

        if not rdeps:
            print(f"No reverse dependencies found for '{file_path}'", file=sys.stderr)
            sys.exit(1)

        sorted_rdeps = limit_and_warn(sorted(rdeps), limit, "reverse dependencies")

        for dep_path in sorted_rdeps:
            print(dep_path)
    finally:
        db.close()
