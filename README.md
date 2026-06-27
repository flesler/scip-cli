# scip-cli

[![PyPI version](https://badge.fury.io/py/scip-cli.svg)](https://badge.fury.io/py/scip-cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Token-efficient code intelligence for AI agents. Precise refs, definitions, and repo health analysis via SCIP indexes — TypeScript/JavaScript and Python.

## Why

AI agents waste tokens on grep and file scanning. scip-cli gives them precise, type-aware code navigation in milliseconds — and `analyze` surfaces dead code, cycles, and coupling so agents (and humans) can fix real problems fast.

## Features

- **Agent-first**: Install as a skill for Claude Code, Cursor, or any AI agent — precise code navigation without burning context
- **Token-efficient**: One record per line, stderr for warnings, pipe-friendly output
- **Fast**: Direct SQLite queries — 10x to 213x faster than alternatives
- **`analyze`**: Find dead exports, import cycles, stale types, coupling hotspots — actionable health dashboards at project, file, or symbol scope
- **Auto-indexing**: Indexes on first query, caches in SQLite, zero config

## For AI Agents

Install as a reusable skill so your agent always knows how to navigate the codebase:

```bash
scip-cli skill ~/.claude/skills/scip-cli/   # Claude Code
scip-cli skill ~/.cursor/skills/scip-cli/   # Cursor
```

Or dump the quick reference for one-off use:

```bash
scip-cli skill
```

## Installation

### 1. Install scip-cli

**From PyPI** (end users):

```bash
pip install scip-cli
```

**Local development** (use a project venv — do not rely on global `pip`):

```bash
cd scip-cli
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
scip-cli --version
```

`pip install -e .` keeps `scip-cli` on your PATH inside the venv while you edit the repo. Run tests with `pytest` from the same venv.

### 2. Install prerequisites (optional)

On **first index**, scip-cli runs language indexers and builds a SQLite cache. You can let it fetch tools on demand, or install them globally ahead of time so the first run does not download via `npx`:

**Option A: Zero extra setup (recommended)**

Install `scip-cli` and run it. On first index, scip-cli will:

- Download `scip-typescript` / `scip-python` via `npx` when not already on PATH
- Download the `scip` converter binary from [GitHub releases](https://github.com/scip-code/scip/releases) into `~/.cache/scip-cli/bin/` when not already on PATH
- Walk the repo for `tsconfig*.json` project roots (TypeScript monorepos), run `scip-typescript` per project (parallel by default), convert each partial index, then merge into one `index.db`

No `.scip-cli.json` required for discovery. Subsequent queries read the cached database only.

**Option B: Install indexers globally ahead of time**

Same indexing steps as Option A; this only avoids `npx` download on the first run:

```bash
# TypeScript/JavaScript indexer (also handles plain JS via --infer-tsconfig)
npm install -g @sourcegraph/scip-typescript

# Python indexer
npm install -g @sourcegraph/scip-python

# SCIP CLI for index conversion (GitHub release — not on npm)
# https://github.com/scip-code/scip/releases  (v0.8.1+ recommended)
```

**Verify installation:**

```bash
scip-cli --help
scip-typescript --version  # Only if you chose Option B
scip --version             # Install from GitHub releases; v0.8.1+ recommended
```

## Usage

All commands are subcommands of `scip-cli`:

```bash
scip-cli <command> [arguments]
```

### Commands

- `refs <symbol>` - Find all references to a symbol (`--path` to scope)
- `code <symbol>` - Find symbol definition with source code (`--path`, `--max-lines`, `--full`, `--offset`, `--snippet`, `--line-numbers`)
- `search <pattern>` - Search symbols by name pattern (`--path`)
- `symbols <file>` - List all symbols in a file (`--path`; bare filename OK)
- `rdeps <file>` - Find files that depend on a file (`--path`)
- `members <symbol>` - List members of a class/interface (`--path`)
- `analyze [target]` - SQL health dashboards (`--limit`, `--include-tests`). No target: project-wide. File or symbol target for scoped checks. See [Finding easy wins with `analyze`](#finding-easy-wins-with-analyze).
- `reindex` - Force re-indexing of the current project (`--path` to limit scope; repeatable)
- `skill [path]` - Install or dump the SKILL.md

### Examples

```bash
# Find where greet is used
scip-cli refs greet

# Get definition of greet
scip-cli code greet

# Search for symbols matching "Widget"
scip-cli search Widget

# Scope to a subdirectory
scip-cli code greet --path packages/api

# List symbols by bare filename
scip-cli symbols helper.ts

# Find files that import from a module
scip-cli rdeps src/helper.ts

# List members of a class
scip-cli members Widget

# Project health dashboard (or: scip-cli analyze src/foo.ts / scip-cli analyze greet)
scip-cli analyze

# Install skill file
scip-cli skill ~/.claude/skills/scip-cli/SKILL.md
```

### Pipelines

Stdout is one record per line; stderr carries warnings and ambiguity notices. Kinds are lowercase (`function`, `class`, `method`, `property`). Pipe-friendly flags: `refs --paths-only`, `search --names-only` / `--paths-only`, `members --names-only`. `rdeps` already prints bare file paths.

```bash
# What do importers of this file export?
scip-cli rdeps src/helper.ts | xargs -I{} scip-cli symbols {}

# Which files reference a symbol?
scip-cli refs greet --paths-only

# Classes matching a name → list their members
scip-cli search Handler --kind class --names-only | xargs -I{} scip-cli members {}

# Walk class members to their definitions
scip-cli members Widget --names-only | xargs -I{} scip-cli code Widget.{}
```

## How It Works

1. On first query, automatically detects project language from `package.json` (TS/JS) or `pyproject.toml`/`setup.py` (Python)
2. For TypeScript monorepos, walks the repository for `tsconfig*.json` project roots (nested ancestors deduped; root included only when its `include` is broad)
3. Runs `scip-typescript` per project (in parallel when there are multiple projects; set `SCIP_CLI_INDEX_WORKERS=1` to force serial), or `scip-python` for Python
4. Converts each SCIP output to SQLite with `scip expt-convert`, then merges partial databases when needed
5. Caches the result in `~/.cache/scip-cli/projects/<dirname>-<hash>/index.db` (e.g. `my-monorepo-1a3f7a`)
6. Subsequent queries are SQLite lookups against that cache (not re-indexing)

## Configuration

Optional `.scip-cli.json` in the project root:

```json
{
  "maxHeapMb": 8192,
  "indexRoots": ["packages/core", "apps/worker"],
  "onlyIndexRoots": false
}
```

- `maxHeapMb` — Node heap for `scip-typescript` / `scip-python` (default **8192 MB** when omitted). Overridden by `SCIP_CLI_MAX_HEAP_MB`. This is the V8 heap cap, not total RAM usage.
- `indexRoots` — extra TypeScript project directories to include on **first index**, merged with auto-discovered projects.
- `onlyIndexRoots` — skip auto-discovery and index **only** `indexRoots` (smaller initial index when you only care about part of a monorepo).

`SCIP_CLI_INDEX_WORKERS` controls parallel `scip-typescript` runs during first index (default: up to 8). Merge into one database is always serial.

Large monorepos (>10 tsconfig projects) log per-project progress to stderr during indexing; smaller repos stay quiet aside from the final `Indexed … (size)` line.

Scoped indexing without editing `.scip-cli.json`:

```bash
scip-cli reindex --path packages/server
scip-cli reindex --path packages/api --path packages/worker
```

`--path` limits which discovered tsconfig projects are indexed (prefix match, same idea as query `--path`). The scope is saved as `index-scope.json` next to `index.db` and reused until you run a full `scip-cli reindex` with no `--path`.

Run `scip-cli reindex` after changing scope, `.scip-cli.json` index settings, or when you want a fresh index.

## Finding easy wins with `analyze`

Use `analyze` on the repo itself before broad refactors or agent review — it surfaces cross-file issues from the SCIP index (not Python `vulture`).

**Quick pass** (after `scip-cli reindex`):

```bash
scip-cli analyze --limit 25
scip-cli analyze --priority high --limit 25   # dead exports & cycles only
```

Sections are tagged `[high]`, `[medium]`, `[low]` and listed in that order.

| Tier | Project sections | Action |
| ---- | ---------------- | ------ |
| **high** | Cycles, unreferenced, dead exports, stale types | Nuke or fix cycles; delete unused; `_` prefix |
| **medium** | Same-file only, change surface (file target) | Module-private by usage |
| **low** | Test-only consumers, coupling, bottlenecks, hotspots | Noisy on Python (index omits many same-file calls); verify with `rg` |

Use `--priority high` for a quick gate; `--priority high,medium` adds context. File drill-down adds change surface and unused imports.

**What to look at first**

| Section | Easy pickings |
| ------- | ------------- |
| **Cycles** | Import/mention cycles between production files — break the edge or extract shared code |
| **Unreferenced** | No usage in the index at all — delete |
| **Dead exports** | No external refs — delete or `_` prefix |
| **Stale types** | Classes/types with ≤1 external consumer — merge, inline, or document why they stay |
| **Same-file only** | Used only inside defining file — rename to `_` |
| **Test-only consumers** | Cross-file refs are all from tests — promote to e2e or accept as internal |

**Per-file or package drill-down** on hubs or suspects:

```bash
scip-cli analyze scip_cli/queries.py --limit 20   # file: scoped project + per-file + top symbols
scip-cli analyze scip_cli --limit 15              # directory: scoped project + each file under it
```

`Dead exports in file` lists same-module symbols with no *external* refs — module-private `_helpers` are filtered out. Remaining rows are worth a manual `rg` check.

**Defaults:** project-wide and directory analyze skip `tests/`, `*.test.*`, `*.spec.*`, `conftest.py`, and `__tests__/`. Pass `--include-tests` to include them. File-target analyze always includes that file.

**Limits:** “Dead export” means no cross-file mentions in the index — not unreachable code. Same-file private helpers are expected. Re-run `reindex` after large changes; the index is a snapshot.

## Performance

Inspired by [scip-query](https://github.com/PlunderStruck/scip-query), scip-cli is a lightweight Python partial reimplementation optimized for speed. Compared to the original:

- `refs`: 6.4s → 0.03s (213x faster)
- `code`: 2.8s → 0.05s (56x faster)
- `search`: 2.6s → 0.03s (87x faster)
- `symbols`: 0.3s → 0.02s (15x faster)
- `rdeps`: 0.2s → 0.02s (10x faster)
- `members`: 3.1s → 0.03s (103x faster)

The speedup comes from using optimized direct SQLite queries and cutting some nice but very slow goodies (like ts-morph).

## Architecture

```
scip_cli/
├── __init__.py
├── __main__.py      # CLI entry point
├── cli_args.py      # Shared argparse helpers
├── config.py        # .scip-cli.json loader
├── discover.py      # TypeScript project discovery
├── merge.py         # SQLite index merging
├── scip_tool.py     # scip binary download
├── sql.py           # SQLite helpers
├── paths.py         # --path scope filtering
├── project.py       # Project root + language detection
├── cache.py         # Index cache paths
├── scope.py         # Persisted reindex scope (index-scope.json)
├── debug.py         # SCIP_CLI_DEBUG stderr helpers
├── indexing.py      # SCIP index build + get_db
├── symbols.py       # Symbol parsing and kinds
├── queries.py       # Symbol/file SQL queries
├── source.py        # Filesystem source reads
├── output.py        # CLI formatting helpers
├── session.py       # setup() and single-match resolution
├── targets.py       # file vs symbol target heuristics
├── analyze/         # SQL dashboard queries (project/file/symbol)
└── commands/        # Subcommand implementations
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -q
pytest tests/ -m integration -q   # indexes tests/fixtures/sample-project (needs scip-typescript)
```

### Debug Logging

Set `SCIP_CLI_DEBUG=1` to enable SQL query logging to stderr (statements truncated to 200 chars):

```bash
SCIP_CLI_DEBUG=1 scip-cli refs MyFunction
# Shows: SQL: SELECT ... | params: (...)
```

This is useful for testing and debugging SQL queries

## License

MIT
