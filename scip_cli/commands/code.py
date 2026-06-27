"""code command - find symbol definitions."""

import sys

from ..cli_args import path_scope_from_args
from ..output import (
    format_def_body,
    format_line_range,
    limit_and_warn,
    maybe_print_symbol_header,
    print_def_truncation_notice,
    resolve_max_def_lines,
    symbol_output_label,
)
from ..queries import get_def_location, resolve_symbol
from ..session import setup
from ..source import fallback_def_location, read_source_lines


def _resolve_symbol_groups(db, names, kind, limit, path_scope):
    """Resolve each query name; warn on stderr for misses."""
    groups = []
    for query_name in names:
        symbols = resolve_symbol(db, query_name, kind, limit=limit + 1, path_scope=path_scope)
        if not symbols:
            print(f"Symbol '{query_name}' not found", file=sys.stderr)
            continue
        groups.append((query_name, limit_and_warn(symbols, limit, "symbols")))
    return groups


def main(args):
    """Find the definition of a symbol."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        limit = args.limit
        groups = _resolve_symbol_groups(db, args.symbol, args.kind, limit, path_scope)
        total = sum(len(symbols) for _, symbols in groups)
        if total == 0:
            sys.exit(1)

        show_headers = total > 1
        snippet_mode = getattr(args, "snippet", False)
        full_mode = getattr(args, "full", False)
        offset = getattr(args, "offset", 0)
        line_numbers = getattr(args, "line_numbers", False)

        if snippet_mode:
            max_def_lines = 1
        elif full_mode:
            max_def_lines = 0
        else:
            max_def_lines = resolve_max_def_lines(getattr(args, "max_lines", None))

        printed = 0
        for query_name, symbols in groups:
            for symbol_id, symbol_str, _display_name in symbols:
                row = get_def_location(db, symbol_id)
                if not row:
                    row = fallback_def_location(db, project_root, symbol_str)
                if not row:
                    continue

                rel_path, start_line, end_line = row
                label = symbol_output_label(query_name, symbol_str, len(symbols))
                maybe_print_symbol_header(label, show_headers)

                if snippet_mode:
                    lines = read_source_lines(project_root, rel_path, start_line, start_line)
                    if lines is None:
                        print(f"{rel_path}:{format_line_range(start_line, end_line)} [file not found]")
                        printed += 1
                        continue
                    first_line = lines[0].rstrip()
                    if line_numbers:
                        first_line = f"{start_line + 1}|{first_line}"
                    print(f"{rel_path}:{format_line_range(start_line, end_line)} {first_line}")
                    printed += 1
                    continue

                lines = read_source_lines(project_root, rel_path, start_line, end_line)
                if lines is not None and offset >= len(lines):
                    print(
                        f"Warning: offset {offset} is beyond definition (lines {start_line + 1}-{end_line + 1})",
                        file=sys.stderr,
                    )

                source_snippet, truncated, shown_start, shown_end = format_def_body(
                    lines, start_line, end_line, max_lines=max_def_lines, offset=offset, line_numbers=line_numbers
                )

                print(f"{rel_path}:{format_line_range(start_line, end_line)}")
                print(source_snippet)
                if truncated:
                    print_def_truncation_notice(rel_path, start_line, end_line, shown_start, shown_end)
                printed += 1

        if printed == 0:
            sys.exit(1)
    finally:
        db.close()
