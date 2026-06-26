"""CLI entry point for scip-cli."""
import argparse
import logging
import os
import sys

from . import __version__
from .lib import SymbolKind
from .commands import refs, def_cmd, search, symbols, rdeps, members, skill, reindex

# Set up debug logging based on SCIP_CLI_DEBUG env var
if os.environ.get("SCIP_CLI_DEBUG"):
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(name)s: %(message)s",
        stream=sys.stderr
    )
else:
    logging.disable(logging.DEBUG)


def main():
    parser = argparse.ArgumentParser(
        prog="scip-cli",
        description="Fast code intelligence via SCIP indexes"
    )
    parser.add_argument("--version", action="version", version=f"scip-cli {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # refs
    refs_parser = subparsers.add_parser("refs", help="Find references to a symbol")
    refs_parser.add_argument("symbol", help="Symbol name")
    refs_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    # def
    def_parser = subparsers.add_parser("def", help="Find symbol definition")
    def_parser.add_argument("--kind", choices=SymbolKind.filterable_values(), help="Filter by kind")
    def_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    def_parser.add_argument("symbol", help="Symbol name")

    # search
    search_parser = subparsers.add_parser("search", help="Search symbols by pattern")
    search_parser.add_argument("--kind", choices=SymbolKind.filterable_values(), help="Filter by kind")
    search_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    search_parser.add_argument("pattern", help="Search pattern")

    # symbols
    symbols_parser = subparsers.add_parser("symbols", help="List symbols in a file")
    symbols_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    symbols_parser.add_argument("file", help="File path or pattern")

    # rdeps
    rdeps_parser = subparsers.add_parser("rdeps", help="Find reverse dependencies of a file")
    rdeps_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    rdeps_parser.add_argument("file", help="File path or pattern")

    # members
    members_parser = subparsers.add_parser("members", help="List members of a class/interface")
    members_parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    members_parser.add_argument("symbol", help="Symbol name")

    # skill
    skill_parser = subparsers.add_parser("skill", help="Install or dump the scip-cli SKILL.md")
    skill_parser.add_argument("path", nargs="?", help="Optional file path to write to (creates dirs)")

    # reindex
    subparsers.add_parser("reindex", help="Force re-indexing of the current project")

    args = parser.parse_args()

    # Dispatch to command handlers
    dispatch = {
        "refs": refs.main,
        "def": def_cmd.main,
        "search": search.main,
        "symbols": symbols.main,
        "rdeps": rdeps.main,
        "members": members.main,
        "skill": skill.main,
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


if __name__ == "__main__":
    main()
