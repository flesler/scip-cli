"""rdeps command - find reverse dependencies of a file."""
import sys

from ..lib import (
    setup,
    resolve_one_file,
    get_file_symbols,
    get_refs_for_symbols,
)


def main(args):
    """Find all files that import from this file."""
    db, _ = setup()
    try:
        file_path = resolve_one_file(db, args.file)

        symbols = get_file_symbols(db, file_path)
        if not symbols:
            print(f"No symbols found in '{file_path}'", file=sys.stderr)
            sys.exit(1)

        symbol_ids = [s[0] for s in symbols]
        refs = get_refs_for_symbols(db, symbol_ids)

        rdeps = set()
        for symbol_id, ref_list in refs.items():
            for ref_path, ref_line in ref_list:
                if ref_path != file_path:
                    rdeps.add(ref_path)

        if not rdeps:
            print(f"No reverse dependencies found for '{file_path}'", file=sys.stderr)
            sys.exit(1)

        for dep_path in sorted(rdeps):
            print(dep_path)
    finally:
        db.close()
