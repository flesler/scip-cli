"""Resolve --tsconfig arguments to repo-relative tsconfig*.json paths."""

from __future__ import annotations

from pathlib import Path

from .discover import SKIP_DIR_NAMES, read_json

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
    return any(part in SKIP_DIR_NAMES or part.startswith(".") for part in relative.parts)


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


def _extends_files(data: dict[str, object], current: Path) -> list[Path]:
    raw = data.get("extends")
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = [item for item in raw if isinstance(item, str)]
    else:
        return []
    found: list[Path] = []
    for item in items:
        if not item.startswith(".") and not item.startswith("/"):
            continue
        candidate = (current.parent / item).resolve()
        if candidate.is_file():
            found.append(candidate)
        elif candidate.with_suffix(".json").is_file():
            found.append(candidate.with_suffix(".json"))
    return found


def walk_tsconfig_chain(path: Path) -> list[tuple[Path, dict[str, object]]]:
    """Leaf-first chain of parsed tsconfig files following `extends`."""
    chain: list[tuple[Path, dict[str, object]]] = []
    seen: set[Path] = set()
    current = path.resolve()
    while current.is_file() and current not in seen:
        seen.add(current)
        data = read_json(current)
        if not data:
            break
        chain.append((current, data))
        extended = _extends_files(data, current)
        if not extended:
            break
        current = extended[0]
    return chain


def resolved_allow_js(path: Path) -> bool:
    """compilerOptions.allowJs after `extends` (child wins). Default false."""
    for _file, data in walk_tsconfig_chain(path):
        options = data.get("compilerOptions")
        if isinstance(options, dict) and "allowJs" in options:
            return bool(options["allowJs"])
    return False


def resolved_include_or_files(path: Path) -> tuple[list[str] | None, list[str] | None]:
    """First `include` or `files` found walking leaf → base. The other is None."""
    for _file, data in walk_tsconfig_chain(path):
        include = data.get("include")
        if isinstance(include, list) and all(isinstance(item, str) for item in include):
            return include, None
        files = data.get("files")
        if isinstance(files, list) and all(isinstance(item, str) for item in files):
            return None, files
    return None, None


def ts_pattern_to_js(pattern: str) -> str | None:
    """Map a .ts/.tsx glob or path to .js/.jsx. Leaves .d.ts and extensionless globs alone."""
    if pattern.endswith(".d.ts"):
        return None
    if pattern.endswith(".tsx"):
        return pattern[: -len(".tsx")] + ".jsx"
    if pattern.endswith(".ts"):
        return pattern[: -len(".ts")] + ".js"
    return None


def extra_js_patterns(patterns: list[str]) -> list[str]:
    """JS/JSX counterparts not already listed."""
    existing = set(patterns)
    extra: list[str] = []
    for pattern in patterns:
        mapped = ts_pattern_to_js(pattern)
        if mapped and mapped not in existing and mapped not in extra:
            extra.append(mapped)
    return extra


def absolutize_patterns(patterns: list[str], base_dir: Path) -> list[str]:
    """Make include/files patterns absolute so a temp tsconfig in another dir still matches."""
    out: list[str] = []
    for pattern in patterns:
        candidate = Path(pattern)
        if candidate.is_absolute():
            out.append(pattern)
        else:
            out.append((base_dir / pattern).as_posix())
    return out


def allow_js_overlay(tsconfig_path: Path) -> dict[str, object] | None:
    """Temp tsconfig body that adds JS includes when allowJs is true.

    Returns None when JS is already covered or allowJs is false. `include`/`files`
    are absolute so the overlay can live outside the project directory.
    """
    path = tsconfig_path.resolve()
    if not path.is_file() or not resolved_allow_js(path):
        return None
    include, files = resolved_include_or_files(path)
    base_dir = path.parent
    if include is not None:
        extra = extra_js_patterns(include)
        if not extra:
            return None
        return {
            "extends": path.as_posix(),
            "include": absolutize_patterns([*include, *extra], base_dir),
        }
    if files is not None:
        extra = extra_js_patterns(files)
        if not extra:
            return None
        return {
            "extends": path.as_posix(),
            "files": absolutize_patterns([*files, *extra], base_dir),
        }
    return None


def tsconfig_for_project(root: Path, project: Path) -> Path | None:
    """Absolute tsconfig file for a discovered directory or an explicit tsconfig path."""
    root = Path(root).resolve()
    candidate = project if project.is_absolute() else root / project
    if is_tsconfig_project_path(candidate):
        return candidate.resolve() if candidate.is_file() else None
    tsconfig = candidate / "tsconfig.json"
    return tsconfig.resolve() if tsconfig.is_file() else None
