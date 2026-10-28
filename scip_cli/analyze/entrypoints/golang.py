"""Entrypoints for Go modules (manifest parsing not implemented yet)."""

from __future__ import annotations

from pathlib import Path


def declared_entrypoint_paths(project_root: Path) -> set[str]:
    """Reserved for go.mod main packages and cmd/* layout heuristics."""
    _ = project_root
    return set()
