"""Run scip-typescript for one or more tsconfig projects."""

from __future__ import annotations

import json
from pathlib import Path

from ..exclude import filter_excluded_paths
from ..tsconfig import allow_js_overlay, tsconfig_for_project
from .constants import SCIP_TYPESCRIPT_NPX_PACKAGE
from .convert import convert_scip_to_db
from .orchestrate import project_batch_label
from .performance import phase
from .runners import indexer_failure_message, run_indexer_with_fallback


def typescript_index_args(
    root,
    output_scip,
    projects,
    *,
    index_files: tuple[str, ...] | None = None,
):
    args = ["index", "--output", str(output_scip)]
    root = Path(root)
    if not (root / "tsconfig.json").exists():
        args.insert(1, "--infer-tsconfig")
    args.extend(str(project) for project in projects)
    if index_files:
        for relative in index_files:
            args.extend(["--files", relative])
    return args


def _overlay_filename(project: Path, index: int) -> str:
    stem = project.as_posix().replace("/", "__").replace("\\", "__")
    return f"allowjs-{index}-{stem}.json"


def materialize_allow_js_projects(root: Path, projects: list[Path], work_dir: Path) -> list[Path]:
    """Rewrite projects to temp tsconfigs that include JS when allowJs is set."""
    root = Path(root).resolve()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    materialized: list[Path] = []
    for index, project in enumerate(projects):
        tsconfig = tsconfig_for_project(root, project)
        if tsconfig is None:
            materialized.append(project)
            continue
        overlay = allow_js_overlay(tsconfig)
        if overlay is None:
            materialized.append(project)
            continue
        dest = work_dir / _overlay_filename(project, index)
        dest.write_text(json.dumps(overlay, indent=2) + "\n", encoding="utf-8")
        materialized.append(dest)
    return materialized


def index_ts_projects(
    root,
    projects,
    work_dir,
    env,
    *,
    output_db: Path | None = None,
    exclude_globs: tuple[str, ...] = (),
    index_files: tuple[str, ...] | None = None,
):
    """Index one or more TypeScript projects into work_dir/index.db (or output_db when set)."""
    root = Path(root)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    label = project_batch_label(projects)
    part_scip = work_dir / "index.scip"
    db_path = Path(output_db) if output_db is not None else work_dir / "index.db"
    index_projects = materialize_allow_js_projects(root, projects, work_dir)
    scoped_files = index_files
    if index_files:
        scoped_files = filter_excluded_paths(index_files, exclude_globs)
        if not scoped_files:
            return label, None, None
    index_args = typescript_index_args(
        root,
        part_scip,
        index_projects,
        index_files=scoped_files,
    )
    with phase("scip_typescript"):
        result = run_indexer_with_fallback(
            "scip-typescript",
            index_args,
            str(root),
            env=env,
            npx_package=SCIP_TYPESCRIPT_NPX_PACKAGE,
        )
    if result.returncode != 0:
        return label, None, indexer_failure_message(result)
    try:
        with phase("scip_convert"):
            convert_scip_to_db(
                part_scip,
                db_path,
                exclude_globs=exclude_globs,
                skip_postprocess=bool(index_files),
            )
    finally:
        part_scip.unlink(missing_ok=True)
    return label, db_path, None
