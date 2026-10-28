"""Entrypoints for Go modules (main.go and cmd/*/main.go)."""

from __future__ import annotations

from pathlib import Path

from ...discover import discover_golang_modules
from .paths import path_in_repo


def declared_entrypoint_paths(project_root: Path) -> set[str]:
    repo_root = project_root.resolve()
    paths: set[str] = set()
    for mod_rel in discover_golang_modules(repo_root):
        mod_root = repo_root / mod_rel
        if (mod_root / "main.go").is_file():
            paths.add(path_in_repo(repo_root, mod_rel, "main.go"))
        cmd_dir = mod_root / "cmd"
        if not cmd_dir.is_dir():
            continue
        for child in cmd_dir.iterdir():
            if not child.is_dir():
                continue
            main_go = child / "main.go"
            if main_go.is_file():
                rel = main_go.relative_to(mod_root).as_posix()
                paths.add(path_in_repo(repo_root, mod_rel, rel))
    return paths
