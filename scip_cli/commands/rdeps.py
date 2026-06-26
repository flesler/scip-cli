"""rdeps command - find reverse dependencies of a file."""
import sys

from ..cli_args import path_scope_from_args
from ..output import limit_and_warn
from ..paths import path_in_scope
from ..queries import get_file_symbols, get_refs_for_symbols
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
        refs = get_refs_for_symbols(db, symbol_ids)

        rdeps = set()
        for symbol_id, ref_list in refs.items():
            for ref_path, ref_line in ref_list:
                if ref_path != file_path and path_in_scope(ref_path, path_scope):
                    rdeps.add(ref_path)

        if not rdeps:
            print(f"No reverse dependencies found for '{file_path}'", file=sys.stderr)
            sys.exit(1)

        sorted_rdeps = sorted(rdeps)
        sorted_rdeps, hit_limit = limit_and_warn(sorted_rdeps, limit, "reverse dependencies")

        for dep_path in sorted_rdeps:
            print(dep_path)

        if hit_limit:
            print(f"# Warning: more than {limit} results, showing first {limit}", file=sys.stderr)
    finally:
        db.close()
