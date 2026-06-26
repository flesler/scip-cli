#!/usr/bin/env python3
"""Core library for scip-cli: indexing, symbol resolution, and source reading."""
import hashlib
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


def _debug_execute(db, sql, params=()):
    """Execute SQL with optional debug logging."""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("SQL: %s | params: %s", sql.strip()[:200], params)
    return db.execute(sql, params)


INDEX_TIMEOUT = 300


class SymbolKind(str, Enum):
    """Symbol kinds for filtering and display."""
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    PROPERTY = "property"
    VARIABLE = "variable"
    UNKNOWN = "unknown"
    
    @classmethod
    def values(cls):
        return [k.value for k in cls]
    
    @classmethod
    def filterable_values(cls):
        """Values suitable for --kind filtering (excludes UNKNOWN)."""
        return [k.value for k in cls if k != cls.UNKNOWN]


def escape_like(s):
    """Escape SQL LIKE special characters in a string."""
    return s.replace("%", "\\%").replace("_", "\\_")


def find_project_root(start_dir=None):
    """Walk up from start_dir (or cwd) to find project root."""
    markers = ["package.json", "tsconfig.json", "pyproject.toml", "setup.py"]
    d = Path(start_dir or os.getcwd()).resolve()
    while d != d.parent:
        if any((d / m).exists() for m in markers):
            return d
        d = d.parent
    return None


def detect_language(project_root):
    """Detect language from project markers.
    
    Returns: 'typescript' (TypeScript/JavaScript via scip-typescript), 'python', or None.
    """
    root = Path(project_root)
    # scip-typescript indexes both TS and JS; package.json is the primary marker
    if (root / "package.json").exists():
        return "typescript"
    if (root / "tsconfig.json").exists():
        return "typescript"
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        return "python"
    return None


def _run_subprocess(cmd, cwd):
    """Run subprocess with timeout; raise RuntimeError on timeout."""
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=INDEX_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"Error: Command timed out after {INDEX_TIMEOUT} seconds", file=sys.stderr)
        raise RuntimeError("Indexing command timed out")


def run_with_fallback(binary, npx_package, cwd, args):
    """Try binary first, fallback to npx if not found."""
    try:
        result = _run_subprocess([binary] + args, cwd)
        if result.returncode == 0:
            return result
        if "not found" in result.stderr.lower():
            print("Tool not found, trying npx (will download automatically)...", file=sys.stderr)
            return _run_subprocess(["npx", "-y", npx_package] + args, cwd)
        return result
    except FileNotFoundError:
        print("Tool not found, trying npx (will download automatically)...", file=sys.stderr)
        return _run_subprocess(["npx", "-y", npx_package] + args, cwd)


def get_cache_dir(project_root):
    """Get the cache directory for a project."""
    h = hashlib.sha256(str(project_root).encode()).hexdigest()[:12]
    return Path.home() / ".cache" / "scip-cli" / "projects" / h


def find_db(project_root=None):
    """Find the index.db for the given project (or cwd)."""
    root = project_root or find_project_root()
    if not root:
        return None
    cache = get_cache_dir(root) / "index.db"
    if cache.exists():
        return cache
    return None


def _index_project(root, lang, cache_dir):
    """Run the language-specific indexer and convert to DB."""
    cache_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        index_scip = os.path.join(tmpdir, "index.scip")

        if lang == "typescript":
            index_args = ["index", "--output", index_scip]
            if not (Path(root) / "tsconfig.json").exists():
                index_args.insert(1, "--infer-tsconfig")
            result = run_with_fallback("scip-typescript", "@sourcegraph/scip-typescript", str(root), index_args)
        elif lang == "python":
            result = run_with_fallback("scip-python", "@sourcegraph/scip-python", str(root), ["index", ".", "--output", index_scip])
        else:
            raise RuntimeError(f"Unsupported language '{lang}'")

        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            raise RuntimeError("Failed to index project")

        index_db = cache_dir / "index.db"
        result = run_with_fallback("scip", "@sourcegraph/scip", tmpdir, ["expt-convert", index_scip, "--output", str(index_db)])

        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            raise RuntimeError("Failed to convert index")


def get_db(project_root=None):
    """Get a sqlite3 connection to the index.db.
    
    If no index exists, auto-index the project with the detected language.
    Raises RuntimeError on failure.
    """
    db_path = find_db(project_root)
    if not db_path:
        root = project_root or find_project_root()
        if not root:
            raise RuntimeError("Could not find project root")

        lang = detect_language(root)
        if lang is None:
            raise RuntimeError(f"No supported project markers found in {root}")

        print(f"Auto-indexing {root} ({lang})...", file=sys.stderr)
        cache_dir = get_cache_dir(root)
        _index_project(root, lang, cache_dir)

        db_path = find_db(project_root)
        if not db_path:
            raise RuntimeError("No index.db found after indexing")

    return sqlite3.connect(str(db_path))


