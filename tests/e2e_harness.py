"""Run scip-cli commands in-process against the shared indexed fixture."""

from __future__ import annotations

import contextlib
import sqlite3
import sys
from collections import namedtuple
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scip_cli.sql import configure_read_connection

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sample-project"

COMMAND_SETUP_PATHS = (
    "scip_cli.commands.analyze.setup",
    "scip_cli.commands.code.setup",
    "scip_cli.commands.deps.setup",
    "scip_cli.commands.members.setup",
    "scip_cli.commands.refs.setup",
    "scip_cli.commands.rdeps.setup",
    "scip_cli.commands.search.setup",
    "scip_cli.commands.symbols.setup",
)

CliResult = namedtuple("CliResult", ("returncode", "stdout", "stderr"))


@dataclass(frozen=True)
class IndexedFixture:
    root: Path
    db_path: Path


def index_fixture_project(root: Path) -> Path:
    """Index the copied fixture with real scip-typescript + scip convert."""
    from scip_cli.cache import find_db
    from scip_cli.indexing import get_db

    conn = get_db(root)
    conn.close()
    db_path = find_db(root)
    if not db_path or not db_path.is_file():
        raise RuntimeError(f"fixture indexing produced no index.db under {root}")
    return db_path


def open_index_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    configure_read_connection(conn)
    return conn


def run_cli(argv: list[str], fixture: IndexedFixture | None = None) -> CliResult:
    """Invoke scip-cli __main__ with optional patched session.setup."""
    from scip_cli import __main__

    out_buf, err_buf = StringIO(), StringIO()
    exit_code = 0

    def fake_setup():
        if fixture is None:
            raise RuntimeError("indexed fixture required for this command")
        return open_index_db(fixture.db_path), fixture.root

    stack = contextlib.ExitStack()
    if fixture is not None:
        for path in COMMAND_SETUP_PATHS:
            stack.enter_context(patch(path, fake_setup))
    stack.enter_context(contextlib.redirect_stdout(out_buf))
    stack.enter_context(contextlib.redirect_stderr(err_buf))

    with stack:
        old_argv = sys.argv
        sys.argv = ["scip-cli", *argv]
        try:
            __main__.main()
        except SystemExit as exc:
            code = exc.code
            if code is None:
                exit_code = 0
            elif isinstance(code, int):
                exit_code = code
            else:
                exit_code = 1
        finally:
            sys.argv = old_argv

    return CliResult(exit_code, out_buf.getvalue(), err_buf.getvalue())


class CliRunner:
    """Shortcut for e2e tests: cli.run('code', 'greet')."""

    def __init__(self, fixture: IndexedFixture) -> None:
        self.fixture = fixture

    def run(self, *argv: str) -> CliResult:
        return run_cli(list(argv), self.fixture)
