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


@dataclass(frozen=True)
class Check:
    key: str
    priority: Priority
    title: str
    run: CheckFn
    false_positive_preface: str | None = None

    def labeled_title(self) -> str:
        return f"[{self.priority.value}] {self.title}"


# Shown only when the section has hits (not "(none)").
FALSE_POSITIVE_PREFACES: dict[str, str] = {
    "dead_exports": (
        "SCIP may miss dynamic loading (loadFiles, GraphQL) and default-export object members "
        "— verify with rdeps/rg before deleting."
    ),
    "unreferenced": (
        "No mentions in the index — symbols may still run via dynamic import or side-effect registration."
    ),
    "same_file_only": ("Referenced only in the defining file — often handlers or private helpers, not dead exports."),
    "stale_types": ("No cross-file refs in the index — may still be used in-file or as a type-only shape."),
    "cycles": "Remaining cycles may be barrel re-exports; confirm before refactoring.",
    "dead_in_file": (
        "SCIP may miss dynamic loading and default-export indirection — verify with rdeps/rg before deleting."
    ),
    "unreferenced_in_file": (
        "No mentions in the index — may still be used in-file via handlers or dynamic registration."
    ),
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
) -> list[tuple[str, list[str], str | None]]:
    """Run checks in priority order (high → low), optionally filtered."""
    selected = [check for check in checks if priorities is None or check.priority in priorities]
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
