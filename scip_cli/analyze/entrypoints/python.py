"""Entrypoints from pyproject/setup scripts and __main__ modules."""

from __future__ import annotations

import configparser
import re
from pathlib import Path

from ...discover import discover_python_projects
from .paths import canonical_rel, path_in_repo

_PYPROJECT_SCRIPT = re.compile(
    r'^\s*(\S+)\s*=\s*"([^"]+)"\s*$',
    re.MULTILINE,
)
_CONSOLE_SCRIPT_ITEM = re.compile(r"['\"]([^'\"=]+)=([^'\"]+)['\"]")


def _module_target_to_py_file(module_target: str) -> str | None:
    module = module_target.split(":", 1)[0].strip()
    if not module:
        return None
    return canonical_rel(module.replace(".", "/") + ".py")


def _pyproject_scripts_block(text: str) -> str | None:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "[project.scripts]":
            start = index + 1
            break
    if start is None:
        return None
    block: list[str] = []
    for line in lines[start:]:
        if line.startswith("[") and line.endswith("]"):
            break
        block.append(line)
    return "\n".join(block)


def _paths_from_pyproject(package_root: Path, repo_root: Path, package_rel: Path) -> set[str]:
    paths: set[str] = set()
    path = package_root / "pyproject.toml"
    if not path.is_file():
        return paths
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return paths
    block = _pyproject_scripts_block(text)
    if not block:
        return paths
    for match in _PYPROJECT_SCRIPT.finditer(block):
        py_file = _module_target_to_py_file(match.group(2))
        if py_file:
            paths.add(path_in_repo(repo_root, package_rel, py_file))
    return paths


def _paths_from_setup_py(package_root: Path, repo_root: Path, package_rel: Path) -> set[str]:
    paths: set[str] = set()
    path = package_root / "setup.py"
    if not path.is_file():
        return paths
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return paths
    block_match = re.search(
        r"console_scripts['\"]?\s*:\s*\[(.*?)\]",
        text,
        re.DOTALL,
    )
    if not block_match:
        return paths
    for match in _CONSOLE_SCRIPT_ITEM.finditer(block_match.group(1)):
        py_file = _module_target_to_py_file(match.group(2))
        if py_file:
            paths.add(path_in_repo(repo_root, package_rel, py_file))
    return paths


def _paths_from_setup_cfg(package_root: Path, repo_root: Path, package_rel: Path) -> set[str]:
    paths: set[str] = set()
    path = package_root / "setup.cfg"
    if not path.is_file():
        return paths
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        return paths
    if not parser.has_section("options.entry_points"):
        return paths
    if not parser.has_option("options.entry_points", "console_scripts"):
        return paths
    block = parser.get("options.entry_points", "console_scripts")
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        _name, _, target = stripped.partition("=")
        py_file = _module_target_to_py_file(target.strip())
        if py_file:
            paths.add(path_in_repo(repo_root, package_rel, py_file))
    return paths


def _paths_from_package(package_root: Path, repo_root: Path, package_rel: Path) -> set[str]:
    paths = _paths_from_pyproject(package_root, repo_root, package_rel)
    paths |= _paths_from_setup_py(package_root, repo_root, package_rel)
    paths |= _paths_from_setup_cfg(package_root, repo_root, package_rel)
    return paths


def declared_entrypoint_paths(project_root: Path) -> set[str]:
    repo_root = project_root.resolve()
    paths: set[str] = set()
    for package_rel in discover_python_projects(repo_root):
        package_root = repo_root / package_rel
        paths |= _paths_from_package(package_root, repo_root, package_rel)
    return paths


def is_python_entrypoint_file(relative_path: str) -> bool:
    return canonical_rel(relative_path).endswith("__main__.py")
