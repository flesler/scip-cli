"""Resolve --tsconfig arguments to repo-relative tsconfig*.json paths."""

from __future__ import annotations

from pathlib import Path

from .discover import _SKIP_DIR_NAMES

_GLOB_CHARS = frozenset("*?[")


def is_tsconfig_filename(name: str) -> bool:
    """True for TypeScript config files (tsconfig.json, tsconfig.app.json, …)."""
    return name.startswith("tsconfig") and name.endswith(".json")


def is_tsconfig_project_path(path: Path) -> bool:
    """True when a project path is an explicit tsconfig file rather than a directory."""
    return is_tsconfig_filename(path.name)


def scope_tsconfig_paths(paths: tuple[str, ...]) -> list[Path] | None:
    """Return explicit tsconfig paths when the whole scope is file-based.

    Directory-prefix scopes return None. Mixed file/directory scopes raise.
    """
    if not paths:
        return None
    flags = [is_tsconfig_filename(Path(path).name) for path in paths]
    if all(flags):
        return [Path(path) for path in paths]
    if any(flags):
        raise RuntimeError("index scope mixes tsconfig files and directory prefixes")
    return None


def _skipped_relative(relative: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES or part.startswith(".") for part in relative.parts)


def _relative_to_root(path: Path, root: Path, original: str) -> Path:
    try:
        return path.resolve().relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"--tsconfig escapes project root: {original}") from exc


def _validate_tsconfig_file(path: Path, root: Path, original: str) -> Path:
    if not path.is_file():
        raise RuntimeError(f"--tsconfig is not a file: {original}")
    relative = _relative_to_root(path, root, original)
    if _skipped_relative(relative):
        raise RuntimeError(f"--tsconfig is under a skipped directory: {relative.as_posix()}")
    if not is_tsconfig_filename(path.name):
        raise RuntimeError(f"--tsconfig expected tsconfig*.json, got {relative.as_posix()}")
    return relative


def expand_tsconfig_patterns(patterns: list[str], project_root: Path) -> list[Path]:
    """Expand --tsconfig args (globs allowed) to sorted, unique, repo-relative paths."""
    root = Path(project_root).resolve()
    found: list[Path] = []
    seen: set[str] = set()

    for pattern in patterns:
        if not pattern:
            raise RuntimeError("invalid or empty --tsconfig")
        if any(char in pattern for char in _GLOB_CHARS):
            matches = [path for path in sorted(root.glob(pattern)) if path.is_file()]
            kept: list[Path] = []
            for match in matches:
                relative = _relative_to_root(match, root, pattern)
                if _skipped_relative(relative):
                    continue
                if not is_tsconfig_filename(match.name):
                    continue
                kept.append(relative)
            if not kept:
                raise RuntimeError(f"No tsconfig files matched --tsconfig {pattern!r}")
            candidates = kept
        else:
            candidate = Path(pattern)
            if not candidate.is_absolute():
                candidate = root / candidate
            candidates = [_validate_tsconfig_file(candidate, root, pattern)]

        for relative in candidates:
            key = relative.as_posix()
            if key not in seen:
                seen.add(key)
                found.append(relative)

    return sorted(found, key=str)
