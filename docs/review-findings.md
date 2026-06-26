# Code Review Findings

## Status: Complete

All actionable findings from reviews 1–4 have been addressed or explicitly discarded.

### Review 4 — Final pass (fixed)

- `SymbolKind.filterable_values()` excludes `unknown` from `--kind` CLI choices
- DB connections closed in all commands via `try/finally`
- `scip_cli/SKILL.md` packaged correctly; `skill` command reads from package dir
- `detect_language`: `package.json` first (TS/JS via scip-typescript), `--infer-tsconfig` for JS-only
- Python support: `parse_symbol`, `members` patterns, docs updated
- `run_with_fallback`: unified `_run_subprocess` with timeout handling on all paths
- `INDEX_TIMEOUT` module constant
- `__main__.py`: top-level `RuntimeError` and `KeyboardInterrupt` handling
- `is_noisy_symbol`: removed overly broad `\d+:` regex (false positives on Python symbols)
- `members.py`: Python-first regex when parent file is `.py`
- `SKILL.md`: removed unimplemented "qualified names always work" claim
- `README.md`: documents `scip-python`, JS-only auto `--infer-tsconfig`
- Tests: `detect_language`, Python `parse_symbol`/`infer_kind`, `SymbolKind` enum assertions

### Discarded (acceptable trade-offs)

- `sys.exit` in CLI helpers (`setup`, `resolve_one_*`): intentional for CLI layer
- `refs.get_exact_refs` vs `get_refs_for_symbols` duplication: different precision needs
- Command integration tests: pure-function + DB unit tests cover core logic
- `resolve_symbol` LIKE performance: acceptable for typical project sizes
- Multi-line member `end_line` fallback: indexer data limitation

## Summary

The codebase is secure (path traversal, SQL escaping), supports TS/JS/Python, has 45+ unit tests, and docs match behavior.
