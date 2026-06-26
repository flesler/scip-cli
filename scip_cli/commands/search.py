"""search command - search symbols by pattern."""
import sys
import re

from ..lib import (
    get_db,
    infer_kind,
)


def parse_symbol(symbol):
    """Parse SCIP symbol into (file_path, symbol_name).
    
    Example:
        scip-typescript npm rovetia-app 1.2 src/hooks/`useDictation.ts`/useDictation().
        -> ('src/hooks/useDictation.ts', 'useDictation()')
    """
    # Find the backtick-wrapped file path
    match = re.search(r'`([^`]+)`', symbol)
    if not match:
        return ('?', '?')
    
    filename = match.group(1)
    
    # Get the directory path before the backtick
    before = symbol[:match.start()]
    # Extract path after version (4th space-separated token)
    parts = before.split()
    if len(parts) >= 5:
        dir_path = ' '.join(parts[4:])
        file_path = dir_path + filename
    else:
        file_path = filename
    
    # Symbol name is everything after the closing backtick + /
    after_file = symbol[match.end():]
    if after_file.startswith('/'):
        after_file = after_file[1:]
    
    # Remove trailing .
    symbol_name = after_file.rstrip('.')
    
    return (file_path, symbol_name)


def is_noisy_symbol(symbol_str):
    """Filter out noisy symbols (file-level, parameters, etc)."""
    # File-level symbol (ends with /)
    if symbol_str.endswith('/'):
        return True
    
    # Parameters (contain 0: like "phrases0:")
    if re.search(r'\d+:', symbol_str):
        return True
    
    # Anonymous type literals (contain "typeLiteral")
    if 'typeLiteral' in symbol_str:
        return True
    
    # Function parameters (like "isNotSupportedError().(err)")
    if ').(' in symbol_str:
        return True
    
    return False


def kind_to_display(kind):
    """Convert kind to display format (capitalized like bash version)."""
    kind_map = {
        'function': 'Function',
        'method': 'Method',
        'class': 'Class',
        'interface': 'Interface',
        'type': 'TypeAlias',
        'variable': 'Variable',
    }
    return kind_map.get(kind, 'Unknown')


def main(args):
    """Search symbols by pattern."""
    db = get_db()
    
    # Search symbols with line numbers in one query
    rows = db.execute("""
        SELECT gs.id, gs.symbol, gs.display_name, der.start_line
        FROM global_symbols gs
        LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        WHERE gs.symbol LIKE ?
        LIMIT 100
    """, (f"%{args.pattern}%",)).fetchall()
    
    if not rows:
        print(f"No symbols found matching '{args.pattern}'", file=sys.stderr)
        sys.exit(1)
    
    # Filter by kind if requested
    if args.kind:
        rows = [r for r in rows if infer_kind(r[1]) == args.kind]
        if not rows:
            print(f"No {args.kind} symbols found matching '{args.pattern}'", file=sys.stderr)
            sys.exit(1)
    
    for symbol_id, symbol_str, display_name, start_line in rows:
        # Skip noisy symbols
        if is_noisy_symbol(symbol_str):
            continue
        
        kind = infer_kind(symbol_str)
        file_path, symbol_name = parse_symbol(symbol_str)
        
        line = start_line + 1 if start_line is not None else 0
        
        # Clean up symbol name: remove SCIP notation
        symbol_name = symbol_name.rstrip('.#')
        if symbol_name.endswith('()'):
            symbol_name = symbol_name[:-2]
        
        kind_display = kind_to_display(kind)
        print(f"{file_path}:{line} {kind_display} {symbol_name}")
