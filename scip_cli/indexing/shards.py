"""Per-tsconfig shard fingerprints and cached part DBs for incremental reindex."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from ..tsconfig import resolved_include_or_files, tsconfig_for_project, walk_tsconfig_chain

MANIFEST_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
SHARDS_DIRNAME = "shards"

_SOURCE_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"})


def shards_dir(cache_dir: Path) -> Path:
    return Path(cache_dir) / SHARDS_DIRNAME


def manifest_path(cache_dir: Path) -> Path:
    return shards_dir(cache_dir) / MANIFEST_FILENAME


def shard_key(project: Path) -> str:
    """Stable manifest key for a TypeScript project path."""
    return project.as_posix()


def shard_db_filename(project: Path) -> str:
    stem = shard_key(project).replace("/", "__").replace("\\", "__")
    return f"{stem}.db"


def shard_db_path(cache_dir: Path, project: Path) -> Path:
    return shards_dir(cache_dir) / shard_db_filename(project)


def clear_shard_cache(cache_dir: Path) -> None:
    """Remove persisted shard part DBs and manifest."""
    root = shards_dir(cache_dir)
    if root.is_dir():
        shutil.rmtree(root)


def load_shard_manifest(cache_dir: Path) -> dict[str, dict[str, str]]:
    """Return shard key → {fingerprint, part_db} from manifest.json."""
    path = manifest_path(cache_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    raw_shards = data.get("shards")
    if not isinstance(raw_shards, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, entry in raw_shards.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        fingerprint = entry.get("fingerprint")
        part_db = entry.get("part_db")
        if isinstance(fingerprint, str) and isinstance(part_db, str):
            out[key] = {"fingerprint": fingerprint, "part_db": part_db}
    return out


def save_shard_manifest(cache_dir: Path, shards: dict[str, dict[str, str]]) -> None:
    """Merge shard entries into manifest.json (full reindex clears stale entries)."""
    root = shards_dir(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    merged = {**load_shard_manifest(cache_dir), **shards}
    payload = {
        "version": MANIFEST_VERSION,
        "shards": {
            key: {"fingerprint": entry["fingerprint"], "part_db": entry["part_db"]}
            for key, entry in sorted(merged.items())
        },
    }
    manifest_path(cache_dir).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _glob_source_files(base_dir: Path, patterns: list[str]) -> list[Path]:
    found: set[Path] = set()
    for pattern in patterns:
        if Path(pattern).is_absolute():
            candidate = Path(pattern)
            if candidate.is_file() and candidate.suffix.lower() in _SOURCE_SUFFIXES:
                found.add(candidate.resolve())
            continue
        for match in base_dir.glob(pattern):
            if match.is_file() and match.suffix.lower() in _SOURCE_SUFFIXES:
                found.add(match.resolve())
    return sorted(found)


def list_project_source_files(root: Path, project: Path) -> list[Path]:
    """Source files that contribute to a shard fingerprint (tsconfig include/files)."""
    root = Path(root).resolve()
    tsconfig = tsconfig_for_project(root, project)
    if tsconfig is None:
        return []

    include, files = resolved_include_or_files(tsconfig)
    base_dir = tsconfig.parent
    if files is not None:
        return _glob_source_files(base_dir, files)
    if include is not None:
        return _glob_source_files(base_dir, include)
    return _glob_source_files(base_dir, ["**/*"])


def compute_shard_fingerprint(
    root: Path,
    project: Path,
    *,
    exclude_globs: tuple[str, ...] = (),
) -> str:
    """Hash tsconfig chain + indexed sources + exclude globs for one project shard."""
    root = Path(root).resolve()
    tsconfig = tsconfig_for_project(root, project)
    digest = hashlib.sha256()
    digest.update(shard_key(project).encode())
    digest.update(b"\0")

    if tsconfig is not None:
        for path, _data in walk_tsconfig_chain(tsconfig):
            digest.update(path.as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")

    for path in list_project_source_files(root, project):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(_hash_file(path).encode())
        digest.update(b"\0")

    for glob in exclude_globs:
        digest.update(glob.encode())
        digest.update(b"\0")

    return digest.hexdigest()


def resolve_cached_shard_db(
    cache_dir: Path,
    project: Path,
    fingerprint: str,
    manifest: dict[str, dict[str, str]],
) -> Path | None:
    """Return a reusable shard part DB when fingerprint and file both match."""
    key = shard_key(project)
    entry = manifest.get(key)
    if entry is None or entry.get("fingerprint") != fingerprint:
        return None
    candidate = shards_dir(cache_dir) / Path(entry["part_db"]).name
    if candidate.is_file():
        return candidate
    fallback = shard_db_path(cache_dir, project)
    if fallback.is_file():
        return fallback
    return None
