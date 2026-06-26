"""def command - find symbol definitions."""
import sys

from ..lib import (
    setup,
    resolve_symbol,
    read_source_lines,
    infer_kind,
    get_def_location,
    format_line_range,
    limit_and_warn,
)


def main(args):
    """Find the definition of a symbol."""
    db, project_root = setup()
    try:
        limit = args.limit
        symbols = resolve_symbol(db, args.symbol, args.kind, limit=limit + 1)
        if not symbols:
            print(f"Symbol '{args.symbol}' not found", file=sys.stderr)
            sys.exit(1)

        symbols, hit_limit = limit_and_warn(symbols, limit, "symbols")

        for symbol_id, symbol_str, display_name in symbols:
            row = get_def_location(db, symbol_id)
            if not row:
                continue

            rel_path, start_line, end_line = row
            kind = infer_kind(symbol_str)

            lines = read_source_lines(project_root, rel_path, start_line, end_line)
            if lines is None:
                source_snippet = "(could not read source)"
            else:
                source_snippet = ''.join(lines).rstrip('\n')

            print(f"{rel_path}:{format_line_range(start_line, end_line)}")
            print(source_snippet)

        if hit_limit:
            print(f"# Warning: more than {limit} symbols match, showing first {limit}", file=sys.stderr)
    finally:
        db.close()
