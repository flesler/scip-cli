"""symbols command - list symbols in a file."""

import sys
from collections import Counter

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

        if getattr(args, "freq", False):
            symbols = _sort_by_frequency(symbols)

        for _symbol_id, symbol_str, _display_name, start_line, end_line in symbols:
            if symbol_str.endswith("/"):
                continue
            kind = infer_kind(symbol_str)
            short = extract_leaf_name(symbol_str)
            line_info = format_line_range(start_line, end_line, sep="-")
            print(f"{line_info} {kind.value} {short}")
    finally:
        db.close()


# pyright: ignore[reportMissingTypeArgument, reportUnknownLambdaType]
def _sort_by_frequency(symbols):
    """Sort symbols by frequency of their leaf name (most common first).

    For ties, sort alphabetically by name.
    """
    # Extract leaf names and count frequencies
    name_counts = Counter()
    symbol_data = []

    for symbol_id, symbol_str, display_name, start_line, end_line in symbols:
        if symbol_str.endswith("/"):
            continue
        short = extract_leaf_name(symbol_str)
        name_counts[short] += 1
        symbol_data.append((symbol_id, symbol_str, display_name, start_line, end_line, short))

    # Sort by frequency (descending), then by name (ascending) for ties
    symbol_data.sort(key=lambda x: (-name_counts[x[5]], x[5]))

    # Return original tuple format (without the extra short name)
    return [(s[0], s[1], s[2], s[3], s[4]) for s in symbol_data]
