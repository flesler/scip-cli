"""Download and locate the scip CLI binary."""

from __future__ import annotations

import json
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

SCIP_RELEASES_API = "https://api.github.com/repos/scip-code/scip/releases/latest"
SCIP_RELEASE_FALLBACK_TAG = "v0.8.1"
MIN_SCIP_VERSION = (0, 8, 0)


def _latest_release_tag() -> str:
    """Return the latest scip release tag from GitHub."""
    try:
        request = urlopen(SCIP_RELEASES_API, timeout=30)
        data = json.loads(request.read().decode("utf-8"))
        tag = data.get("tag_name")
        if isinstance(tag, str) and tag:
            return tag
    except Exception:
        pass
    return SCIP_RELEASE_FALLBACK_TAG


def _release_base(tag: str) -> str:
    return f"https://github.com/scip-code/scip/releases/download/{tag}"


def _platform_archive() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        arch = "amd64"
    elif machine in {"arm64", "aarch64"}:
        arch = "arm64"
    else:
        raise RuntimeError(f"Unsupported platform for auto-install: {system}/{machine}")
    if system == "darwin":
        return f"scip-darwin-{arch}.tar.gz"
    if system == "linux":
        return f"scip-linux-{arch}.tar.gz"
    raise RuntimeError(f"Unsupported platform for auto-install: {system}")


def cached_scip_path() -> Path:
    return Path.home() / ".cache" / "scip-cli" / "bin" / "scip"


def parse_scip_version(output: str) -> tuple[int, int, int] | None:
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", output)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _scip_version_at(path: Path) -> tuple[int, int, int] | None:
    try:
        result = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return parse_scip_version(result.stdout + result.stderr)


def _path_scip_binary() -> Path | None:
    found = shutil.which("scip")
    if not found:
        return None
    return Path(found)


def _download_scip_binary(dest: Path) -> None:
    release_tag = _latest_release_tag()
    archive_name = _platform_archive()
    url = f"{_release_base(release_tag)}/{archive_name}"
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading scip {release_tag} from GitHub releases...", file=sys.stderr)

    with urlopen(url, timeout=120) as response:
        data = response.read()

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / archive_name
        archive_path.write_bytes(data)
        with tarfile.open(archive_path, "r:gz") as tar:
            members = [m for m in tar.getmembers() if m.name == "scip" or m.name.endswith("/scip")]
            if not members:
                raise RuntimeError("scip archive did not contain a scip binary")
            tar.extract(members[0], path=tmpdir)
            extracted = Path(tmpdir) / members[0].name
            shutil.move(str(extracted), dest)

    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_scip_binary() -> Path:
    """Return a scip binary path, downloading to the cache if needed."""
    cached = cached_scip_path()
    if cached.is_file():
        version = _scip_version_at(cached)
        if version and version >= MIN_SCIP_VERSION:
            return cached

    path_binary = _path_scip_binary()
    if path_binary is not None:
        version = _scip_version_at(path_binary)
        if version and version >= MIN_SCIP_VERSION:
            return path_binary
        if version is None and path_binary.is_file():
            print(
                "Warning: 'scip' on PATH is not the SCIP indexer "
                "(brew install scip installs an unrelated solver). "
                "Downloading the correct binary...",
                file=sys.stderr,
            )

    if cached.is_file():
        cached.unlink()

    try:
        _download_scip_binary(cached)
    except Exception as exc:
        raise RuntimeError(
            "scip CLI not found and auto-download failed. "
            f"Install manually from https://github.com/scip-code/scip/releases. "
            f"Reason: {exc}"
        ) from exc

    version = _scip_version_at(cached)
    if not version or version < MIN_SCIP_VERSION:
        raise RuntimeError("Downloaded scip binary failed version check")

    return cached