def infer_kind(symbol):
    """Infer symbol kind from symbol string pattern.
    
    Returns: SymbolKind enum value or 'unknown'.
    Note: cannot distinguish class/interface/type from symbol string alone; all return 'class'.
    
    Works with both TypeScript and Python SCIP formats.
    """
    # Method: has # (class member) and ends with (). (function call)
    if "#" in symbol and symbol.endswith("()."):
        return SymbolKind.METHOD
    # Function: ends with (). (not a class member)
    if symbol.endswith("()."):
        return SymbolKind.FUNCTION
    # Class: ends with # (TypeScript) or is a class definition (Python)
    if symbol.endswith("#"):
        name = symbol.split("/")[-1].rstrip("#")
        if name and name[0].isupper():
            return SymbolKind.CLASS
    # Property: has typeLiteral (TypeScript) or is a simple attribute
    if "#typeLiteral" in symbol and ":" in symbol and symbol.endswith("."):
        return SymbolKind.PROPERTY
    # Variable: ends with . but not (). (not a function)
    if symbol.endswith(".") and not symbol.endswith("()."):
        return SymbolKind.VARIABLE
    return SymbolKind.UNKNOWN


def resolve_symbol(db, name, kind_filter=None, limit=None):
    """Resolve bare name to symbol_id(s).
    
    Two-phase resolution: exact leaf match first, then substring fallback.
    
    Args:
        db: sqlite3 connection
        name: bare symbol name (e.g., "useDictation")
        kind_filter: optional kind filter ('function', 'class', etc)
        limit: optional limit for results (no limit if None)
    
    Returns:
        List of (symbol_id, symbol, display_name) tuples
    """
    escaped = escape_like(name)
    
    # Build LIMIT clause
    limit_clause = f"LIMIT {limit}" if limit else ""
    
    sql = f"""
        SELECT id, symbol, display_name FROM global_symbols 
        WHERE symbol LIKE ? ESCAPE '\\' OR symbol LIKE ? ESCAPE '\\' OR symbol LIKE ? ESCAPE '\\'
        {limit_clause}
    """
    params = (
        f"%/{escaped}().",
        f"%/{escaped}#",
        f"%/{escaped}.",
    )
    rows = _debug_execute(db, sql, params).fetchall()

    results = list(rows)

    if not results:
        sql = f"SELECT id, symbol, display_name FROM global_symbols WHERE symbol LIKE ? ESCAPE '\\' {limit_clause}"
        params = (f"%{escaped}%",)
        rows = _debug_execute(db, sql, params).fetchall()
        results = [r for r in rows if name in r[1].split("/")[-1]]

    if kind_filter and results:
        results = [r for r in results if infer_kind(r[1]) == kind_filter]

    return results


def resolve_file(db, file_pattern):
    """Resolve file pattern to relative_path.
    
    Args:
        db: sqlite3 connection
        file_pattern: file path or pattern (e.g., "useDictation" or "src/hooks/useDictation.ts")
    
    Returns:
        List of matching relative_paths
    """
    rows = _debug_execute(db, 
        "SELECT relative_path FROM documents WHERE relative_path = ?",
        (file_pattern,)
    ).fetchall()
    if rows:
        return [r[0] for r in rows]

    # Escape LIKE metacharacters first, then convert user's * to SQL %
    escaped = escape_like(file_pattern)
    if "/" not in file_pattern and "." not in file_pattern:
        pattern = f"%{escaped}%"
    else:
        pattern = escaped.replace("*", "%")

    rows = _debug_execute(db, 
        "SELECT relative_path FROM documents WHERE relative_path LIKE ? ESCAPE '\\'",
        (pattern,)
    ).fetchall()
    return [r[0] for r in rows]


def get_file_symbols(db, relative_path, limit=None):
    """Get all symbols defined in a file.
    
    Args:
        db: sqlite3 connection
        relative_path: file path
        limit: optional limit (no limit if None)
    
    Returns:
        List of (symbol_id, symbol, display_name, start_line, end_line) tuples
    """
    limit_clause = f"LIMIT {limit}" if limit else ""
    sql = f"""
        SELECT gs.id, gs.symbol, gs.display_name, der.start_line, der.end_line
        FROM global_symbols gs
        JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        JOIN documents d ON der.document_id = d.id
        WHERE d.relative_path = ?
        ORDER BY der.start_line
        {limit_clause}
    """
    return _debug_execute(db, sql, (relative_path,)).fetchall()


