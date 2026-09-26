---
name: scip-cli-new-command
description: Read when adding or changing a scip-cli CLI subcommand.
---

# New or changed CLI command

User-facing reference lives in `scip_cli/SKILL.md` + `README.md` (must match `scip_cli/__main__.py` flags). Run `scip-cli skill` to verify dump.

## Checklist

1. **`scip_cli/commands/<name>.py`** — `main(args)`; thin handler. Use `session.setup()` for index DB unless the command is `reindex` / `skill`.
2. **`scip_cli/__main__.py`** — import; `add_parser`; wire `dispatch["<name>"] = <module>.main`.
3. **Shared flags** — reuse `scip_cli/cli_args.py` (`add_path_argument`, `add_limit_argument`, …) when siblings use them.
4. **SQL** — keep queries in `scip_cli/queries.py` or `scip_cli/analyze/`, not fat command modules.
5. **Docs** — quick-guide row + `### <name>` section in `scip_cli/SKILL.md`; bullet in README § Commands.
6. **Tests** — `tests/test_e2e.py` (or `test_e2e_analyze_patterns.py` for analyze-only); add `scip_cli.commands.<name>.setup` to `tests/e2e_harness.py` `COMMAND_SETUP_PATHS`.
7. **Verify** — Read `.cursor/skills/test/SKILL.md`; run narrowed pytest then e2e loop.

## Patterns

- **Read-only DB:** `db, project_root = setup()` in `try` / `finally: db.close()`. Connection already has `configure_read_connection` via `get_db`.
- **Errors:** raise `RuntimeError` or let `sqlite3.Error` bubble — `__main__.main` maps them to stderr + exit code.
- **Output:** stdout = records; stderr = warnings (match existing commands).

## Map

|Concern|Path|
|---|---|
|Entry / argparse|`scip_cli/__main__.py`|
|Handlers|`scip_cli/commands/`|
|Index open|`scip_cli/session.py`, `scip_cli/indexing/core.py`|
|User skill install|`scip-cli skill <path>` copies `scip_cli/SKILL.md`|
