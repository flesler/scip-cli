"""Entrypoints for Rust crates (Cargo.toml [[bin]] and default src/main.rs)."""

from __future__ import annotations

import re
from pathlib import Path

from ...discover import discover_rust_crates
from .paths import path_in_repo

_BIN_PATH = re.compile(r'^\s*path\s*=\s*"([^"]+)"\s*$')


def _paths_from_cargo(crate_root: Path, repo_root: Path, crate_rel: Path) -> set[str]:
    paths: set[str] = set()
    cargo_path = crate_root / "Cargo.toml"
    if not cargo_path.is_file():
        return paths
    try:
        lines = cargo_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return paths
    in_bin = False
    saw_bin_table = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[[bin]]":
            in_bin = True
            saw_bin_table = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_bin = False
            continue
        if in_bin:
            match = _BIN_PATH.match(stripped)
            if match:
                paths.add(path_in_repo(repo_root, crate_rel, match.group(1)))
    if not saw_bin_table and (crate_root / "src" / "main.rs").is_file():
        paths.add(path_in_repo(repo_root, crate_rel, "src/main.rs"))
    return paths


def declared_entrypoint_paths(project_root: Path) -> set[str]:
    repo_root = project_root.resolve()
    paths: set[str] = set()
    for crate_rel in discover_rust_crates(repo_root):
        crate_root = repo_root / crate_rel
        paths |= _paths_from_cargo(crate_root, repo_root, crate_rel)
    return paths
