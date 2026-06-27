"""analyze command — run SQL-based analysis dashboards."""

import sys

from ..analyze import file as file_checks
from ..analyze import project as project_checks
from ..analyze import symbol as symbol_checks
from ..analyze.common import section
from ..analyze.targets import MAX_DIR_FILES, list_dir_files, resolve_analyze_target
from ..cli_args import path_scope_from_args
from ..session import resolve_one_symbol, setup


def _print_sections(sections: list[tuple[str, list[str]]]) -> None:
    for title, lines in sections:
        print(f"=== {title} ===")
        for line in lines:
            print(line)
        print()


def _project_sections(db, *, limit: int, include_tests: bool, scope: str | None) -> list[tuple[str, list[str]]]:
    return project_checks.run_all(db, limit=limit, include_tests=include_tests, scope=scope)


def _file_sections(db, path: str, *, limit: int) -> list[tuple[str, list[str]]]:
    return file_checks.run_all(db, path, limit=limit)


def _dir_sections(
    db,
    scope: str,
    *,
    limit: int,
    include_tests: bool,
) -> list[tuple[str, list[str]]]:
    sections = _project_sections(db, limit=limit, include_tests=include_tests, scope=scope)
    files = list_dir_files(db, scope, include_tests=include_tests)
    total = len(files)
    if total > MAX_DIR_FILES:
        print(
            f"Note: {total} indexed files under {scope}; showing first {MAX_DIR_FILES} "
            f"(analyze one file for full detail)",
            file=sys.stderr,
        )
        files = files[:MAX_DIR_FILES]
    if files:
        sections.append(section(f"Files in {scope}", [f"{len(files)} shown of {total} indexed"]))
    for path in files:
        sections.extend(file_checks.run_all_sections_only(db, path, limit=limit))
    return sections


def main(args):
    """Run project, directory, file, or symbol analysis from one optional target."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        limit = args.limit
        include_tests = getattr(args, "include_tests", False)
        target = getattr(args, "target", None)

        if target is None:
            if path_scope:
                print(
                    f"Error: use analyze {path_scope!r} for directory scope (not analyze --path)",
                    file=sys.stderr,
                )
                sys.exit(1)
            sections = _project_sections(db, limit=limit, include_tests=include_tests, scope=None)
        else:
            resolved = resolve_analyze_target(db, target, project_root, path_scope)
            if resolved.kind == "dir":
                sections = _dir_sections(
                    db,
                    resolved.scope,
                    limit=limit,
                    include_tests=include_tests,
                )
            elif resolved.kind == "file":
                sections = _project_sections(
                    db,
                    limit=limit,
                    include_tests=include_tests,
                    scope=resolved.scope,
                )
                sections.extend(_file_sections(db, resolved.scope, limit=limit))
            else:
                symbol_id, _symbol_str, _display = resolve_one_symbol(
                    db,
                    resolved.symbol_name,
                    path_scope=path_scope,
                )
                sections = symbol_checks.run_all(db, symbol_id, limit=limit)

        _print_sections(sections)
    finally:
        if db is not None:
            db.close()
