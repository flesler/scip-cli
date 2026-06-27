"""analyze command — run SQL-based analysis dashboards."""

from ..analyze import file as file_checks
from ..analyze import project as project_checks
from ..analyze import symbol as symbol_checks
from ..session import resolve_one_file, resolve_one_symbol, setup


def _looks_like_file(target: str) -> bool:
    return "." in target


def _print_sections(sections: list[tuple[str, list[str]]]) -> None:
    for title, lines in sections:
        print(f"=== {title} ===")
        for line in lines:
            print(line)
        print()


def main(args):
    """Run project, file, or symbol analysis based on optional target."""
    db, _project_root = setup()
    try:
        limit = args.limit
        target = getattr(args, "target", None)

        if target is None:
            sections = project_checks.run_all(db, limit=limit)
        elif _looks_like_file(target):
            path = resolve_one_file(db, target, path_scope=None)
            sections = file_checks.run_all(db, path, limit=limit)
        else:
            symbol_id, _symbol_str, _display = resolve_one_symbol(db, target)
            sections = symbol_checks.run_all(db, symbol_id, limit=limit)

        _print_sections(sections)
    finally:
        db.close()
