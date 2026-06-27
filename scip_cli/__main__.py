"""CLI entry point for scip-cli."""

import argparse
import logging
import os
import shutil
import sqlite3
import sys

from . import __version__
from .cli_args import add_limit_argument, add_names_only_argument, add_path_argument, add_paths_only_argument
from .commands import analyze, code, members, rdeps, refs, reindex, search, skill, symbols
from .symbols import SymbolKind

# Set up debug logging based on SCIP_CLI_DEBUG env var
if os.environ.get("SCIP_CLI_DEBUG"):
    logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s", stream=sys.stderr)
else:
    logging.disable(logging.DEBUG)


def main():
    parser = argparse.ArgumentParser(
        prog="scip-cli",
        description="Fast code intelligence via SCIP indexes",
        epilog="AI agents: run 'scip-cli skill' for quick reference",
    )
    parser.add_argument("--version", action="store_true", help="Show version and install path")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # refs
    refs_parser = subparsers.add_parser("refs", help="Find references to a symbol")
    refs_parser.add_argument("symbol", nargs="+", help="Symbol name(s)")
    add_limit_argument(refs_parser, default=10, help_suffix="reference lines")
    add_path_argument(refs_parser)
    add_paths_only_argument(refs_parser)

    # code
    code_parser = subparsers.add_parser("code", help="Find symbol definition")
    code_parser.add_argument("--kind", choices=SymbolKind.filterable_values(), help="Filter by kind")
    add_limit_argument(code_parser, default=10, help_suffix="matching symbols")
    add_path_argument(code_parser)
    code_parser.add_argument(
        "--max-lines",
        type=int,
        default=None,
        metavar="N",
        help=("Max source lines per definition body (default: 80, env SCIP_CLI_MAX_DEF_LINES). Use 0 for unlimited."),
    )
    code_parser.add_argument(
        "--full",
        action="store_true",
        help="Show full definition (equivalent to --max-lines 0)",
    )
    code_parser.add_argument(
        "--offset",
        type=int,
        default=0,
        metavar="N",
        help="Skip first N lines of definition (use with --max-lines for pagination)",
    )
    code_parser.add_argument(
        "--snippet",
        action="store_true",
        help="Show only file, line range, and first line (not full body)",
    )
    code_parser.add_argument(
        "--line-numbers",
        "-n",
        action="store_true",
        help="Prefix each line with its line number",
    )
    code_parser.add_argument("symbol", nargs="+", help="Symbol name(s)")

    # search
    search_parser = subparsers.add_parser("search", help="Search symbols by pattern")
    search_parser.add_argument("--kind", choices=SymbolKind.filterable_values(), help="Filter by kind")
    add_limit_argument(search_parser, default=10)
    add_path_argument(search_parser)
    add_names_only_argument(search_parser)
    add_paths_only_argument(search_parser)
    search_parser.add_argument("pattern", nargs="+", help="Search pattern(s), matched with OR logic")

    # symbols
    symbols_parser = subparsers.add_parser("symbols", help="List symbols in a file")
    add_limit_argument(symbols_parser, default=10, help_suffix="symbols")
    add_path_argument(symbols_parser)
    symbols_parser.add_argument("file", help="File path or pattern")

    # rdeps
    rdeps_parser = subparsers.add_parser("rdeps", help="Find reverse dependencies of a file")
    add_limit_argument(rdeps_parser, default=10, help_suffix="importer files")
    add_path_argument(rdeps_parser)
    rdeps_parser.add_argument("file", help="File path or pattern")

    # members
    members_parser = subparsers.add_parser("members", help="List members of a class/interface")
    add_limit_argument(members_parser, default=10, help_suffix="members")
    add_path_argument(members_parser)
    add_names_only_argument(members_parser)
    members_parser.add_argument("symbol", help="Symbol name")

    # skill
    skill_parser = subparsers.add_parser("skill", help="Install or dump the scip-cli SKILL.md")
    skill_parser.add_argument("path", nargs="?", help="Optional file path to write to (creates dirs)")

    # analyze
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Run SQL-based analysis (project, file, or symbol)",
    )
    analyze_parser.add_argument(
        "target",
        nargs="?",
        help="Omit for project-wide; directory for scoped project + per-file; file or symbol for focused checks",
    )
    add_path_argument(analyze_parser)
    add_limit_argument(analyze_parser, default=20, help_suffix="rows per section")
    analyze_parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include tests/, *.test.*, *.spec.* paths in project-wide analyze (default: skip)",
    )

    # reindex
    reindex_parser = subparsers.add_parser("reindex", help="Force re-indexing of the current project")
    reindex_parser.add_argument(
        "--path",
        action="append",
        metavar="PATH",
        help="Index only tsconfig projects under PATH (repeatable; persisted until full reindex)",
    )

    args = parser.parse_args()

    if args.version:
        exe = shutil.which("scip-cli") or sys.argv[0]
        print(f"scip-cli {__version__} ({exe})")
        return

    # Dispatch to command handlers
    dispatch = {
        "refs": refs.main,
        "code": code.main,
        "search": search.main,
        "symbols": symbols.main,
        "rdeps": rdeps.main,
        "members": members.main,
        "skill": skill.main,
        "analyze": analyze.main,
        "reindex": reindex.main,
    }

    handler = dispatch.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(1)

    try:
        handler(args)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"System error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
