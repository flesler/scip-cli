"""members command - list members of a class/interface."""
import sys
import re

from ..lib import (
    get_db,
    resolve_symbol,
    warn_ambiguous,
    get_members,
    infer_kind,
    extract_leaf_name,
    read_source_lines,
    find_project_root,
)


def main(args):
    """List members of a class or interface."""
    db = get_db()
    
    symbols = resolve_symbol(db, args.symbol)
    if not symbols:
        print(f"Symbol '{args.symbol}' not found", file=sys.stderr)
        sys.exit(1)
    
    if len(symbols) > 1:
        warn_ambiguous(args.symbol, symbols, "symbol")
    
    symbol_id, symbol_str, display_name = symbols[0]
    members = get_members(db, symbol_id)
    
    if not members:
        print(f"No members found for '{args.symbol}'", file=sys.stderr)
        sys.exit(1)
    
    # Get parent's file path and line range for fallback
    project_root = find_project_root()
    parent_def = db.execute("""
        SELECT d.relative_path, der.start_line, der.end_line
        FROM defn_enclosing_ranges der
        JOIN documents d ON der.document_id = d.id
        WHERE der.symbol_id = ?
    """, (symbol_id,)).fetchone()
    
    parent_file = parent_def[0] if parent_def else None
    parent_start = parent_def[1] if parent_def else None
    parent_end = parent_def[2] if parent_def else None
    
    # Check if any members need line number lookup
    needs_lookup = any(m[3] is None for m in members)
    
    # Read source file once if needed
    source_lines = None
    if needs_lookup and project_root and parent_file and parent_start is not None:
        source_lines = read_source_lines(project_root, parent_file, parent_start, parent_end)
    
    for member_id, member_symbol, member_name, start_line, end_line in members:
        kind = infer_kind(member_symbol)
        short = extract_leaf_name(member_symbol)
        
        # Skip function parameters (they have ().( in the symbol)
        if ").(" in member_symbol:
            continue
        
        # If no line numbers from DB, try to find in source
        if start_line is None and source_lines:
            if "<constructor>" in member_symbol:
                pattern = rf'^\s*constructor\s*\('
            elif "<get>" in member_symbol:
                pattern = rf'^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+)*get\s+{re.escape(short)}\s*\('
            elif "<set>" in member_symbol:
                pattern = rf'^\s*(?:public\s+|private\s+|protected\s+|static\s+)*set\s+{re.escape(short)}\s*\('
            else:
                # Regular property/method - handle TypeScript modifiers
                pattern = rf'^\s*(?:public\s+|private\s+|protected\s+|static\s+|readonly\s+)*{re.escape(short)}\s*\??\s*[:=(]'
            
            for i, line in enumerate(source_lines):
                if re.match(pattern, line):
                    start_line = parent_start + i
                    end_line = start_line
                    break
        
        line_info = f"{start_line + 1}:{end_line + 1}" if start_line is not None else "??"
        print(f"{line_info} {kind} {short}")
