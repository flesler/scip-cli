"""Discover TypeScript source paths for shard indexing."""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from ..discover import SKIP_DIR_NAMES
from ..exclude import path_matches_glob
from ..metadata import index_unversioned
from ..tsconfig import resolved_exclude, resolved_include_or_files, tsconfig_for_project

_SOURCE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})


def source_suffixes() -> frozenset[str]:
    return _SOURCE_SUFFIXES


def _is_source_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _SOURCE_SUFFIXES


def _relative_posix(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _path_under_base(relative: str, base_rel: str) -> bool:
    if not base_rel or base_rel == ".":
        return True
    return relative == base_rel or relative.startswith(f"{base_rel}/")


def _relative_to_tsconfig_base(relative: str, base_rel: str) -> str:
    if not base_rel or base_rel == ".":
        return relative
    prefix = f"{base_rel}/"
    if not relative.startswith(prefix):
        return relative
    return relative[len(prefix) :]


def _matches_tsconfig_files(files: list[str], rel_to_base: str) -> bool:
    normalized = rel_to_base.replace("\\", "/")
    for entry in files:
        entry_norm = entry.replace("\\", "/").lstrip("./")
        if normalized == entry_norm:
            return True
        if Path(entry_norm).name == Path(normalized).name and entry_norm.endswith(normalized):
            return True
    return False


def _matches_tsconfig_include(include: list[str], rel_to_base: str) -> bool:
    return any(path_matches_glob(rel_to_base, pattern) for pattern in include)


def _excluded_by_tsconfig(exclude_patterns: list[str], rel_to_base: str) -> bool:
    return any(path_matches_glob(rel_to_base, pattern) for pattern in exclude_patterns)


def _path_matches_tsconfig_rules(
    relative: str,
    base_rel: str,
    *,
    include: list[str] | None,
    files: list[str] | None,
    exclude_patterns: list[str],
) -> bool:
    relative = relative.replace("\\", "/").lstrip("/")
    if not _path_under_base(relative, base_rel):
        return False
    suffix = Path(relative).suffix.lower()
    if suffix and suffix not in _SOURCE_SUFFIXES:
        return False
    rel_to_base = _relative_to_tsconfig_base(relative, base_rel)
    if files is not None:
        if not _matches_tsconfig_files(files, rel_to_base):
            return False
    elif include is not None:
        if not _matches_tsconfig_include(include, rel_to_base):
            return False
    elif not path_matches_glob(rel_to_base, "**/*"):
        return False
    return not _excluded_by_tsconfig(exclude_patterns, rel_to_base)


def path_matches_tsconfig_shard(root: Path, tsconfig: Path, relative: str) -> bool:
    """True when a repo-relative path belongs to a shard (file need not exist — deletions)."""
    base_dir = tsconfig.parent.resolve()
    try:
        base_rel = _relative_posix(base_dir, root.resolve())
    except ValueError:
        base_rel = ""
    include, files = resolved_include_or_files(tsconfig)
    exclude_patterns = resolved_exclude(tsconfig)
    return _path_matches_tsconfig_rules(
        relative,
        base_rel,
        include=include,
        files=files,
        exclude_patterns=exclude_patterns,
    )


def filter_tsconfig_candidates(
    root: Path,
    tsconfig: Path,
    candidates: list[str],
) -> list[Path]:
    include, files = resolved_include_or_files(tsconfig)
    exclude_patterns = resolved_exclude(tsconfig)
    base_dir = tsconfig.parent.resolve()
    try:
        base_rel = _relative_posix(base_dir, root.resolve())
    except ValueError:
        base_rel = ""

    found: list[Path] = []
    seen: set[str] = set()
    for relative in candidates:
        relative = relative.replace("\\", "/").lstrip("/")
        if not _path_matches_tsconfig_rules(
            relative,
            base_rel,
            include=include,
            files=files,
            exclude_patterns=exclude_patterns,
        ):
            continue
        path = (root / relative).resolve()
        if not _is_source_file(path):
            continue
        key = path.as_posix()
        if key not in seen:
            seen.add(key)
            found.append(path)
    return sorted(found)


def _walk_glob_source_files(base_dir: Path, patterns: list[str]) -> list[Path]:
    base_dir = base_dir.resolve()
    if not patterns:
        patterns = ["**/*"]

    found: set[Path] = set()
    for pattern in patterns:
        candidate = Path(pattern)
        if candidate.is_absolute():
            if _is_source_file(candidate):
                found.add(candidate.resolve())
            continue

        for dirpath, dirnames, filenames in os.walk(base_dir, topdown=True):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIR_NAMES and not name.startswith(".")]
            for name in filenames:
                path = Path(dirpath) / name
                if not _is_source_file(path):
                    continue
                rel = _relative_posix(path, base_dir)
                if path_matches_glob(rel, pattern):
                    found.add(path.resolve())
    return sorted(found)


def _git_available() -> bool:
    return shutil.which("git") is not None


def is_versioned_repo(root: Path) -> bool:
    """True in a git worktree with git on PATH."""
    root = root.resolve()
    return (root / ".git").exists() and _git_available()


def clear_git_index_cache() -> None:
    _git_indexed_paths.cache_clear()


@lru_cache(maxsize=64)
def _git_indexed_paths(root: Path, pathspec: str = "") -> tuple[str, ...] | None:
    root = root.resolve()
    if not is_versioned_repo(root):
        return None
    args = [
        "git",
        "-C",
        str(root),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    if pathspec:
        args.extend(["--", pathspec])
    proc = subprocess.run(args, capture_output=True, check=False)
    if proc.returncode != 0:
        return None
    return tuple(part.decode("utf-8", errors="surrogateescape") for part in proc.stdout.split(b"\0") if part)


def list_project_source_files(root: Path, project: Path) -> list[Path]:
    """Source files for one tsconfig shard (git ls-files or skip-dir glob)."""
    root = Path(root).resolve()
    tsconfig = tsconfig_for_project(root, project)
    if tsconfig is None:
        return []

    use_git = is_versioned_repo(root) and not index_unversioned(root)
    if use_git:
        try:
            base_rel = _relative_posix(tsconfig.parent.resolve(), root)
        except ValueError:
            base_rel = ""
        pathspec = f"{base_rel}/" if base_rel and base_rel != "." else ""
        indexed = _git_indexed_paths(root, pathspec)
        if indexed is not None:
            return filter_tsconfig_candidates(root, tsconfig, list(indexed))

    include, files = resolved_include_or_files(tsconfig)
    base_dir = tsconfig.parent
    if files is not None:
        patterns = files
    elif include is not None:
        patterns = include
    else:
        patterns = ["**/*"]
    candidates = _walk_glob_source_files(base_dir, patterns)
    exclude_patterns = resolved_exclude(tsconfig)
    if not exclude_patterns:
        return candidates
    filtered: list[Path] = []
    for path in candidates:
        try:
            rel_to_base = _relative_posix(path, base_dir)
        except ValueError:
            continue
        if not _excluded_by_tsconfig(exclude_patterns, rel_to_base):
            filtered.append(path)
    return filtered
