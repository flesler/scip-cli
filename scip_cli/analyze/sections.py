"""Priority ordering and filtering for analyze dashboards."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from .common import section
from .live import bind_live, reset_live

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


# One recipe per section. STEM = basename of the path in parentheses, no extension.
# Empty scip-cli rdeps is the SCIP gap, not proof unused. Do not rg the symbol name
# (short names like async match the whole repo).
_RG_STEM = (
    "Verify each row: rg -F STEM  (STEM = basename of the (...) path, no extension; ignore hits in that same file)"
)

FALSE_POSITIVE_PREFACES: dict[str, str] = {
    "dead_exports": ("Warn: SCIP misses require()/default exports; empty rdeps is not unused. " + _RG_STEM),
    "dead_files": ("Warn: SCIP often has no import edge (named import, barrel, require). " + _RG_STEM),
    "unreferenced": ("Warn: no index mentions — may still be called dynamically. " + _RG_STEM),
    "same_file_only": ("Warn: in-file only in SCIP — callers may be unindexed. " + _RG_STEM),
    "stale_types": ("Warn: type-only imports are often dropped by SCIP. " + _RG_STEM),
    "cycles": ("Warn: remaining cycles may be barrel re-exports. Confirm the listed files before refactoring."),
    "dead_in_file": ("Warn: SCIP may miss dynamic loading and export const arrows. " + _RG_STEM),
    "unreferenced_in_file": ("Warn: no index mentions — may still be registered dynamically. " + _RG_STEM),
    "unused_imports": ("Warn: may still be a type-only use SCIP did not bind. " + _RG_STEM),
    "test_only": ("Warn: index may miss production calls, so this can look test-only. " + _RG_STEM),
}


def _preface_for(key: str) -> str | None:
    return FALSE_POSITIVE_PREFACES.get(key)


TRUNCATION_LINE = "… truncated (raise --limit or --per-check-limit)"

# Project unreferenced survivors match dead_exports after filters; file unreferenced
# matches dead_in_file. Keep the redundant check only when the covering check is off.
_REDUNDANT_IF_COVERED = {
    "unreferenced": frozenset({"dead_exports", "dead_in_file"}),
}


@dataclass
class RowBudget:
    """Shared cap on result rows across analyze sections."""

    remaining: int

    def exhausted(self) -> bool:
        return self.remaining <= 0


def check_row_cap(remaining: int, per_check_limit: int | None) -> int:
    """Rows this check may emit: global remainder, optionally capped per check."""
    if per_check_limit is None:
        return remaining
    return min(remaining, per_check_limit)


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
    per_check_limit: int | None = None,
) -> list[tuple[str, list[str], str | None]]:
    """Run checks in priority order (high → low). `--limit` is a shared row budget.

    `--per-check-limit` (default unlimited) caps each section so one noisy check
    cannot spend the whole budget.
    """
    selected = [check for check in checks if priorities is None or check.priority in priorities]
    if check_keys is not None:
        selected = [check for check in selected if check.key in check_keys]
    selected.sort(key=lambda check: (_ORDER.index(check.priority), check.key))
    keys = {check.key for check in selected}
    skip = {redundant for redundant, covers in _REDUNDANT_IF_COVERED.items() if redundant in keys and keys & covers}
    if skip:
        selected = [check for check in selected if check.key not in skip]
    budget_obj: RowBudget = budget or RowBudget(remaining=limit)
    sections: list[tuple[str, list[str], str | None]] = []
    remaining_after = list(selected)
    token = bind_live(db)
    try:
        for index, check in enumerate(selected):
            if budget_obj.exhausted():
                remaining_after = selected[index:]
                break
            cap = check_row_cap(budget_obj.remaining, per_check_limit)
            raw = check.run(db, cap + 1, include_tests=include_tests, scope=scope)
            if not raw or raw == ["(none)"]:
                lines = raw or []
            else:
                truncated = len(raw) > cap
                lines = raw[:cap]
                budget_obj.remaining -= len(lines)
                if truncated:
                    lines.append(TRUNCATION_LINE)
            preface = check.false_positive_preface if check.false_positive_preface else _preface_for(check.key)
            sections.append(section(check.labeled_title(), lines, preface=preface))
        else:
            remaining_after = []
        if remaining_after and budget_obj.exhausted():
            sections.append(
                section(
                    "[note] Output truncated",
                    ["global --limit reached; later checks skipped (raise --limit)"],
                )
            )
        return sections
    finally:
        reset_live(token)
