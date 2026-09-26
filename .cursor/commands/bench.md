# Benchmark SQL changes

1. Read `.cursor/skills/sql-bench/SKILL.md`.
2. If the user has not saved a baseline this session and you changed SQL: `scripts/bench.sh --baseline`.
3. After edits: `scripts/bench.sh --compare` (or `scripts/bench.sh` for timings only).
4. Report any ratio >1.2 as a likely regression; suggest investigation.

Do not commit unless the user asks.
