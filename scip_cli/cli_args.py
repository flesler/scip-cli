"""Shared CLI argument helpers."""

import argparse


def positive_int(min_value: int = 1):
    """Argparse type: integer >= min_value."""

    def _check(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc
        if parsed < min_value:
            raise argparse.ArgumentTypeError(f"must be >= {min_value}")
        return parsed

    return _check


def add_limit_argument(parser: argparse.ArgumentParser, *, default: int, help_suffix: str = "results") -> None:
    parser.add_argument(
        "--limit",
        type=positive_int(),
        default=default,
        help=f"Max {help_suffix} (default: {default})",
    )


def add_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--path",
        metavar="PATH",
        help="Limit results to a file or directory under the project root",
    )


def add_paths_only_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--paths-only",
        action="store_true",
        help="Print unique file paths only (one per line, for piping to symbols/rdeps)",
    )


def add_names_only_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--names-only",
        action="store_true",
        help="Print symbol names only (one per line, for piping to code/refs/members)",
    )


def path_scope_from_args(args, project_root):
    from .paths import normalize_path_scope

    path_arg = getattr(args, "path", None)
    return normalize_path_scope(path_arg, project_root)
