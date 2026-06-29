"""SCIP protobuf to SQLite conversion."""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

from ..scip_tool import ensure_scip_binary
from .constants import SCIP_INSTALL_URL
from .postprocess import postprocess_index
from .runners import run_subprocess

_scip_version_warned = False


def _scip_version(binary):
    result = run_subprocess([binary, "--version"], cwd=os.getcwd())
    if result.returncode != 0:
        return None
    match = re.search(r"v?(\d+)\.(\d+)\.(\d+)", result.stdout + result.stderr)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def resolve_scip_binary():
    """Locate the scip CLI used to convert protobuf indexes to SQLite."""
    return str(ensure_scip_binary())


def _warn_old_scip(binary):
    global _scip_version_warned
    if _scip_version_warned:
        return
    version = _scip_version(binary)
    if version and version < (0, 8, 0):
        _scip_version_warned = True
        print(
            f"Warning: {binary} {'.'.join(map(str, version))} is older than 0.8.0; "
            + "upgrade from "
            + f"{SCIP_INSTALL_URL} if indexing fails.",
            file=sys.stderr,
        )


def project_path_prefix(project: Path | str | None) -> str | None:
    if project is None:
        return None
    path = Path(project)
    if path == Path("."):
        return None
    return path.as_posix()


def prefix_document_paths(db_path: Path, prefix: str) -> None:
    """Rewrite document paths to be relative to the repository root."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE documents SET relative_path = ? || '/' || relative_path",
            (prefix,),
        )
        conn.commit()
    finally:
        conn.close()


def convert_scip_to_db(scip_path, db_path, *, document_path_prefix: Path | str | None = None):
    """Convert a SCIP protobuf file to a SQLite index at db_path."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    scip_binary = resolve_scip_binary()
    _warn_old_scip(scip_binary)

    result = run_subprocess(
        [scip_binary, "expt-convert", str(scip_path), "--output", db_path.name],
        cwd=str(db_path.parent),
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Failed to convert index")
    if not db_path.exists():
        raise RuntimeError("Failed to convert index")

    postprocess_index(db_path)
    prefix = project_path_prefix(document_path_prefix)
    if prefix is not None:
        prefix_document_paths(db_path, prefix)
