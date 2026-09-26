---
name: scip-cli-sql-bench
description: Read when changing queries.py, analyze SQL, symbols SQL, or sql.py.
---

# SQL / query performance

Small fixture DB hides regressions on 40MB+ indexes. CI perf tests only catch gross mistakes on the tiny project.

## Required before commit

Touching `scip_cli/queries.py`, `scip_cli/analyze/*`, `scip_cli/symbols.py` SQL, or `scip_cli/sql.py`:

```bash
scripts/bench.sh --baseline   # once per change series
# … edit …
scripts/bench.sh --compare
```

Synthetic scale: `tests/bench_db.py` + `tests/test_bench_queries.py`. Lines `BENCH:<name>:<ms>`; compare table ratio >1.0 = regression.

## Correctness vs speed

- Behavior / SCIP shapes → fixture e2e (`.cursor/skills/test/SKILL.md`).
- Graph plumbing only → `analyze_db` unit tests.

## Optional: real cached index

Replace `<project-slug>` under `~/.cache/scip-cli/projects/` — snippet in `agent.mdc` § Large cached index benchmark.
