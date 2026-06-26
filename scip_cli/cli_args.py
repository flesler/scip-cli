"""Shared CLI argument helpers."""
import argparse


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
        help="Print symbol names only (one per line, for piping to def/refs/members)",
    )


def path_scope_from_args(args, project_root):
    from .paths import normalize_path_scope

    path_arg = getattr(args, "path", None)
    return normalize_path_scope(path_arg, project_root)
