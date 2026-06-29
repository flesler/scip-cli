"""Subprocess execution and indexer install fallbacks."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ..debug import debug_log
from .constants import INDEX_TIMEOUT


def _run_subprocess(cmd, cwd, env=None):
    """Run subprocess with timeout; raise RuntimeError on timeout."""
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=INDEX_TIMEOUT,
        )
    except subprocess.TimeoutExpired as err:
        print(f"Error: Command timed out after {INDEX_TIMEOUT} seconds", file=sys.stderr)
        raise RuntimeError("Indexing command timed out") from err


def _run_indexer_command(binary, args, cwd, env):
    """Try to run an indexer binary. Returns (success, result)."""
    try:
        result = _run_subprocess([binary, *args], cwd, env=env)
        if result.returncode == 0:
            return True, result
        if "not found" in result.stderr.lower():
            return False, result
        return True, result  # Command ran but failed - return the error
    except FileNotFoundError:
        return False, None


def _install_via_npx(package, version, args, cwd, env):
    """Install and run via npx."""
    npx_spec = f"{package}@~{version}" if version else package
    debug_log("Tool not found, trying npx (will download automatically)...")
    return _run_subprocess(["npx", "-y", npx_spec, *args], cwd, env=env)


def _install_via_go_install(package, binary, args, cwd, env, *, version: str | None = None):
    """Install via go install and run from ~/go/bin."""
    go_bin_dir = Path.home() / "go" / "bin"
    go_env = env.copy()
    go_env["PATH"] = f"{go_bin_dir}:{go_env.get('PATH', '')}"

    go_binary = go_bin_dir / binary
    if go_binary.exists():
        debug_log(f"Found {binary} at {go_binary}")
        return _run_subprocess([str(go_binary), *args], cwd, env=go_env)

    install_spec = f"{package}@v{version}" if version else f"{package}@latest"
    debug_log(f"Tool not found, installing via go install {install_spec}...")
    install_result = _run_subprocess(
        ["go", "install", install_spec],
        cwd,
        env=go_env,
    )
    if install_result.returncode != 0:
        raise RuntimeError(f"Failed to install {binary} via go install: {install_result.stderr}")
    debug_log(f"{binary} installed, retrying...")
    return _run_subprocess([str(go_binary), *args], cwd, env=go_env)


def _install_via_rustup(component, binary, args, cwd, env):
    """Install via rustup component add and run."""
    debug_log(f"Tool not found, installing rustup component {component}...")
    install_result = _run_subprocess(
        ["rustup", "component", "add", component],
        cwd,
        env=env,
    )
    if install_result.returncode != 0:
        raise RuntimeError(f"Failed to install {component} via rustup: {install_result.stderr}")
    debug_log(f"{binary} installed via rustup, retrying...")
    return _run_subprocess([binary, *args], cwd, env=env)


def run_indexer_with_fallback(
    binary,
    args,
    cwd,
    env=None,
    npx_package=None,
    npx_version=None,
    go_package=None,
    go_version=None,
    rustup_component=None,
) -> subprocess.CompletedProcess[str]:
    """Run an indexer, installing it automatically if not found."""
    run_env = env if env is not None else os.environ.copy()

    success, result = _run_indexer_command(binary, args, cwd, run_env)
    if success:
        assert result is not None
        return result

    if go_package:
        return _install_via_go_install(go_package, binary, args, cwd, run_env, version=go_version)
    if rustup_component:
        return _install_via_rustup(rustup_component, binary, args, cwd, run_env)
    if npx_package:
        return _install_via_npx(npx_package, npx_version, args, cwd, run_env)

    if result is None:
        raise RuntimeError(f"Binary '{binary}' not found and no fallback available")
    return result
