"""Entrypoints from package.json bin and scripts (Node / TS / JS projects)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ...discover import discover_npm_package_dirs
from .paths import normalize_path_under_root, path_in_repo

_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_SCRIPT_PATH = re.compile(
    r"(?:^|[\s|'\"`&;|])((?:[\w.-]+/)+[\w.-]+\.(?:tsx?|jsx?|mjs|cjs)|[\./][\w./-]+\.(?:tsx?|jsx?|mjs|cjs)|[\w][\w.-]*\.(?:tsx?|jsx?|mjs|cjs))(?=$|[\s'\"`&;])",
    re.IGNORECASE,
)


def _paths_from_script_command(package_root: Path, command: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for match in _SCRIPT_PATH.finditer(command):
        raw = match.group(1)
        normalized = normalize_path_under_root(package_root, raw, extensions=_JS_EXTENSIONS)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        paths.append(normalized)
    return paths


def _paths_from_package_json(repo_root: Path, package_rel: Path) -> set[str]:
    paths: set[str] = set()
    package_root = repo_root / package_rel
    pkg_path = package_root / "package.json"
    if not pkg_path.is_file():
        return paths
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return paths
    bin_field = data.get("bin")
    if isinstance(bin_field, str):
        normalized = normalize_path_under_root(package_root, bin_field, extensions=_JS_EXTENSIONS)
        if normalized:
            paths.add(path_in_repo(repo_root, package_rel, normalized))
    elif isinstance(bin_field, dict):
        for value in bin_field.values():
            if isinstance(value, str):
                normalized = normalize_path_under_root(package_root, value, extensions=_JS_EXTENSIONS)
                if normalized:
                    paths.add(path_in_repo(repo_root, package_rel, normalized))
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        for value in scripts.values():
            if isinstance(value, str):
                for path in _paths_from_script_command(package_root, value):
                    paths.add(path_in_repo(repo_root, package_rel, path))
    return paths


def declared_entrypoint_paths(project_root: Path) -> set[str]:
    """Paths from every package.json under the repo (root + monorepo packages)."""
    repo_root = project_root.resolve()
    paths: set[str] = set()
    for package_rel in discover_npm_package_dirs(repo_root):
        paths |= _paths_from_package_json(repo_root, package_rel)
    return paths
