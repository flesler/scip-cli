"""def command - find symbol definitions."""
import sys

from ..lib import (
    get_db,
    resolve_symbol,
    find_project_root,
    read_source_lines,
    infer_kind,
)


def main(args):
    """Find the definition of a symbol."""
    db = get_db()
    
    symbols = resolve_symbol(db, args.symbol, args.kind)
    if not symbols:
        print(f"Symbol '{args.symbol}' not found", file=sys.stderr)
        sys.exit(1)
    
    project_root = find_project_root()
    if not project_root:
        print("Error: Could not find project root", file=sys.stderr)
        sys.exit(1)
    
    for symbol_id, symbol_str, display_name in symbols:
        # Get definition location from defn_enclosing_ranges
        row = db.execute("""
            SELECT d.relative_path, der.start_line, der.end_line
            FROM defn_enclosing_ranges der
            JOIN documents d ON der.document_id = d.id
            WHERE der.symbol_id = ?
        """, (symbol_id,)).fetchone()
        
        if not row:
            continue
        
        rel_path, start_line, end_line = row
        kind = infer_kind(symbol_str)
        
        # Read source from filesystem
        lines = read_source_lines(project_root, rel_path, start_line, end_line)
        if lines is None:
            source_snippet = "(could not read source)"
        else:
            source_snippet = ''.join(lines).rstrip('\n')
        
        print(f"{rel_path}:{start_line + 1}:{end_line + 1}")
        print(source_snippet)
