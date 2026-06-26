"""rdeps command - find reverse dependencies of a file."""
import sys

from ..lib import (
    get_db,
    resolve_file,
    warn_ambiguous,
    get_file_symbols,
    get_refs_for_symbols,
)


def main(args):
    """Find all files that import from this file."""
    db = get_db()
    
    # Resolve file pattern to actual path
    files = resolve_file(db, args.file)
    if not files:
        print(f"File '{args.file}' not found", file=sys.stderr)
        sys.exit(1)
    
    if len(files) > 1:
        warn_ambiguous(args.file, files, "file")
    
    file_path = files[0]
    
    # Get all symbols defined in this file
    symbols = get_file_symbols(db, file_path)
    if not symbols:
        print(f"No symbols found in '{file_path}'", file=sys.stderr)
        sys.exit(1)
    
    # Get all symbol IDs
    symbol_ids = [s[0] for s in symbols]
    
    # Find all references to these symbols from OTHER files in one query
    refs = get_refs_for_symbols(db, symbol_ids)
    
    # Collect unique file paths that reference this file
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
