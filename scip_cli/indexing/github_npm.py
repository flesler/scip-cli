"""Install and run npm packages from github: specs (source-only, no prebuilt dist).

TODO: Remove this module and all github: fork install wiring (runners branch,
constants note, fallback tests) once SCIP_TYPESCRIPT_NPX_PACKAGE switches back
to upstream @sourcegraph/scip-typescript on npm.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ..debug import debug_log
from .constants import INDEX_TIMEOUT

# TODO: Remove github_npm fork install boilerplate when switching back to upstream npm.
_GITHUB_NPM_TOOL_ROOT = Path.home() / ".cache" / "scip-cli" / "tools" / "github-npm"
_INSTALL_LOCK = ".install.lock"
_SPEC_STAMP = ".spec"
_REPO_DIR = "repo"
_ENTRY = Path("dist") / "src" / "main.js"
_GITHUB_SPEC = re.compile(r"^github:(?P<repo>[^#]+)(?:#(?P<ref>.+))?$")


def _github_npm_cache_dir(spec: str) -> Path:
    digest = hashlib.sha256(spec.encode()).hexdigest()[:20]
    return _GITHUB_NPM_TOOL_ROOT / digest


def _parse_github_spec(spec: str) -> tuple[str, str]:
    match = _GITHUB_SPEC.match(spec)
    if not match:
        raise ValueError(f"expected github:owner/repo#ref npm spec, got {spec!r}")
    repo = match.group("repo").removesuffix(".git")
    ref = match.group("ref") or "HEAD"
    return f"https://github.com/{repo}.git", ref


@contextlib.contextmanager
def _install_lock(cache_dir: Path):
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / _INSTALL_LOCK
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _run_checked(cmd: list[str], cwd: Path, env: dict[str, str], *, timeout: int | None = None):
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout or INDEX_TIMEOUT * 2,
        )
    except subprocess.TimeoutExpired as err:
        print(f"Error: Command timed out: {' '.join(cmd)}", file=sys.stderr)
        raise RuntimeError("github npm install/build timed out") from err


def _failure(label: str, result: subprocess.CompletedProcess[str]) -> RuntimeError:
    detail = (result.stderr or result.stdout or "").strip()
    return RuntimeError(f"{label}: {detail}")


def ensure_github_npm_package(spec: str, env: dict[str, str]) -> Path:
    """Clone github spec, npm install --ignore-scripts, build; return CLI entry."""
    if not spec.startswith("github:"):
        raise ValueError(f"expected github: npm spec, got {spec!r}")

    cache_dir = _github_npm_cache_dir(spec)
    repo_dir = cache_dir / _REPO_DIR
    entry = repo_dir / _ENTRY
    stamp = cache_dir / _SPEC_STAMP

    if entry.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8") == spec:
        return entry

    npm = shutil.which("npm", path=env.get("PATH"))
    git = shutil.which("git", path=env.get("PATH"))
    if not npm:
        raise RuntimeError("npm not found on PATH (required for github: scip-typescript install)")
    if not git:
        raise RuntimeError("git not found on PATH (required for github: scip-typescript install)")

    git_url, git_ref = _parse_github_spec(spec)
    install_env = {**env, "NODE_ENV": "development"}

    with _install_lock(cache_dir):
        if entry.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8") == spec:
            return entry

        if repo_dir.exists():
            shutil.rmtree(repo_dir)

        debug_log(f"Cloning {git_url} ({git_ref}) into {repo_dir}...")
        clone = _run_checked(
            ["git", "clone", "--depth", "1", "--branch", git_ref, git_url, str(repo_dir)],
            cwd=cache_dir,
            env=install_env,
            timeout=INDEX_TIMEOUT * 2,
        )
        if clone.returncode != 0:
            raise _failure(f"git clone failed for {spec}", clone)

        debug_log(f"npm install --ignore-scripts in {repo_dir}...")
        install = _run_checked(
            [npm, "install", "--ignore-scripts"],
            cwd=repo_dir,
            env=install_env,
        )
        if install.returncode != 0:
            raise _failure(f"npm install failed for {spec}", install)

        debug_log(f"npm run build in {repo_dir}...")
        build = _run_checked([npm, "run", "build"], cwd=repo_dir, env=install_env)
        if build.returncode != 0:
            raise _failure(f"npm run build failed for {spec}", build)

        pkg_json = repo_dir / "dist" / "package.json"
        if not pkg_json.is_file() and (repo_dir / "package.json").is_file():
            shutil.copy2(repo_dir / "package.json", pkg_json)

        if not entry.is_file():
            raise RuntimeError(f"build did not produce {entry}")

        stamp.write_text(spec, encoding="utf-8")
        return entry


def install_via_github_npm(spec: str, args: list[str], cwd: str | Path, env: dict[str, str]):
    """Run scip-typescript from a cached github: install."""
    entry = ensure_github_npm_package(spec, env)
    node = shutil.which("node", path=env.get("PATH")) or "node"
    return _run_checked([node, str(entry), *args], Path(cwd), env, timeout=INDEX_TIMEOUT)
