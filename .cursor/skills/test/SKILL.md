---
name: scip-cli-test
description: Read when running or writing scip-cli tests (pytest, e2e, CI parity).
---

# scip-cli tests

Repo root only. Bootstrap: `.cursor/rules/agent.mdc` (editable install, Node for fixture index).

## Pick a suite

|Goal|Command|
|---|---|
|Pre-commit / CI parity|`scripts/test.sh`|
|Full|`pytest`|
|CLI + fixture index|`pytest tests/test_e2e.py tests/test_e2e_analyze_patterns.py`|
|One class / test|`pytest tests/test_e2e.py::TestQuery -q`|
|Analyze unit / graph|`pytest tests/test_analyze_graph.py tests/test_analyze.py`|
|SQL perf (not correctness)|`scripts/bench.sh` — see `.cursor/skills/sql-bench/SKILL.md`|

`scripts/test.sh` uses `.venv/bin/{ruff,basedpyright,pytest}`; create venv + `pip install -e ".[dev]"` if missing.

## E2e rules

- In-process only: `tests/e2e_harness.py` (`CliRunner`, `run_cli`) patches `scip_cli.commands.<cmd>.setup` — **never** subprocess `scip-cli` in tests.
- **Never** call `reindex` in e2e (mutates `~/.cache/scip-cli`).
- Session fixture `indexed_fixture` indexes `tests/fixtures/typescript-project/` once (real `scip-typescript`).
- Stable symbols/paths: add constants to `tests/fixture_catalog.py`; import in tests — do not hardcode fixture paths in test bodies.
- New CLI command: append `scip_cli.commands.<cmd>.setup` to `COMMAND_SETUP_PATHS` in `e2e_harness.py`.

## Fixture vs in-memory DB

|Need|Layer|
|---|---|
|SCIP symbol shapes, analyze false positives, CLI output|Fixture e2e (`test_e2e*.py`)|
|Tarjan, section wiring, one-off SQL plumbing|`tests/analyze_db.py` + `test_analyze_graph.py`|

Prefer fixture e2e for indexer-dependent behavior. Details: `agent.mdc` § TDD.

## After command / flag changes

Run e2e loop at minimum before commit; `scripts/test.sh` before push.
