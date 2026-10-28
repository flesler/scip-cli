"""Shared path normalization for entrypoint manifests."""

from __future__ import annotations

from pathlib import Path


def canonical_rel(relative_path: str) -> str:
    return relative_path.replace("\\", "/").lstrip("./")


def path_in_repo(_repo_root: Path, package_rel: Path, path_in_package: str) -> str:
    """Map a path relative to a package dir to a repo-relative path."""
    rel = path_in_package.replace("\\", "/").lstrip("./")
    if not package_rel.parts:
        return canonical_rel(rel)
    prefix = package_rel.as_posix().strip("/")
    return canonical_rel(f"{prefix}/{rel}")


def normalize_path_under_root(project_root: Path, raw: str, *, extensions: tuple[str, ...]) -> str | None:
    text = raw.strip().strip("'\"")
    if not text:
        return None
    if not any(text.endswith(ext) for ext in extensions):
        return None
    root = project_root.resolve()
    path = Path(text)
    if path.is_absolute():
        try:
            return canonical_rel(str(path.resolve().relative_to(root)))
        except ValueError:
            return None
    return canonical_rel(text)
