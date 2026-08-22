"""Priority ordering and filtering for analyze dashboards."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from .common import section

CheckFn = Callable[..., list[str]]


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_ORDER = (Priority.HIGH, Priority.MEDIUM, Priority.LOW)
_ALIASES = {
    "1": Priority.HIGH,
    "2": Priority.MEDIUM,
    "3": Priority.LOW,
    "h": Priority.HIGH,
    "m": Priority.MEDIUM,
    "l": Priority.LOW,
}


def parse_priorities(value: str | None) -> set[Priority] | None:
    """Parse --priority (comma-separated names or 1/2/3). None means all levels."""
    if not value:
        return None
    out: set[Priority] = set()
    for part in value.replace(" ", "").split(","):
        if not part:
            continue
        key = part.lower()
        if key in _ALIASES:
            out.add(_ALIASES[key])
            continue
        try:
            out.add(Priority(key))
        except ValueError as exc:
            allowed = ", ".join(p.value for p in Priority)
            raise RuntimeError(f"unknown analyze priority {part!r} (use {allowed} or 1/2/3)") from exc
    return out


# Project, file, and symbol Check.key values. --check rejects anything else.
CHECK_KEYS = frozenset(
    {
        "affected",
        "bottlenecks",
        "change_surface",
        "consumer_files",
        "coupling",
        "cycles",
        "dead_exports",
        "dead_files",
        "dead_in_file",
        "def_context",
        "dependencies",
        "file_consumers",
        "hotspots",
        "imports_summary",
        "same_file_only",
        "stale_types",
        "symbol_pressure",
        "test_only",
        "top_coupling",
        "top_symbols",
        "unreferenced",
        "unused_imports",
    }
)


def parse_checks(values: list[str] | None) -> set[str] | None:
    """Parse --check (repeatable; commas allowed). None means all checks."""
    if not values:
        return None
    out: set[str] = set()
    for value in values:
        for part in value.replace(" ", "").split(","):
            if not part:
                continue
            key = part.lower()
            if key not in CHECK_KEYS:
                allowed = ", ".join(sorted(CHECK_KEYS))
                raise RuntimeError(f"unknown analyze check {part!r} (use {allowed})")
            out.add(key)
    if not out:
        return None
    return out


@dataclass(frozen=True)
class Check:
    key: str
    priority: Priority
    title: str
    run: CheckFn
    false_positive_preface: str | None = None

    def labeled_title(self) -> str:
        return f"[{self.priority.value}] {self.title}"


# Shown only when the section has hits (not "(none)"). Situation hints, not exhaustive.
FALSE_POSITIVE_PREFACES: dict[str, str] = {
    "dead_exports": (
        "SCIP may miss dynamic loading (loadFiles, GraphQL), default-export object members, "
        "and some export const arrows — verify with rdeps/rg before deleting."
    ),
    "dead_files": (
        "Empty rdeps in the index. SCIP often records export const / arrow files as module-only, "
        "so named imports (routes, barrels) may not count; same for dynamic require. Confirm with rg."
    ),
    "unreferenced": (
        "No mentions in the index — may still run via dynamic import, side-effect registration, "
        "or a call SCIP did not record."
    ),
    "same_file_only": (
        "Referenced only in the defining file — often handlers or private helpers, "
        "or an external call SCIP missed; not necessarily a dead export."
    ),
    "stale_types": (
        "No cross-file refs in the index — may still be used in-file, as a type-only import SCIP dropped, "
        "or as a structural shape."
    ),
    "cycles": "Remaining cycles may be barrel re-exports; confirm before refactoring.",
    "dead_in_file": (
        "SCIP may miss dynamic loading, default-export indirection, and some export const arrows "
        "— verify with rdeps/rg before deleting."
    ),
    "unreferenced_in_file": (
        "No mentions in the index — may still be used in-file via handlers or dynamic registration."
    ),
    "unused_imports": ("Import may still be a type-only use or a name SCIP did not bind — confirm before removing."),
    "test_only": "Index may miss same-file production calls, so this can look test-only when it is not.",
}


def _preface_for(key: str) -> str | None:
    return FALSE_POSITIVE_PREFACES.get(key)


@dataclass
class RowBudget:
    """Shared cap on result rows across analyze sections."""

    remaining: int

    def exhausted(self) -> bool:
        return self.remaining <= 0


def run_checks(
    checks: list[Check],
    db,
    limit: int,
    priorities: set[Priority] | None,
    *,
    include_tests: bool = False,
    scope: str | None = None,
    budget: RowBudget | None = None,
    check_keys: set[str] | None = None,
) -> list[tuple[str, list[str], str | None]]:
    """Run checks in priority order (high → low), optionally filtered."""
    selected = [check for check in checks if priorities is None or check.priority in priorities]
    if check_keys is not None:
        selected = [check for check in selected if check.key in check_keys]
    selected.sort(key=lambda check: (_ORDER.index(check.priority), check.key))
    budget_obj: RowBudget = budget or RowBudget(remaining=limit)
    sections: list[tuple[str, list[str], str | None]] = []
    for check in selected:
        if budget_obj.exhausted():
            break
        lines = check.run(db, budget_obj.remaining, include_tests=include_tests, scope=scope)
        if lines != ["(none)"]:
            lines = lines[: budget_obj.remaining]
            budget_obj.remaining -= len(lines)
        preface = check.false_positive_preface if check.false_positive_preface else _preface_for(check.key)
        sections.append(section(check.labeled_title(), lines, preface=preface))
    return sections
