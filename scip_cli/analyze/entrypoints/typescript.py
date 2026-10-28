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
_DIST_BIN_PATH = re.compile(
    r"(?:^|[\s|'\"`&;|])((?:dist|bin)/[\w./-]+?)(?=$|[\s'\"`&;])",
    re.IGNORECASE,
)


def _manifest_path_variants(package_root: Path, raw: str) -> list[str]:
    """Map package.json main/bin paths (often dist/*.js) to likely indexed source paths."""
    text = raw.strip().strip("'\"")
    if not text:
        return []
    candidates = [text]
    if text.startswith("dist/"):
        rest = text[5:]
        candidates.append(f"src/{rest}")
        if rest.endswith(".js"):
            candidates.append(f"src/{rest[:-3]}.ts")
        if not any(rest.endswith(ext) for ext in _JS_EXTENSIONS):
            for ext in (".ts", ".tsx", ".js"):
                candidates.append(f"src/{rest}{ext}")
    if text.endswith(".js"):
        candidates.append(f"{text[:-3]}.ts")
    if not any(text.endswith(ext) for ext in _JS_EXTENSIONS):
        for ext in (".ts", ".tsx", ".js"):
            candidates.append(f"{text}{ext}")

    variants: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = normalize_path_under_root(package_root, candidate, extensions=_JS_EXTENSIONS)
        if normalized and normalized not in seen:
            seen.add(normalized)
            variants.append(normalized)
    return variants


def _paths_from_script_command(package_root: Path, command: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for match in _SCRIPT_PATH.finditer(command):
        for variant in _manifest_path_variants(package_root, match.group(1)):
            if variant not in seen:
                seen.add(variant)
                paths.append(variant)
    for match in _DIST_BIN_PATH.finditer(command):
        for variant in _manifest_path_variants(package_root, match.group(1)):
            if variant not in seen:
                seen.add(variant)
                paths.append(variant)
    return paths


def _remember_manifest_paths(
    repo_root: Path,
    package_rel: Path,
    package_root: Path,
    raw: str,
    paths: set[str],
) -> None:
    for variant in _manifest_path_variants(package_root, raw):
        paths.add(path_in_repo(repo_root, package_rel, variant))


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
    main_field = data.get("main")
    if isinstance(main_field, str):
        _remember_manifest_paths(repo_root, package_rel, package_root, main_field, paths)
    bin_field = data.get("bin")
    if isinstance(bin_field, str):
        _remember_manifest_paths(repo_root, package_rel, package_root, bin_field, paths)
    elif isinstance(bin_field, dict):
        for value in bin_field.values():
            if isinstance(value, str):
                _remember_manifest_paths(repo_root, package_rel, package_root, value, paths)
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        for value in scripts.values():
            if isinstance(value, str):
                for path in _paths_from_script_command(package_root, value):
                    paths.add(path_in_repo(repo_root, package_rel, path))
    paths |= _paths_from_index_html(repo_root, package_rel, package_root)
    return paths


_HTML_SCRIPT_SRC = re.compile(
    r"""<script[^>]+src\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE,
)


def _paths_from_index_html(repo_root: Path, package_rel: Path, package_root: Path) -> set[str]:
    """Vite / SPA entry scripts referenced from index.html."""
    paths: set[str] = set()
    html_path = package_root / "index.html"
    if not html_path.is_file():
        return paths
    try:
        text = html_path.read_text(encoding="utf-8")
    except OSError:
        return paths
    for match in _HTML_SCRIPT_SRC.finditer(text):
        raw = match.group(1).strip()
        if not raw or raw.startswith(("http://", "https://", "//")):
            continue
        if raw.startswith("/"):
            raw = raw.lstrip("/")
        for variant in _manifest_path_variants(package_root, raw):
            paths.add(path_in_repo(repo_root, package_rel, variant))
    return paths


def declared_entrypoint_paths(project_root: Path) -> set[str]:
    """Paths from every package.json under the repo (root + monorepo packages)."""
    repo_root = project_root.resolve()
    paths: set[str] = set()
    for package_rel in discover_npm_package_dirs(repo_root):
        paths |= _paths_from_package_json(repo_root, package_rel)
    return paths
