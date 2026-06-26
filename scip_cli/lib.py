#!/usr/bin/env python3
"""Common utilities for read-symbol Python scripts."""
import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def find_project_root(start_dir=None):
    """Walk up from start_dir (or cwd) to find project root."""
    markers = ["package.json", "tsconfig.json", "pyproject.toml", "Cargo.toml", "go.mod"]
    d = Path(start_dir or os.getcwd()).resolve()
    while d != d.parent:
        if any((d / m).exists() for m in markers):
            return d
        d = d.parent
    return None


def detect_language(project_root):
    """Detect language from project markers.
    
    Returns: 'typescript', 'python', 'rust', 'go', or 'typescript' (default)
    """
    root = Path(project_root)
    if (root / "tsconfig.json").exists() or (root / "package.json").exists():
        return "typescript"
    elif (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "python"
    elif (root / "Cargo.toml").exists():
        return "rust"
    elif (root / "go.mod").exists():
        return "go"
    else:
        return "typescript"  # default


def find_db(project_root=None):
    """Find the index.db for the given project (or cwd)."""
    root = project_root or find_project_root()
    if not root:
        return None
    h = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    cache = Path.home() / ".cache" / "scip-query" / "projects" / h / "index.db"
    if cache.exists():
        return cache
    return None


def get_db(project_root=None):
    """Get a sqlite3 connection to the index.db.
    
    If no index exists, auto-index the project with the detected language.
    """
    db_path = find_db(project_root)
    if not db_path:
        # Auto-index
        root = project_root or find_project_root()
        if not root:
            print("Error: Could not find project root", file=sys.stderr)
            sys.exit(1)
        
        lang = detect_language(root)
        print(f"Auto-indexing {root} ({lang})...", file=sys.stderr)
        
        # Create cache directory
        h = hashlib.sha256(str(root).encode()).hexdigest()[:12]
        cache_dir = Path.home() / ".cache" / "scip-query" / "projects" / h
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Run language-specific indexer
        with tempfile.TemporaryDirectory() as tmpdir:
            index_scip = os.path.join(tmpdir, "index.scip")
            
            if lang == "typescript":
                indexer_cmd = ["scip-typescript", "index", "--output", index_scip]
            elif lang == "python":
                indexer_cmd = ["scip-python", "index", ".", "--output", index_scip]
            else:
                print(f"Error: Unsupported language '{lang}'", file=sys.stderr)
                sys.exit(1)
            
            result = subprocess.run(
                indexer_cmd,
                cwd=str(root),
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Error: Failed to index project", file=sys.stderr)
                print(result.stderr, file=sys.stderr)
                sys.exit(1)
            
            # Convert index.scip to index.db
            index_db = cache_dir / "index.db"
            result = subprocess.run(
                ["scip", "expt-convert", index_scip, "--output", str(index_db)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"Error: Failed to convert index", file=sys.stderr)
                print(result.stderr, file=sys.stderr)
                sys.exit(1)
        
        # Try again
        db_path = find_db(project_root)
        if not db_path:
            print("Error: No index.db found after indexing", file=sys.stderr)
            sys.exit(1)
    
    return sqlite3.connect(str(db_path))


def infer_kind(symbol):
    """Infer symbol kind from symbol string pattern.
    
    Returns: 'function', 'method', 'class', 'interface', 'type', 'property', 'variable', or 'unknown'
    """
    # Method: has # in middle and ends with ().
    if "#" in symbol and symbol.endswith("()."):
        return "method"
    # Function: ends with (). but no # before it
    if symbol.endswith("().") and "#" not in symbol.split("/")[-1]:
        return "function"
    # Class: ends with # and name starts with uppercase
    if symbol.endswith("#"):
        name = symbol.split("/")[-1].rstrip("#")
        if name and name[0].isupper():
            # Could be class or interface - check if it's an interface
            # Interfaces often have "Interface" in display_name or are in .d.ts
            return "class"  # default to class
    # Type alias: ends with # and name starts with uppercase (but not class)
    if symbol.endswith("#"):
        return "type"
    # Property: type literal property (ParentClass#typeLiteral0:propertyName.)
    if "#typeLiteral" in symbol and ":" in symbol and symbol.endswith("."):
        return "property"
    # Variable/const: ends with . but not ()
    if symbol.endswith(".") and not symbol.endswith("()."):
        return "variable"
    return "unknown"


def resolve_symbol(db, name, kind_filter=None):
    """Resolve bare name to symbol_id(s).
    
    Args:
        db: sqlite3 connection
        name: bare symbol name (e.g., "useDictation")
        kind_filter: optional kind filter ('function', 'class', etc)
    
    Returns:
        List of (symbol_id, symbol, display_name) tuples
    """
    # Try exact leaf match first with single query using OR
    rows = db.execute("""
        SELECT id, symbol, display_name FROM global_symbols 
        WHERE symbol LIKE ? OR symbol LIKE ? OR symbol LIKE ?
    """, (
        f"%/{name}().",      # function/method
        f"%/{name}#",        # class/interface/type
        f"%/{name}.",        # variable/property
    )).fetchall()
    
    results = list(rows)
    
    # If no exact match, try contains
    if not results:
        rows = db.execute(
            "SELECT id, symbol, display_name FROM global_symbols WHERE symbol LIKE ?",
            (f"%{name}%",)
        ).fetchall()
        # Filter to leaf matches (name appears after last /)
        results = [r for r in rows if name in r[1].split("/")[-1]]
    
    # Apply kind filter if provided
    if kind_filter and results:
        filtered = [r for r in results if infer_kind(r[1]) == kind_filter]
        if filtered:
            results = filtered
    
    return results


def resolve_file(db, file_pattern):
    """Resolve file pattern to relative_path.
    
    Args:
        db: sqlite3 connection
        file_pattern: file path or pattern (e.g., "useDictation" or "src/hooks/useDictation.ts")
    
    Returns:
        List of matching relative_paths
    """
    # Try exact match first
    rows = db.execute(
        "SELECT relative_path FROM documents WHERE relative_path = ?",
        (file_pattern,)
    ).fetchall()
    if rows:
        return [r[0] for r in rows]
    
    # Try LIKE match
    if "/" not in file_pattern and "." not in file_pattern:
        # Bare name - search in filename
        pattern = f"%{file_pattern}%"
    else:
        pattern = file_pattern.replace("*", "%")
    
    rows = db.execute(
        "SELECT relative_path FROM documents WHERE relative_path LIKE ?",
        (pattern,)
    ).fetchall()
    return [r[0] for r in rows]


def get_file_symbols(db, relative_path):
    """Get all symbols defined in a file.
    
    Returns:
        List of (symbol_id, symbol, display_name, start_line, end_line) tuples
    """
    rows = db.execute("""
        SELECT gs.id, gs.symbol, gs.display_name, der.start_line, der.end_line
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents d ON der.document_id = d.id
        WHERE d.relative_path = ?
        ORDER BY der.start_line
    """, (relative_path,)).fetchall()
    return rows


def get_refs_for_symbols(db, symbol_ids):
    """Get all references for multiple symbol_ids in one query.
    
    Args:
        db: sqlite3 connection
        symbol_ids: list of symbol IDs
    
    Returns:
        Dict mapping symbol_id -> list of (relative_path, start_line) tuples
    """
    if not symbol_ids:
        return {}
    
    placeholders = ','.join('?' * len(symbol_ids))
    rows = db.execute(f"""
        SELECT m.symbol_id, d.relative_path, c.start_line
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN documents d ON c.document_id = d.id
        WHERE m.symbol_id IN ({placeholders}) AND m.role != 1
    """, symbol_ids).fetchall()
    
    result = {}
    for symbol_id, path, line in rows:
        if symbol_id not in result:
            result[symbol_id] = []
        result[symbol_id].append((path, line))
    
    return result


def get_members(db, symbol_id):
    """Get members (children) of a symbol.
    
    Returns:
        List of (symbol_id, symbol, display_name, start_line, end_line) tuples
    """
    # Get the symbol string for this symbol_id
    row = db.execute("SELECT symbol FROM global_symbols WHERE id = ?", (symbol_id,)).fetchone()
    if not row:
        return []
    parent_symbol = row[0]
    
    # Try enclosing_symbol first
    rows = db.execute("""
        SELECT gs.id, gs.symbol, gs.display_name, der.start_line, der.end_line
        FROM global_symbols gs
        LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        WHERE gs.enclosing_symbol = ?
        ORDER BY der.start_line
    """, (parent_symbol,)).fetchall()
    
    # Fall back to symbol prefix matching if no results
    if not rows:
        rows = db.execute("""
            SELECT gs.id, gs.symbol, gs.display_name, der.start_line, der.end_line
            FROM global_symbols gs
            LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
            WHERE gs.symbol LIKE ? AND gs.symbol != ?
            ORDER BY der.start_line
        """, (parent_symbol + '%', parent_symbol)).fetchall()
    
    # Filter out function parameters (contain "().(" pattern)
    rows = [r for r in rows if ").(" not in r[1]]
    
    return rows


def extract_leaf_name(symbol_str):
    """Extract the leaf name from a SCIP symbol string.
    
    Example:
        .../useDictationOrRecording(). -> useDictationOrRecording
        .../UseDictationOrRecordingOptions# -> UseDictationOrRecordingOptions
        .../UseDictationOrRecordingOptions#typeLiteral0:onFallbackToRecording. -> onFallbackToRecording
        .../GameEngine#config. -> config
        .../GameEngine#`<get>aliveHeroes`(). -> aliveHeroes
    """
    leaf = symbol_str.split("/")[-1].rstrip(".#")
    if leaf.endswith("()"):
        leaf = leaf[:-2]
    # Handle type literal properties (ParentClass#typeLiteral0:propertyName)
    if ":" in leaf:
        leaf = leaf.split(":")[-1]
    # Handle class members (ParentClass#memberName)
    if "#" in leaf:
        leaf = leaf.split("#")[-1]
    # Remove backticks
    leaf = leaf.replace("`", "")
    # Handle getters/setters: <get>name -> name
    if leaf.startswith("<get>"):
        leaf = leaf[5:]
    elif leaf.startswith("<set>"):
        leaf = leaf[5:]
    return leaf


def read_source_lines(project_root, relative_path, start_line=None, end_line=None):
    """Read source lines from filesystem.
    
    Args:
        project_root: Project root path
        relative_path: Relative path to file
        start_line: Optional start line (0-indexed)
        end_line: Optional end line (0-indexed, inclusive)
    
    Returns:
        List of lines, or None if file cannot be read
    """
    full_path = os.path.join(str(project_root), relative_path)
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if start_line is not None and end_line is not None:
                return lines[start_line:end_line + 1]
            return lines
    except Exception:
        return None


def warn_ambiguous(name, matches, context="symbol"):
    """Print warning if multiple matches found.
    
    Args:
        name: The search pattern
        matches: List of matches
        context: Description of what was searched (e.g., "symbol", "file")
    """
    if len(matches) > 1:
        print(f"Ambiguous {context} '{name}' ({len(matches)} matches). Using first match: {matches[0][1] if isinstance(matches[0], tuple) else matches[0]}", file=sys.stderr)
