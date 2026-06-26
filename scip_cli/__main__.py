#!/usr/bin/env python3
"""CLI entry point for scip-cli."""
import argparse
import sys

from . import __version__
from .commands import refs, def_cmd, search, symbols, rdeps, members, skill


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

    # def
    def_parser = subparsers.add_parser("def", help="Find symbol definition")
    def_parser.add_argument("--type", dest="kind", help="Filter by kind (function, class, etc)")
    def_parser.add_argument("symbol", help="Symbol name")

    # search
    search_parser = subparsers.add_parser("search", help="Search symbols by pattern")
    search_parser.add_argument("--kind", help="Filter by kind")
    search_parser.add_argument("pattern", help="Search pattern")

    # symbols
    symbols_parser = subparsers.add_parser("symbols", help="List symbols in a file")
    symbols_parser.add_argument("file", help="File path or pattern")

    # rdeps
    rdeps_parser = subparsers.add_parser("rdeps", help="Find reverse dependencies of a file")
    rdeps_parser.add_argument("file", help="File path or pattern")

    # members
    members_parser = subparsers.add_parser("members", help="List members of a class/interface")
    members_parser.add_argument("symbol", help="Symbol name")

    # skill
    skill_parser = subparsers.add_parser("skill", help="Install or dump the scip-cli SKILL.md")
    skill_parser.add_argument("path", nargs="?", help="Optional file path to write to (creates dirs)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch to command handlers
    if args.command == "refs":
        refs.main(args)
    elif args.command == "def":
        def_cmd.main(args)
    elif args.command == "search":
        search.main(args)
    elif args.command == "symbols":
        symbols.main(args)
    elif args.command == "rdeps":
        rdeps.main(args)
    elif args.command == "members":
        members.main(args)
    elif args.command == "skill":
        skill.main(args)


if __name__ == "__main__":
    main()
