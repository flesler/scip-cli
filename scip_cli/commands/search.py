"""search command - search symbols by pattern."""
import sys
import re

from ..lib import (
    setup,
    infer_kind,
    escape_like,
    SymbolKind,
)


def parse_symbol(symbol):
    """Parse SCIP symbol into (file_path, symbol_name).
    
    Works with TypeScript and Python SCIP formats.
    
    Examples:
        TypeScript: scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation().
        -> ('src/hooks/useDictation.ts', 'useDictation()')
        
        Python: scip-python pip mypackage src/module.py/MyClass#method().
        -> ('src/module.py', 'MyClass#method()')
    """
    # Try backtick format first (TypeScript)
    match = re.search(r'`([^`]+)`', symbol)
    if match:
        filename = match.group(1)
        before = symbol[:match.start()]
        parts = before.split()
        if len(parts) >= 5:
            dir_path = ' '.join(parts[4:])
            file_path = dir_path + filename
        else:
            file_path = filename

        after_file = symbol[match.end():]
        if after_file.startswith('/'):
            after_file = after_file[1:]

        symbol_name = after_file.rstrip('.')
        return (file_path, symbol_name)
    
    # Python format: look for .py/ pattern
    py_match = re.search(r'(\S+\.py)/(.+)$', symbol)
    if py_match:
        return (py_match.group(1), py_match.group(2))
    
    return ('?', '?')


def is_noisy_symbol(symbol_str):
    """Filter out noisy symbols (file-level, parameters, etc)."""
    if symbol_str.endswith('/'):
        return True
    if symbol_str.endswith('/__init__:'):
        return True
    if 'typeLiteral' in symbol_str:
        return True
    if ').(' in symbol_str:
        return True
    return False


def kind_to_display(kind):
    """Convert kind to display format."""
    kind_map = {
        SymbolKind.FUNCTION: 'Function',
        SymbolKind.METHOD: 'Method',
        SymbolKind.CLASS: 'Class',
        SymbolKind.PROPERTY: 'Property',
        SymbolKind.VARIABLE: 'Variable',
    }
    return kind_map.get(kind, 'Unknown')


def main(args):
    """Search symbols by pattern."""
    db, _ = setup()
    try:
        limit = args.limit
        # Escape LIKE wildcards in user pattern
        escaped_pattern = escape_like(args.pattern)
        
        # When filtering by kind, don't LIMIT in SQL to avoid missing results
        # Apply LIMIT after filtering in Python
        if args.kind:
            rows = db.execute("""
                SELECT gs.id, gs.symbol, gs.display_name, der.start_line
                FROM global_symbols gs
                LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
                WHERE gs.symbol LIKE ? ESCAPE '\\'
            """, (f"%{escaped_pattern}%",)).fetchall()
            
            # Apply kind filter in Python
            rows = [r for r in rows if infer_kind(r[1]) == args.kind]
            
            # Apply LIMIT after filtering
            hit_limit = len(rows) > limit
            rows = rows[:limit]
        else:
            rows = db.execute(f"""
                SELECT gs.id, gs.symbol, gs.display_name, der.start_line
                FROM global_symbols gs
                LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
                WHERE gs.symbol LIKE ? ESCAPE '\\'
                LIMIT {limit + 1}
            """, (f"%{escaped_pattern}%",)).fetchall()
            hit_limit = len(rows) > limit
            rows = rows[:limit]

        if not rows:
            if args.kind:
                print(f"No {args.kind} symbols found matching '{args.pattern}'", file=sys.stderr)
            else:
                print(f"No symbols found matching '{args.pattern}'", file=sys.stderr)
            sys.exit(1)

        for symbol_id, symbol_str, display_name, start_line in rows:
            if is_noisy_symbol(symbol_str):
                continue

            kind = infer_kind(symbol_str)
            file_path, symbol_name = parse_symbol(symbol_str)

            line = start_line + 1 if start_line is not None else '?'

            symbol_name = symbol_name.rstrip('.#')
            if symbol_name.endswith('()'):
                symbol_name = symbol_name[:-2]

            kind_display = kind_to_display(kind)
            print(f"{file_path}:{line} {kind_display} {symbol_name}")

        if hit_limit:
            print(f"# Warning: more than {limit} results, showing first {limit}", file=sys.stderr)
    finally:
        db.close()
