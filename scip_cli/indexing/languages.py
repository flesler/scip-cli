"""Per-language single-project indexers."""

from __future__ import annotations

from pathlib import Path

from .convert import convert_scip_to_db
from .orchestrate import project_label
from .runners import run_indexer_with_fallback


def _project_cwd(root: Path, project: Path) -> Path:
    return root if project == Path(".") else root / project


def index_python_project(root, project, work_dir, env, *, output_db=None):
    """Index one Python package directory into work_dir/index.db (or output_db when set)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = project_label(Path(project))
    cwd = _project_cwd(Path(root), Path(project))
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    result = run_indexer_with_fallback(
        "scip-python",
        ["index", ".", "--output", str(part_scip)],
        str(cwd),
        env=env,
        npx_package="@sourcegraph/scip-python",
    )
    if result.returncode != 0:
        return label, None, result.stderr.strip() or "indexing failed"
    try:
        convert_scip_to_db(part_scip, db_path, document_path_prefix=project)
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None


def index_golang_module(root, module, work_dir, env, *, output_db=None):
    """Index one Go module directory into work_dir/index.db (or output_db when set)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = project_label(Path(module))
    cwd = _project_cwd(Path(root), Path(module))
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    result = run_indexer_with_fallback(
        "scip-go",
        ["--output", str(part_scip)],
        str(cwd),
        env=env,
        go_package="github.com/scip-code/scip-go/cmd/scip-go",
    )
    if result.returncode != 0:
        return label, None, result.stderr.strip() or "indexing failed"
    try:
        convert_scip_to_db(part_scip, db_path, document_path_prefix=module)
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None


def index_rust_crate(root, crate, work_dir, env, *, output_db=None):
    """Index one Rust crate directory into work_dir/index.db (or output_db when set)."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = project_label(Path(crate))
    cwd = _project_cwd(Path(root), Path(crate))
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    result = run_indexer_with_fallback(
        "rust-analyzer",
        ["scip", str(cwd), "--output", str(part_scip)],
        str(cwd),
        env=env,
        rustup_component="rust-analyzer",
    )
    if result.returncode != 0:
        return label, None, result.stderr.strip() or "indexing failed"
    try:
        convert_scip_to_db(part_scip, db_path, document_path_prefix=crate)
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None
