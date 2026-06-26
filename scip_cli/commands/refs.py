"""refs command - find all references to a symbol."""
import sys

from ..lib import (
    setup,
    resolve_one_symbol,
    read_source_lines,
    extract_leaf_name,
)


def get_exact_refs(db, symbol_id, project_root):
    """Get references with exact line numbers by reading source files."""
    sym_row = db.execute("SELECT symbol FROM global_symbols WHERE id = ?", (symbol_id,)).fetchone()
    if not sym_row:
        return []

    leaf = extract_leaf_name(sym_row[0])

    chunks = db.execute("""
        SELECT c.id, c.document_id, c.start_line, c.end_line, d.relative_path
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents d ON c.document_id = d.id
        WHERE m.symbol_id = ? AND m.role != 1
    """, (symbol_id,)).fetchall()

    if not chunks:
        return []

    by_doc = {}
    for chunk_id, doc_id, start_line, end_line, rel_path in chunks:
        if doc_id not in by_doc:
            by_doc[doc_id] = {'path': rel_path, 'chunks': []}
        by_doc[doc_id]['chunks'].append((chunk_id, start_line, end_line))

    results = []

    for doc_id, info in by_doc.items():
        rel_path = info['path']
        min_line = min(c[1] for c in info['chunks'])
        max_line = max(c[2] for c in info['chunks'])

        lines = read_source_lines(project_root, rel_path, min_line, max_line)
        if lines is None:
            for chunk_id, start_line, end_line in info['chunks']:
                results.append((rel_path, start_line + 1))
            continue

        for chunk_id, start_line, end_line in info['chunks']:
            offset = min_line
            found = False
            for line_idx in range(start_line - offset, min(end_line - offset + 1, len(lines))):
                if leaf in lines[line_idx]:
                    results.append((rel_path, line_idx + offset + 1))
                    found = True
                    break
            if not found:
                results.append((rel_path, start_line + 1))

    return results


def main(args):
    """Find all references to a symbol."""
    db, project_root = setup()
    try:
        symbol_id, _, _ = resolve_one_symbol(db, args.symbol)

        refs = get_exact_refs(db, symbol_id, project_root)

        if not refs:
            print(f"No references found for '{args.symbol}'", file=sys.stderr)
            sys.exit(1)

        seen = set()
        for path, line in refs:
            key = (path, line)
            if key not in seen:
                seen.add(key)
                print(f"{path}:{line}")
    finally:
        db.close()
