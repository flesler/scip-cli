"""refs command - find all references to a symbol."""
import sys

from ..lib import (
    get_db,
    resolve_symbol,
    warn_ambiguous,
    find_project_root,
    read_source_lines,
    extract_leaf_name,
)


def get_exact_refs(db, symbol_id, project_root):
    """Get references with exact line numbers by reading source files."""
    # Get symbol name once
    sym_row = db.execute("SELECT symbol FROM global_symbols WHERE id = ?", (symbol_id,)).fetchone()
    if not sym_row:
        return []
    
    leaf = extract_leaf_name(sym_row[0])
    
    # Get all chunks that reference this symbol
    chunks = db.execute("""
        SELECT c.id, c.document_id, c.start_line, c.end_line, d.relative_path
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents d ON c.document_id = d.id
        WHERE m.symbol_id = ? AND m.role != 1
    """, (symbol_id,)).fetchall()
    
    if not chunks:
        return []
    
    # Group by document
    by_doc = {}
    for chunk_id, doc_id, start_line, end_line, rel_path in chunks:
        if doc_id not in by_doc:
            by_doc[doc_id] = {'path': rel_path, 'chunks': []}
        by_doc[doc_id]['chunks'].append((chunk_id, start_line, end_line))
    
    results = []
    
    # For each document, read source and find exact lines
    for doc_id, info in by_doc.items():
        rel_path = info['path']
        
        # Get min/max line range for this document
        min_line = min(c[1] for c in info['chunks'])
        max_line = max(c[2] for c in info['chunks'])
        
        # Read only the needed range
        lines = read_source_lines(project_root, rel_path, min_line, max_line)
        if lines is None:
            # If can't read file, fall back to chunk start lines
            for chunk_id, start_line, end_line in info['chunks']:
                results.append((rel_path, start_line + 1))
            continue
        
        # Search for the symbol in each chunk's line range
        for chunk_id, start_line, end_line in info['chunks']:
            # Search within the chunk range (adjusted for offset)
            offset = min_line
            for line_idx in range(start_line - offset, min(end_line - offset + 1, len(lines))):
                line = lines[line_idx]
                # Simple check: does the line contain the symbol name?
                if leaf in line:
                    results.append((rel_path, line_idx + offset + 1))
                    break  # One match per chunk is enough
            else:
                # Fallback to chunk start line
                results.append((rel_path, start_line + 1))
    
    return results


def main(args):
    """Find all references to a symbol."""
    db = get_db()
    
    symbols = resolve_symbol(db, args.symbol)
    if not symbols:
        print(f"Symbol '{args.symbol}' not found", file=sys.stderr)
        sys.exit(1)
    
    warn_ambiguous(args.symbol, symbols, "symbol")
    
    symbol_id, symbol_str, display_name = symbols[0]
    
    project_root = find_project_root()
    if not project_root:
        print("Error: Could not find project root", file=sys.stderr)
        sys.exit(1)
    
    refs = get_exact_refs(db, symbol_id, project_root)
    
    if not refs:
        print(f"No references found for '{args.symbol}'", file=sys.stderr)
        sys.exit(1)
    
    # Deduplicate and sort
    seen = set()
    for path, line in refs:
        key = (path, line)
        if key not in seen:
            seen.add(key)
            print(f"{path}:{line}")
