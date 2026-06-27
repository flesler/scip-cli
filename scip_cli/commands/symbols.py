"""symbols command - list symbols in a file."""

import sys

from ..cli_args import path_scope_from_args
from ..output import format_line_range, limit_and_warn
from ..queries import get_file_symbols
from ..session import resolve_one_file, setup
from ..symbols import extract_leaf_name, infer_kind


def main(args):
    """List all symbols in a file."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        file_path = resolve_one_file(db, args.file, path_scope=path_scope)

        limit = args.limit
        symbols = get_file_symbols(db, file_path, limit=limit + 1)
        if not symbols:
            print(f"No symbols found in '{file_path}'", file=sys.stderr)
            sys.exit(1)

        symbols = limit_and_warn(symbols, limit, "symbols")

        for _symbol_id, symbol_str, _display_name, start_line, end_line in symbols:
            if symbol_str.endswith("/"):
                continue
            kind = infer_kind(symbol_str)
            short = extract_leaf_name(symbol_str)
            line_info = format_line_range(start_line, end_line, sep="-")
            print(f"{line_info} {kind.value} {short}")
    finally:
        db.close()