def get_refs_for_symbols(db, symbol_ids):
    """Get all references for multiple symbol_ids in one query.
    
    Returns:
        Dict mapping symbol_id -> list of (relative_path, start_line) tuples
    """
    if not symbol_ids:
        return {}

    placeholders = ','.join('?' * len(symbol_ids))
    rows = _debug_execute(db, f"""
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
        List of (symbol_id, symbol, display_name, start_line, end_line) tuples.
        Function parameters are already filtered out.
    """
    row = _debug_execute(db, "SELECT symbol FROM global_symbols WHERE id = ?", (symbol_id,)).fetchone()
    if not row:
        return []
    parent_symbol = row[0]

    rows = _debug_execute(db, """
        SELECT gs.id, gs.symbol, gs.display_name, der.start_line, der.end_line
        FROM global_symbols gs
        LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
        WHERE gs.enclosing_symbol = ?
        ORDER BY der.start_line
    """, (parent_symbol,)).fetchall()

    if not rows:
        # Escape LIKE metacharacters in parent_symbol before using as prefix
        escaped_parent = escape_like(parent_symbol)
        rows = _debug_execute(db, """
            SELECT gs.id, gs.symbol, gs.display_name, der.start_line, der.end_line
            FROM global_symbols gs
            LEFT JOIN defn_enclosing_ranges der ON gs.id = der.symbol_id
            WHERE gs.symbol LIKE ? ESCAPE '\\' AND gs.symbol != ?
            ORDER BY der.start_line
        """, (escaped_parent + '%', parent_symbol)).fetchall()

    return [r for r in rows if ").(" not in r[1]]


def get_def_location(db, symbol_id):
    """Get definition location for a symbol.
    
    Returns:
        Tuple of (relative_path, start_line, end_line) or None
    """
    return _debug_execute(db, """
        SELECT d.relative_path, der.start_line, der.end_line
        FROM defn_enclosing_ranges der
        JOIN documents d ON der.document_id = d.id
        WHERE der.symbol_id = ?
    """, (symbol_id,)).fetchone()


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
    if ":" in leaf:
        leaf = leaf.split(":")[-1]
    if "#" in leaf:
        leaf = leaf.split("#")[-1]
    leaf = leaf.replace("`", "")
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
        List of lines, or None if file cannot be read or path escapes project root
    """
    try:
        full_path = Path(project_root).resolve() / relative_path
        if not full_path.resolve().is_relative_to(Path(project_root).resolve()):
            return None
        with open(full_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if start_line is not None and end_line is not None:
                return lines[start_line:end_line + 1]
            return lines
    except (FileNotFoundError, PermissionError, UnicodeDecodeError):
        return None


def warn_ambiguous(name, matches, context="symbol"):
    """Print warning if multiple matches found."""
    if len(matches) <= 1:
        return
    first = matches[0]
    label = first[1] if isinstance(first, tuple) and len(first) > 1 else first
    print(f"Ambiguous {context} '{name}' ({len(matches)} matches). Using first match: {label}", file=sys.stderr)


def format_line_range(start_line, end_line, sep=":"):
    """Format a line range as a string, handling None values.

    Args:
        start_line: 0-indexed start line, or None
        end_line: 0-indexed end line (inclusive), or None
        sep: separator between values (default ":" for "start:end")

    Returns:
        Formatted string like "10:20" or "??" if unavailable
    """
    if start_line is not None and end_line is not None:
        return f"{start_line + 1}{sep}{end_line + 1}"
    if start_line is not None:
        return f"{start_line + 1}{sep}?"
    return "??"


def setup():
    """Setup command execution: find project root and get DB connection.
    
    Returns:
        Tuple of (db, project_root)
    
    Exits with error if project root not found or indexing fails.
    """
    project_root = find_project_root()
    if not project_root:
        print("Error: Could not find project root", file=sys.stderr)
        sys.exit(1)
    try:
        db = get_db(project_root)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    return db, project_root


def resolve_one_symbol(db, name, kind_filter=None):
    """Resolve a symbol name to a single symbol, warning if ambiguous.
    
    Returns:
        Tuple of (symbol_id, symbol_str, display_name)
    
    Exits with error if symbol not found.
    """
    symbols = resolve_symbol(db, name, kind_filter)
    if not symbols:
        print(f"Symbol '{name}' not found", file=sys.stderr)
        sys.exit(1)

    warn_ambiguous(name, symbols, "symbol")
    return symbols[0]


def resolve_one_file(db, pattern):
    """Resolve a file pattern to a single path, warning if ambiguous.
    
    Returns:
        The relative_path string.
    
    Exits with error if file not found.
    """
    files = resolve_file(db, pattern)
    if not files:
        print(f"File '{pattern}' not found", file=sys.stderr)
        sys.exit(1)

    warn_ambiguous(pattern, files, "file")
    return files[0]
