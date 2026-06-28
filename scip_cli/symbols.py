"""SCIP symbol parsing and kind inference."""

from __future__ import annotations

import re
from enum import Enum


class SymbolKind(str, Enum):
    """Symbol kinds for filtering and display."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    PROPERTY = "property"
    UNKNOWN = "unknown"

    @classmethod
    def filterable_values(cls) -> list[str]:
        """Values suitable for --kind filtering (excludes UNKNOWN)."""
        return [k.value for k in cls if k != cls.UNKNOWN]


def kind_sql_clause(kind: SymbolKind | str) -> str:
    """Approximate SQL WHERE fragment to pre-filter symbols by kind."""
    if not isinstance(kind, SymbolKind):
        kind = SymbolKind(kind)
    if kind == SymbolKind.FUNCTION:
        return " AND gs.symbol LIKE '%().' AND gs.symbol NOT LIKE '%#%().'"
    if kind == SymbolKind.METHOD:
        return " AND gs.symbol LIKE '%#%' AND gs.symbol LIKE '%().'"
    if kind == SymbolKind.CLASS:
        return " AND gs.symbol LIKE '%#' AND gs.symbol NOT LIKE '%().'"
    if kind == SymbolKind.PROPERTY:
        return " AND gs.symbol LIKE '%#typeLiteral%'"
    return ""


def is_variable_symbol(symbol_str: str) -> bool:
    """Module/local const let var — high row count, low query value."""
    if symbol_str.endswith("/") or ").(" in symbol_str or "#typeLiteral" in symbol_str:
        return False
    return symbol_str.endswith(".") and not symbol_str.endswith("().")


def sql_exclude_variable_symbols(column: str = "symbol") -> str:
    """SQL expression: true when column is not a prunable const/let/var."""
    c = column
    return (
        f"NOT ({c} LIKE '%.' AND {c} NOT LIKE '%().' "
        f"AND {c} NOT LIKE '%#typeLiteral%' AND {c} NOT LIKE '%).(%' "
        f"AND {c} NOT LIKE '%/')"
    )


def is_module_symbol(symbol_str: str) -> bool:
    return symbol_str.endswith("/")


def is_type_or_interface_symbol(symbol_str: str) -> bool:
    """True for SCIP type/interface symbols (erased at runtime — ignore for import cycles)."""
    if symbol_str.endswith("/") or symbol_str.endswith("()."):
        return False
    if "#typeLiteral" in symbol_str:
        return True
    tail = symbol_str.split("/")[-1]
    return "#" in tail


def cycle_edge_type_sql(column: str = "gs.symbol") -> str:
    """SQL: true when symbol is a runtime dependency (not type/interface-only)."""
    c = column
    return f"({c} LIKE '%().' OR {c} LIKE '%/' OR ({c} NOT LIKE '%#%' AND {c} NOT LIKE '%#typeLiteral%'))"


def cycle_runtime_edge_sql(column: str = "gs.symbol") -> str:
    """SQL: cycle edges excluding types and module-only re-exports (barrel false positives)."""
    c = column
    return f"({c} LIKE '%().' OR ({c} NOT LIKE '%#%' AND {c} NOT LIKE '%#typeLiteral%' AND {c} NOT LIKE '%/'))"


def infer_kind(symbol: str) -> SymbolKind:
    """Infer symbol kind from symbol string pattern."""
    if "#" in symbol and symbol.endswith("()."):
        return SymbolKind.METHOD
    if symbol.endswith("()."):
        return SymbolKind.FUNCTION
    if symbol.endswith("#"):
        name = symbol.split("/")[-1].rstrip("#")
        if name and name[0].isupper():
            return SymbolKind.CLASS
    if "#typeLiteral" in symbol and ":" in symbol and symbol.endswith("."):
        return SymbolKind.PROPERTY
    return SymbolKind.UNKNOWN


def symbol_like_patterns(leaf: str) -> list[str]:
    """SQL LIKE patterns for finding a symbol by leaf name."""
    from .sql import escape_like

    escaped = escape_like(leaf)
    return [
        f"%/{escaped}().",
        f"%/{escaped}#",
        f"%/{escaped}.",
        f"%#{escaped}().",
        f"%#{escaped}.",
        f"%typeLiteral%:{escaped}.",
    ]


def parse_qualified_name(name: str) -> tuple[list[str], str]:
    """Split a dotted symbol query into qualifier segments and leaf name."""
    if "." not in name:
        return [], name
    parts = name.split(".")
    return parts[:-1], parts[-1]


def is_parameter_symbol(symbol_str: str) -> bool:
    """Return True for function/method parameter symbols."""
    return ").(" in symbol_str


def symbol_matches_qualifier(symbol_str: str, qualifier_parts: list[str], leaf: str) -> bool:
    """Return True when a SCIP symbol matches Class.member style qualifiers."""
    if not qualifier_parts:
        return True

    tail = symbol_str.split("/")[-1]
    joined = "#".join(qualifier_parts)
    if f"{joined}#{leaf}" in tail:
        return True

    container = qualifier_parts[-1]
    if re.search(rf"{re.escape(container)}#typeLiteral\d+:{re.escape(leaf)}\.", tail):
        if len(qualifier_parts) == 1:
            return True
        return all(part in symbol_str for part in qualifier_parts[:-1])

    if f"{container}#{leaf}" in tail:
        if len(qualifier_parts) == 1:
            return True
        prefix = qualifier_parts[:-1]
        return all(part in symbol_str for part in prefix)

    dotted = ".".join(qualifier_parts)
    if f"{dotted}.{leaf}" in symbol_str or f"{dotted}/{leaf}" in symbol_str:
        return True

    if ".py/" in symbol_str and f"{container}#{leaf}" in symbol_str:
        if len(qualifier_parts) == 1:
            return True
        return all(part in symbol_str for part in qualifier_parts[:-1])

    return False


def extract_leaf_name(symbol_str: str) -> str:
    """Extract the leaf name from a SCIP symbol string."""
    leaf = symbol_str.split("/")[-1].rstrip(".#")
    if leaf.endswith("()"):
        leaf = leaf[:-2]
    if ":" in leaf:
        leaf = leaf.split(":")[-1]
    if "#" in leaf:
        leaf = leaf.split("#")[-1]
    leaf = leaf.replace("`", "")
    if leaf.startswith("<get>") or leaf.startswith("<set>"):
        leaf = leaf[5:]
    return leaf


def extract_file_path_from_symbol(symbol_str: str) -> str | None:
    """Extract the source file path encoded in a SCIP symbol string."""
    match = re.search(r"`([^`]+)`", symbol_str)
    if match:
        filename = match.group(1)
        before = symbol_str[: match.start()]
        parts = before.split()
        if len(parts) >= 5:
            return " ".join(parts[4:]) + filename
        return filename

    py_match = re.search(r"(\S+\.py)/", symbol_str)
    if py_match:
        return py_match.group(1)
    return None
