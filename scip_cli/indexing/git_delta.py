"""Git commit-anchored change detection for incremental reindex."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..tsconfig import tsconfig_for_project
from .source_discovery import clear_git_index_cache, filter_tsconfig_candidates, path_matches_tsconfig_shard


def _run_git(root: Path, *args: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(root.resolve()), *args],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="surrogateescape").strip()


def git_head(root: Path) -> str | None:
    """Current HEAD commit, or None when not a git repo."""
    if not (root.resolve() / ".git").exists():
        return None
    return _run_git(root, "rev-parse", "HEAD")


def git_is_ancestor(root: Path, commit: str) -> bool:
    """True when ``commit`` is an ancestor of HEAD (safe after pull/rebase onto)."""
    proc = subprocess.run(
        ["git", "-C", str(root.resolve()), "merge-base", "--is-ancestor", commit, "HEAD"],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def clear_git_delta_cache() -> None:
    """Clear cached git delta path sets (tests and benchmarks)."""
    _git_index_delta_cached.cache_clear()
    clear_git_index_cache()


@dataclass(frozen=True)
class GitIndexDelta:
    """Paths changed since the manifest ``git_commit``.

    Git rename detection is disabled in diffs so ``git mv`` becomes delete old path +
    add new path (old path must be removed from the index).
    """

    added_or_modified: frozenset[str]
    removed: frozenset[str]

    @property
    def all_paths(self) -> frozenset[str]:
        return self.added_or_modified | self.removed

    def affects_shard(
        self,
        root: Path,
        project: Path,
        *,
        exclude_globs: tuple[str, ...] = (),
    ) -> bool:
        modified, removed = shard_dirty_paths(root, project, self, exclude_globs=exclude_globs)
        return bool(modified or removed)


def _git_paths_z(root: Path, *args: str) -> set[str]:
    proc = subprocess.run(
        ["git", "-C", str(root.resolve()), *args],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return set()
    return {part.decode("utf-8", errors="surrogateescape") for part in proc.stdout.split(b"\0") if part}


def _diff_paths(root: Path, *diff_args: str) -> tuple[set[str], set[str]]:
    """Return (added_or_modified, removed) from git diff.

    Uses ``--no-renames``: with rename folding, only the new path appears and the
    old path is omitted from ``--diff-filter=D``, so deleted symbols would linger.
    """
    common = ("diff", "--name-only", "-z", "--no-renames", *diff_args)
    added_or_modified = _git_paths_z(root, *common, "--diff-filter=ACMRTUXB")
    removed = _git_paths_z(root, *common, "--diff-filter=D")
    return added_or_modified, removed


@lru_cache(maxsize=8)
def _git_index_delta_cached(root: Path, since_commit: str) -> GitIndexDelta:
    """Accumulated changes since ``since_commit``: commits, staged, unstaged, untracked."""
    root = root.resolve()
    added: set[str] = set()
    removed: set[str] = set()

    head = _run_git(root, "rev-parse", "HEAD")
    if head and head != since_commit:
        committed_added, committed_removed = _diff_paths(root, f"{since_commit}..HEAD")
        added |= committed_added
        removed |= committed_removed

    work_added, work_removed = _diff_paths(root)
    added |= work_added
    removed |= work_removed

    staged_added, staged_removed = _diff_paths(root, "--cached")
    added |= staged_added
    removed |= staged_removed

    added |= _git_paths_z(root, "ls-files", "--others", "--exclude-standard", "-z")
    return GitIndexDelta(
        added_or_modified=frozenset(added),
        removed=frozenset(removed),
    )


def git_index_delta(root: Path, since_commit: str) -> GitIndexDelta:
    return _git_index_delta_cached(root.resolve(), since_commit)


def git_changed_paths(root: Path, since_commit: str) -> frozenset[str]:
    """All repo-relative paths touched since ``since_commit``."""
    return git_index_delta(root, since_commit).all_paths


def shard_dirty_paths(
    root: Path,
    project: Path,
    delta: GitIndexDelta,
    *,
    exclude_globs: tuple[str, ...] = (),
) -> tuple[frozenset[str], frozenset[str]]:
    """Return (added_or_modified, removed) repo-relative paths in ``project`` shard."""
    from ..exclude import path_matches_any_glob

    tsconfig = tsconfig_for_project(root, project)
    if tsconfig is None:
        return frozenset(), frozenset()

    modified = frozenset(
        path.relative_to(root).as_posix()
        for path in filter_tsconfig_candidates(root, tsconfig, sorted(delta.added_or_modified))
        if not exclude_globs or not path_matches_any_glob(path.relative_to(root).as_posix(), exclude_globs)
    )
    removed = frozenset(
        relative for relative in sorted(delta.removed) if path_matches_tsconfig_shard(root, tsconfig, relative)
    )
    return modified, removed


def shard_paths_from_delta(
    root: Path,
    project: Path,
    delta_paths: frozenset[str],
) -> set[str]:
    """Repo-relative source paths in ``project`` that appear in ``delta_paths`` (legacy helper)."""
    modified, _ = shard_dirty_paths(
        root,
        project,
        GitIndexDelta(added_or_modified=delta_paths, removed=frozenset()),
    )
    return set(modified)
