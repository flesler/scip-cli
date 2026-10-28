"""Entrypoints for Rust crates (manifest parsing not implemented yet)."""

from __future__ import annotations

from pathlib import Path


def declared_entrypoint_paths(project_root: Path) -> set[str]:
    """Reserved for Cargo.toml [[bin]] targets."""
    _ = project_root
    return set()
