"""symbols command - list symbols in a file."""
import sys

from ..lib import (
    get_db,
    resolve_file,
    warn_ambiguous,
    get_file_symbols,
    infer_kind,
    extract_leaf_name,
)


def main(args):
    """List all symbols in a file."""
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
    
    for symbol_id, symbol_str, display_name, start_line, end_line in symbols:
        # Skip file-level symbols (end with /)
        if symbol_str.endswith('/'):
            continue
        kind = infer_kind(symbol_str)
        short = extract_leaf_name(symbol_str)
        line_info = f"{start_line + 1}-{end_line + 1}" if start_line is not None else "??"
        print(f"{line_info} {kind} {short}")
