"""Human-readable catalog of analyze --check names (single source for CHECK_KEYS)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PriorityTier = Literal["high", "medium", "low"]
Scope = Literal["project", "file", "symbol"]


@dataclass(frozen=True, slots=True)
class CheckDoc:
    key: str
    priority: PriorityTier
    scope: Scope
    summary: str


# Keep summaries short — printed by `scip-cli analyze --list-checks`.
CHECK_CATALOG: tuple[CheckDoc, ...] = (
    CheckDoc("cycles", "high", "project", "Import/mention cycles between files"),
    CheckDoc("unreferenced", "high", "project", "No index mentions (superset; skipped when dead_exports runs)"),
    CheckDoc("dead_exports", "high", "project", "Exports with no cross-file use in the index"),
    CheckDoc("dead_files", "high", "project", "Files with no importers in the index"),
    CheckDoc("stale_types", "high", "project", "Types/interfaces with no external consumers"),
    CheckDoc("same_file_only", "medium", "project", "Used only in defining file but file has external importers"),
    CheckDoc("test_only", "low", "project", "Cross-file consumers are all under test paths"),
    CheckDoc("single_importer_files", "low", "project", "Whole file imported from exactly one other file"),
    CheckDoc("one_line_exports", "low", "project", "Tiny exported functions that delegate to one other module"),
    CheckDoc("top_coupling", "low", "project", "File pairs that share the most symbol edges"),
    CheckDoc("bottlenecks", "low", "project", "High fan-in x fan-out symbols by index metrics"),
    CheckDoc("hotspots", "low", "project", "Most-referenced symbols"),
    CheckDoc("dead_in_file", "high", "file", "Exports in this file with no external refs"),
    CheckDoc("unreferenced", "high", "file", "Symbols in this file with no index mentions"),
    CheckDoc("unused_imports", "high", "file", "Import bindings with no use in this file (index)"),
    CheckDoc("single_use_imports", "low", "file", "Imported once here and used once repo-wide"),
    CheckDoc("change_surface", "medium", "file", "Exports ranked by external consumer count"),
    CheckDoc("file_consumers", "medium", "file", "Other files that reference this file's symbols"),
    CheckDoc("coupling", "low", "file", "Partner files for this path"),
    CheckDoc("imports_summary", "low", "file", "Import count and top bindings"),
    CheckDoc("top_symbols", "low", "file", "Highest-pressure exports in this file"),
    CheckDoc("consumer_files", "high", "symbol", "Files with direct mentions of this symbol"),
    CheckDoc("dependencies", "high", "symbol", "Cross-file symbols used inside this definition"),
    CheckDoc("affected", "low", "symbol", "Coarse transitive dependents"),
    CheckDoc("symbol_pressure", "low", "symbol", "LOC x fan-in/out metrics for one symbol"),
    CheckDoc("def_context", "low", "symbol", "Kind, location, display metadata"),
)

CHECK_KEYS = frozenset({doc.key for doc in CHECK_CATALOG})

SLOP_CHECK_BUNDLE = "dead_exports,dead_files,single_importer_files,one_line_exports"


def format_check_catalog() -> str:
    """Plain-text catalog for --list-checks and analyze --help epilog."""
    by_tier: dict[str, list[CheckDoc]] = {"high": [], "medium": [], "low": []}
    for doc in CHECK_CATALOG:
        by_tier[doc.priority].append(doc)
    lines = ["Analyze checks (use with --check NAME; combine with --priority):"]
    for tier in ("high", "medium", "low"):
        lines.append(f"  [{tier}]")
        for doc in sorted(by_tier[tier], key=lambda d: (d.scope, d.key)):
            lines.append(f"    {doc.key:<22} {doc.scope:<7} {doc.summary}")
    lines.append("")
    lines.append("Glue / slop pass (project, production):")
    lines.append(f"  scip-cli analyze --check {SLOP_CHECK_BUNDLE} --priority high,low --limit 40")
    lines.append("")
    lines.append("single_importer_files = one inbound file for the whole module.")
    lines.append("single_use_imports  = per-file analyze only: one import site + one global use.")
    lines.append("one_line_exports    = short def span; SCIP range includes wrapped signatures (Prettier).")
    lines.append("Full guide: scip-cli skill  (or README § Finding easy wins with analyze)")
    return "\n".join(lines)
