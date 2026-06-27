"""Priority ordering and filtering for analyze dashboards."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

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

    def labeled_title(self) -> str:
        return f"[{self.priority.value}] {self.title}"


def run_checks(
    checks: list[Check],
    db,
    limit: int,
    priorities: set[Priority] | None,
    **kwargs: Any,
) -> list[tuple[str, list[str]]]:
    """Run checks in priority order (high → low), optionally filtered."""
    selected = [check for check in checks if priorities is None or check.priority in priorities]
    selected.sort(key=lambda check: (_ORDER.index(check.priority), check.key))
    sections: list[tuple[str, list[str]]] = []
    for check in selected:
        lines = check.run(db, limit, **kwargs)
        sections.append(section(check.labeled_title(), lines))
    return sections
