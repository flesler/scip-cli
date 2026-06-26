"""members command - list members of a class/interface."""
import sys
import re

from ..lib import (
    setup,
    resolve_one_symbol,
    get_members,
    get_def_location,
    infer_kind,
    extract_leaf_name,
    read_source_lines,
    format_line_range,
    SymbolKind,
)


def _member_source_patterns(member_symbol, short, kind):
    """Build TS/JS and Python regex patterns for finding a member's source line."""
    if "<constructor>" in member_symbol:
        ts_pattern = r'^\s*constructor\s*\('
    elif "<get>" in member_symbol:
        ts_pattern = rf'^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+)*get\s+{re.escape(short)}\s*\('
    elif "<set>" in member_symbol:
        ts_pattern = rf'^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+)*set\s+{re.escape(short)}\s*\('
    else:
        ts_pattern = rf'^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+)*{re.escape(short)}\s*\??\s*[:=(]'

    py_pattern = None
    if kind == SymbolKind.METHOD:
        py_pattern = rf'^\s*(?:async\s+)?def\s+{re.escape(short)}\s*\('
    elif kind == SymbolKind.PROPERTY:
        py_pattern = rf'^\s*{re.escape(short)}\s*[=:]'
    elif kind == SymbolKind.CLASS:
        py_pattern = rf'^\s*class\s+{re.escape(short)}\s*[:\(]'

    return ts_pattern, py_pattern


def main(args):
    """List members of a class or interface."""
    db, project_root = setup()
    try:
        symbol_id, _, _ = resolve_one_symbol(db, args.symbol)
        members = get_members(db, symbol_id)

        if not members:
            print(f"No members found for '{args.symbol}'", file=sys.stderr)
            sys.exit(1)

        parent_def = get_def_location(db, symbol_id)
        parent_file = parent_def[0] if parent_def else None
        parent_start = parent_def[1] if parent_def else None
        parent_end = parent_def[2] if parent_def else None

        needs_lookup = any(m[3] is None for m in members)
        source_lines = None
        if needs_lookup and project_root and parent_file and parent_start is not None:
            source_lines = read_source_lines(project_root, parent_file, parent_start, parent_end)

        for member_id, member_symbol, member_name, start_line, end_line in members:
            kind = infer_kind(member_symbol)
            short = extract_leaf_name(member_symbol)

            if start_line is None and source_lines:
                ts_pattern, py_pattern = _member_source_patterns(member_symbol, short, kind)
                patterns = []
                if parent_file and parent_file.endswith('.py'):
                    if py_pattern:
                        patterns.append(py_pattern)
                    patterns.append(ts_pattern)
                else:
                    patterns.append(ts_pattern)
                    if py_pattern:
                        patterns.append(py_pattern)

                for i, line in enumerate(source_lines):
                    if any(re.match(p, line) for p in patterns):
                        start_line = parent_start + i
                        end_line = start_line
                        break

            line_info = format_line_range(start_line, end_line)
            print(f"{line_info} {kind} {short}")
    finally:
        db.close()
