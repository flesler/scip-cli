"""symbols command - list symbols in a file."""
import sys

from ..lib import (
    setup,
    resolve_one_file,
    get_file_symbols,
    infer_kind,
    extract_leaf_name,
    format_line_range,
)


def main(args):
    """List all symbols in a file."""
    db, _ = setup()
    try:
        file_path = resolve_one_file(db, args.file)

        symbols = get_file_symbols(db, file_path)
        if not symbols:
            print(f"No symbols found in '{file_path}'", file=sys.stderr)
            sys.exit(1)

        for symbol_id, symbol_str, display_name, start_line, end_line in symbols:
            if symbol_str.endswith('/'):
                continue
            kind = infer_kind(symbol_str)
            short = extract_leaf_name(symbol_str)
            line_info = format_line_range(start_line, end_line, sep="-")
            print(f"{line_info} {kind} {short}")
    finally:
        db.close()
