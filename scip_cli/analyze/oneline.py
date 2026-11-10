"""Heuristics for tiny exported functions (thin delegates, one-line wrappers)."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from pathlib import Path

from ..paths import path_filter_sql
from ..source import read_source_lines
from ..symbols import is_module_symbol, is_type_or_interface_symbol
from .common import (
    DEFAULT_LIMIT,
    SYM_DEF_JOIN,
    analyze_noise,
    collect_until_limit,
    fetch_all,
    short_name,
)
from .entrypoints import is_entrypoint_path
from .live import file_has_scip_importers, live_for

# Inclusive definition line count (signature + body) from SCIP ranges.
MAX_DEF_LOC = 4

_analyze_root: ContextVar[Path | None] = ContextVar("scip_cli_analyze_root", default=None)


def bind_analyze_root(project_root: Path | str | None) -> Token[Path | None]:
    root = Path(project_root) if project_root is not None else None
    return _analyze_root.set(root)


def reset_analyze_root(token: Token[Path | None]) -> None:
    _analyze_root.reset(token)


def analyze_root() -> Path | None:
    return _analyze_root.get()


def _external_body_refs(
    db,
    *,
    def_doc_id: int,
    symbol_id: int,
    start_line: int,
    end_line: int,
) -> list[tuple[str, str]]:
    """Symbols used inside a definition range that are defined in another file."""
    return fetch_all(
        db,
        """
        SELECT DISTINCT gs.symbol, def_d.relative_path
        FROM mentions m
        JOIN chunks c ON m.chunk_id = c.id
        JOIN global_symbols gs ON m.symbol_id = gs.id
        JOIN defn_enclosing_ranges def_der ON def_der.symbol_id = gs.id
        JOIN documents def_d ON def_der.document_id = def_d.id
        WHERE c.document_id = ?
          AND c.start_line <= ?
          AND c.end_line >= ?
          AND m.role NOT IN (1, 2)
          AND gs.id != ?
          AND def_d.id != ?
        ORDER BY def_d.relative_path, gs.symbol
        """,
        (def_doc_id, end_line, start_line, symbol_id, def_doc_id),
    )


def _body_delegate_hint(
    project_root: Path,
    relative_path: str,
    start_line: int,
    end_line: int,
) -> str | None:
    """Best-effort: single return/call statement inside the definition."""
    lines = read_source_lines(project_root, relative_path, start_line, end_line)
    if not lines:
        return None
    text = "".join(lines)
    brace = text.find("{")
    if brace == -1:
        stripped = text.strip()
        if re.match(r"^async\s+", stripped):
            stripped = re.sub(r"^async\s+", "", stripped, count=1)
        if "=>" in stripped:
            tail = stripped.split("=>", 1)[1].strip().rstrip(";")
            if tail and not tail.startswith("{"):
                return short_name_from_expr(tail)
        return None
    inner = text[brace + 1 :]
    close = inner.rfind("}")
    if close != -1:
        inner = inner[:close]
    inner = re.sub(r"/\*.*?\*/", "", inner, flags=re.S)
    inner = re.sub(r"//.*?$", "", inner, flags=re.M)
    statements = [part.strip() for part in inner.split(";") if part.strip()]
    if len(statements) != 1:
        return None
    stmt = statements[0]
    match = re.match(r"^(?:async\s+)?return\s+(.+)$", stmt, flags=re.S)
    if match:
        return short_name_from_expr(match.group(1).strip())
    if re.match(r"^[\w$.]+", stmt):
        return short_name_from_expr(stmt)
    return None


_SIMPLE_CALL = re.compile(r"^[\w$.]+\([^)]*\)$")


def _looks_like_thin_delegate(
    hint: str | None,
    *,
    runtime_refs: list[tuple[str, str]],
    module_refs: list[tuple[str, str]],
) -> bool:
    """Narrow SCIP+source hits to obvious one-line shims, not every tiny helper."""
    if hint:
        h = hint.strip()
        if any(marker in h for marker in ("`", "=>", ".find(", ".some(", ".map(", "??", "||", "?.", "${")):
            return False
        if not _SIMPLE_CALL.match(h):
            return False
    if len(runtime_refs) == 1 and runtime_refs[0][0].endswith("()."):
        return True
    return len(module_refs) == 1 and hint is not None and _SIMPLE_CALL.match(hint.strip()) is not None


def short_name_from_expr(expr: str) -> str:
    """Compact label for a one-line expression (for display only)."""
    expr = expr.strip()
    if len(expr) > 48:
        return expr[:45] + "…"
    return expr


def _is_top_level_function(symbol: str) -> bool:
    if not symbol.endswith("()."):
        return False
    tail = symbol.split("/")[-1]
    return "#" not in tail


def _is_exported(
    db,
    *,
    symbol: str,
    path: str,
    def_doc_id: int,
    ext_consumer_files: int,
    live,
) -> bool:
    if ext_consumer_files >= 1:
        return True
    if live.possibly_live_label(symbol, def_doc_id):
        return True
    return file_has_scip_importers(db, path, live=live, def_doc_id=def_doc_id)


def one_line_exports(
    db,
    limit: int = DEFAULT_LIMIT,
    *,
    include_tests: bool = False,
    scope: str | None = None,
) -> list[str]:
    """Exported functions with a tiny body, usually a single outbound call (wrappers/shims)."""
    scope_clause, scope_params = path_filter_sql(db, scope, doc_alias="def_d")
    sql = f"""
        SELECT gs.id, gs.symbol, def_d.relative_path, def_d.id,
               sym_def.start_line, sym_def.end_line,
               sym_def.end_line - sym_def.start_line + 1 AS loc,
               COUNT(DISTINCT CASE WHEN ref_d.id != def_d.id THEN ref_d.id END) AS ext_files
        FROM global_symbols gs
        {SYM_DEF_JOIN}
        LEFT JOIN mentions m ON m.symbol_id = gs.id AND m.role != 1
        LEFT JOIN chunks c ON m.chunk_id = c.id
        LEFT JOIN documents ref_d ON c.document_id = ref_d.id
        WHERE gs.symbol LIKE '%().'
          AND gs.symbol NOT LIKE '%#%().'{scope_clause}
        GROUP BY gs.id
        HAVING loc <= ?
        ORDER BY loc ASC, ext_files DESC, def_d.relative_path
    """
    live = live_for(db)
    root = analyze_root()

    def fetch_page(page_size: int, offset: int):
        return fetch_all(
            db,
            sql + " LIMIT ? OFFSET ?",
            (*scope_params, MAX_DEF_LOC, page_size, offset),
        )

    def accept(row):
        sym_id, symbol, path, def_doc_id, start, end, loc, ext_files = row
        if is_entrypoint_path(path):
            return None
        if analyze_noise(path, symbol, include_tests=include_tests):
            return None
        if is_module_symbol(symbol) or not _is_top_level_function(symbol):
            return None
        if not _is_exported(
            db,
            symbol=symbol,
            path=path,
            def_doc_id=def_doc_id,
            ext_consumer_files=ext_files,
            live=live,
        ):
            return None

        body_refs = _external_body_refs(
            db,
            def_doc_id=def_doc_id,
            symbol_id=sym_id,
            start_line=start,
            end_line=end,
        )
        usable_refs = [(sym, ref_path) for sym, ref_path in body_refs if not is_type_or_interface_symbol(sym)]
        other_files = {ref_path for _sym, ref_path in usable_refs}
        if len(other_files) != 1 or not usable_refs:
            return None

        runtime_refs = [(sym, ref_path) for sym, ref_path in usable_refs if not is_module_symbol(sym)]
        module_refs = [(sym, ref_path) for sym, ref_path in usable_refs if is_module_symbol(sym)]

        hint = _body_delegate_hint(root, path, start, end) if root is not None else None

        if not _looks_like_thin_delegate(hint, runtime_refs=runtime_refs, module_refs=module_refs):
            return None

        if hint and re.match(r"^[a-z][\w$]*\.trim\(\)$", hint.strip()):
            return None

        if runtime_refs:
            callee = short_name(runtime_refs[0][0])
            tag = f"delegate→{callee}"
        else:
            tag = f"delegate→{hint}"

        if hint and runtime_refs and hint not in tag:
            tag = f"{tag}  body={hint}"

        return f"{short_name(symbol)}  loc={loc}  {tag}  ({path})"

    return collect_until_limit(limit, fetch_page, accept)
