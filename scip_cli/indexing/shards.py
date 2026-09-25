"""Per-tsconfig shard manifest for git-anchored incremental reindex."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from ..metadata import index_unversioned
from ..tsconfig import tsconfig_for_project, walk_tsconfig_chain
from .git_delta import GitIndexDelta, git_head, git_is_ancestor

MANIFEST_VERSION = 4
MANIFEST_FILENAME = "manifest.json"
SHARDS_DIRNAME = "shards"
TSBUILDINFO_DIRNAME = "tsbuildinfo"


def shards_dir(cache_dir: Path) -> Path:
    return Path(cache_dir) / SHARDS_DIRNAME


def ts_build_info_dir(cache_dir: Path) -> Path:
    return Path(cache_dir) / TSBUILDINFO_DIRNAME


def manifest_path(cache_dir: Path) -> Path:
    return shards_dir(cache_dir) / MANIFEST_FILENAME


def shard_key(project: Path) -> str:
    return project.as_posix()


def clear_shard_cache(cache_dir: Path) -> None:
    root = shards_dir(cache_dir)
    if root.is_dir():
        shutil.rmtree(root)
    build_info = ts_build_info_dir(cache_dir)
    if build_info.is_dir():
        shutil.rmtree(build_info)


def tsconfig_chain_digest(project: Path, tsconfig: Path | None) -> str:
    """Digest of the tsconfig chain (shard skip when unchanged and git clean)."""
    digest = hashlib.sha256()
    digest.update(shard_key(project).encode())
    digest.update(b"\0")
    if tsconfig is not None:
        for path, _data in walk_tsconfig_chain(tsconfig):
            digest.update(path.as_posix().encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def _normalize_manifest_entry(entry: dict[str, object]) -> dict[str, object] | None:
    tsconfig_digest = entry.get("tsconfig_digest")
    if not isinstance(tsconfig_digest, str) or not tsconfig_digest:
        return None
    return {"tsconfig_digest": tsconfig_digest}


def _parse_manifest_shards(data: dict[str, object]) -> dict[str, dict[str, object]]:
    raw_shards = data.get("shards")
    if not isinstance(raw_shards, dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for key, entry in raw_shards.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        normalized = _normalize_manifest_entry(entry)
        if normalized is not None:
            out[key] = normalized
    return out


def load_manifest_data(cache_dir: Path) -> tuple[dict[str, dict[str, object]], str | None]:
    """Return (shard entries, git_commit at last index) from manifest.json."""
    path = manifest_path(cache_dir)
    if not path.is_file():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, None
    if not isinstance(data, dict):
        return {}, None
    git_commit = data.get("git_commit")
    commit = git_commit if isinstance(git_commit, str) and git_commit else None
    return _parse_manifest_shards(data), commit


def load_shard_manifest(cache_dir: Path) -> dict[str, dict[str, object]]:
    return load_manifest_data(cache_dir)[0]


def save_shard_manifest(
    cache_dir: Path,
    shards: dict[str, dict[str, object]],
    *,
    project_root: Path | None = None,
) -> None:
    root = shards_dir(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    merged = {**load_shard_manifest(cache_dir), **shards}
    git_commit = None
    if project_root is not None and not index_unversioned(project_root):
        git_commit = git_head(project_root)
    payload: dict[str, object] = {
        "version": MANIFEST_VERSION,
        "shards": {key: dict(entry) for key, entry in sorted(merged.items())},
    }
    if git_commit:
        payload["git_commit"] = git_commit
    manifest_path(cache_dir).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def shard_entry_for_project(root: Path, project: Path) -> dict[str, object]:
    tsconfig = tsconfig_for_project(root, project)
    return {"tsconfig_digest": tsconfig_chain_digest(project, tsconfig)}


def shard_is_clean(
    root: Path,
    project: Path,
    entry: dict[str, object] | None,
    manifest_git_commit: str | None,
    delta: GitIndexDelta | None,
    *,
    exclude_globs: tuple[str, ...] = (),
) -> bool:
    """True when tsconfig unchanged and git reports no changes in this shard."""
    if entry is None or not manifest_git_commit or delta is None:
        return False
    if not git_is_ancestor(root, manifest_git_commit):
        return False
    tsconfig = tsconfig_for_project(root, project)
    current_digest = tsconfig_chain_digest(project, tsconfig)
    if entry.get("tsconfig_digest") != current_digest:
        return False
    return not delta.affects_shard(root, project, exclude_globs=exclude_globs)
