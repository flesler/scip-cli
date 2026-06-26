# scip-cli

[![PyPI version](https://badge.fury.io/py/scip-cli.svg)](https://badge.fury.io/py/scip-cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Fast code intelligence CLI for TypeScript/JavaScript and Python projects. Query SCIP indexes directly via SQLite for instant results.

## Features

- **Fast**: Direct SQLite queries, eliminating skippable overhead
- **Simple**: Single binary with subcommands
- **Auto-indexing**: Automatically indexes projects on first query
- **Token-efficient**: Clean, minimal output optimized for AI consumption

## Installation

### 1. Install scip-cli

**From PyPI:**

```bash
pip install scip-cli
```

**From source (local development):**

```bash
git clone https://github.com/flesler/scip-cli.git
cd scip-cli
pip install .
```

For editable development (where `pip install -e .` fails due to permissions):

```bash
export PYTHONPATH=/path/to/scip-cli:$PYTHONPATH
python -m scip_cli --help
```

### 2. Install prerequisites (optional)

scip-cli can automatically download the required indexing tools when needed, or you can install them globally for faster performance:

**Option A: Let scip-cli handle it (recommended)**

Just use scip-cli - it will automatically download the required tools via `npx` on first use. No global installation needed.

**Option B: Install globally for better performance**

```bash
# TypeScript/JavaScript indexer (also handles plain JS via --infer-tsconfig)
npm install -g @sourcegraph/scip-typescript

# Python indexer
npm install -g @sourcegraph/scip-python

# SCIP CLI for index conversion
npm install -g @sourcegraph/scip
```

**Verify installation:**

```bash
scip-cli --help
scip-typescript --version  # Only if you chose Option B
scip --version             # Only if you chose Option B
```

## Usage

All commands are subcommands of `scip-cli`:

```bash
scip-cli <command> [arguments]
```

### Commands

- `refs <symbol>` - Find all references to a symbol
- `def <symbol>` - Find symbol definition with source code
- `search <pattern>` - Search symbols by name pattern
- `symbols <file>` - List all symbols in a file
- `rdeps <file>` - Find files that depend on a file
- `members <symbol>` - List members of a class/interface
- `reindex` - Force re-indexing of the current project
- `skill [path]` - Install or dump the SKILL.md

### Examples

```bash
# Find where useDictation is used
scip-cli refs useDictation

# Get definition of useDictation
scip-cli def useDictation

# Search for symbols matching "Dictation"
scip-cli search Dictation

# List symbols in a file
scip-cli symbols src/hooks/useDictation.ts

# Find files that import from useDictation.ts
scip-cli rdeps src/hooks/useDictation.ts

# List members of a class
scip-cli members UseDictationOptions

# Install skill file
scip-cli skill ~/.claude/skills/scip/SKILL.md
```

## How It Works

1. On first query, automatically detects project language from `package.json` (TS/JS) or `pyproject.toml`/`setup.py` (Python)
2. Indexes using `scip-typescript` (adds `--infer-tsconfig` for JS-only projects) or `scip-python`
3. Converts the SCIP index to SQLite using `scip expt-convert`
4. Caches the database in `~/.cache/scip-cli/projects/<hash>/index.db`
5. Subsequent queries are instant SQLite lookups

## Performance

Inspired by [scip-query](https://github.com/PlunderStruck/scip-query), scip-cli is a lightweight Python reimplementation optimized for speed. Compared to the original bash wrapper scripts:

- `refs`: 6.4s → 0.03s (213x faster)
- `def`: 2.8s → 0.05s (56x faster)
- `search`: 2.6s → 0.03s (87x faster)
- `symbols`: 0.3s → 0.02s (15x faster)
- `rdeps`: 0.2s → 0.02s (10x faster)
- `members`: 3.1s → 0.03s (103x faster)

The speedup comes from direct SQLite queries instead of shell command chains, eliminating subprocess overhead.

## Architecture

```
scip_cli/
├── __init__.py
├── __main__.py    # CLI entry point
├── lib.py         # Core utilities (indexing, symbol resolution)
└── commands/      # Subcommand implementations
    ├── refs.py
    ├── def_cmd.py
    ├── search.py
    ├── symbols.py
    ├── rdeps.py
    ├── members.py
    ├── reindex.py
    └── skill.py
```

## License

MIT
