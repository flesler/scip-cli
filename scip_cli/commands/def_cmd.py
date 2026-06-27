"""def command - find symbol definitions."""
import sys

from ..cli_args import path_scope_from_args
from ..output import (
    format_def_body,
    format_line_range,
    limit_and_warn,
    print_def_truncation_notice,
    resolve_max_def_lines,
)
from ..queries import get_def_location, resolve_symbol
from ..session import setup
from ..source import fallback_def_location, read_source_lines


def main(args):
    """Find the definition of a symbol."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        limit = args.limit
        symbols = resolve_symbol(
            db, args.symbol, args.kind, limit=limit + 1, path_scope=path_scope
        )
        if not symbols:
            print(f"Symbol '{args.symbol}' not found", file=sys.stderr)
            sys.exit(1)

        symbols = limit_and_warn(symbols, limit, "symbols")
        max_def_lines = resolve_max_def_lines(getattr(args, "max_lines", None))

        for symbol_id, symbol_str, _display_name in symbols:
            row = get_def_location(db, symbol_id)
            if not row:
                row = fallback_def_location(db, project_root, symbol_str)
            if not row:
                continue

            rel_path, start_line, end_line = row

            lines = read_source_lines(project_root, rel_path, start_line, end_line)
            source_snippet, truncated, shown_start, shown_end = format_def_body(
                lines, start_line, end_line, max_lines=max_def_lines
            )

            print(f"{rel_path}:{format_line_range(start_line, end_line)}")
            print(source_snippet)
            if truncated:
                print_def_truncation_notice(
                    rel_path, start_line, end_line, shown_start, shown_end
                )
    finally:
        db.close()
