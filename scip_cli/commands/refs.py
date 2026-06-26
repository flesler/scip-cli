"""refs command - find all references to a symbol."""
import sys

from ..lib import (
    setup,
    resolve_symbol,
    read_source_lines,
    extract_leaf_name,
)


def get_exact_refs(db, symbol_id, project_root, max_refs):
    """Get references with exact line numbers by reading source files."""
    sym_row = db.execute("SELECT symbol FROM global_symbols WHERE id = ?", (symbol_id,)).fetchone()
    if not sym_row:
        return [], False

    leaf = extract_leaf_name(sym_row[0])

    chunks = db.execute("""
        SELECT c.id, c.document_id, c.start_line, c.end_line, d.relative_path
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents d ON c.document_id = d.id
        WHERE m.symbol_id = ? AND m.role != 1
        LIMIT ?
    """, (symbol_id, max_refs + 1)).fetchall()

    hit_limit = len(chunks) > max_refs
    if hit_limit:
        chunks = chunks[:max_refs]

    if not chunks:
        return [], False

    by_doc = {}
    for chunk_id, doc_id, start_line, end_line, rel_path in chunks:
        if doc_id not in by_doc:
            by_doc[doc_id] = {'path': rel_path, 'chunks': []}
        by_doc[doc_id]['chunks'].append((chunk_id, start_line, end_line))

    results = []

    for doc_id, info in by_doc.items():
        rel_path = info['path']
        chunks_list = info['chunks']
        if not chunks_list:
            continue

        min_line = min(c[1] for c in chunks_list)
        max_line = max(c[2] for c in chunks_list)

        lines = read_source_lines(project_root, rel_path, min_line, max_line)
        if lines is None:
            for chunk_id, start_line, end_line in chunks_list:
                if start_line is not None:
                    results.append((rel_path, start_line + 1))
            continue

        for chunk_id, start_line, end_line in chunks_list:
            if start_line is None:
                continue
            offset = min_line
            found = False
            for line_idx in range(start_line - offset, min(end_line - offset + 1, len(lines))):
                if leaf in lines[line_idx]:
                    results.append((rel_path, line_idx + offset + 1))
                    found = True
                    break
            if not found:
                results.append((rel_path, start_line + 1))

    return results, hit_limit


def main(args):
    """Find all references to a symbol."""
    db, project_root = setup()
    try:
        limit = args.limit

        # Get symbols with LIMIT + 1 to detect if we hit the limit
        symbols = resolve_symbol(db, args.symbol, limit=limit + 1)
        if not symbols:
            print(f"Symbol '{args.symbol}' not found", file=sys.stderr)
            sys.exit(1)

        symbols_hit_limit = len(symbols) > limit
        symbols = symbols[:limit]

        all_refs = []
        for symbol_id, symbol_str, display_name in symbols:
            refs, refs_hit_limit = get_exact_refs(db, symbol_id, project_root, limit)
            if refs:
                all_refs.append((symbol_str, refs, refs_hit_limit))

        if not all_refs:
            print(f"No references found for '{args.symbol}'", file=sys.stderr)
            sys.exit(1)

        if symbols_hit_limit:
            print(f"# Warning: more than {limit} symbols match, showing first {limit}", file=sys.stderr)

        for symbol_str, refs, refs_hit_limit in all_refs:
            if len(all_refs) > 1:
                print(f"# {symbol_str}")
            if refs_hit_limit:
                print(f"# Warning: more than {limit} refs for this symbol")
            seen = set()
            for path, line in refs:
                key = (path, line)
                if key not in seen:
                    seen.add(key)
                    print(f"{path}:{line}")
    finally:
        db.close()
