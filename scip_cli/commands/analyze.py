"""analyze command — run SQL-based analysis dashboards."""

from ..analyze import file as file_checks
from ..analyze import project as project_checks
from ..analyze import symbol as symbol_checks
from ..cli_args import path_scope_from_args
from ..session import resolve_one_file, resolve_one_symbol, setup
from ..targets import looks_like_file_target


def _print_sections(sections: list[tuple[str, list[str]]]) -> None:
    for title, lines in sections:
        print(f"=== {title} ===")
        for line in lines:
            print(line)
        print()


def main(args):
    """Run project, file, or symbol analysis based on optional target."""
    db, project_root = setup()
    try:
        path_scope = path_scope_from_args(args, project_root)
        limit = args.limit
        target = getattr(args, "target", None)

        if target is None:
            sections = project_checks.run_all(db, limit=limit)
        elif looks_like_file_target(target):
            path = resolve_one_file(db, target, path_scope=path_scope)
            sections = file_checks.run_all(db, path, limit=limit)
        else:
            symbol_id, _symbol_str, _display = resolve_one_symbol(db, target, path_scope=path_scope)
            sections = symbol_checks.run_all(db, symbol_id, limit=limit)

        _print_sections(sections)
    finally:
        db.close()
