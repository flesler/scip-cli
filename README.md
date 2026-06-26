# scip-cli

[![PyPI version](https://badge.fury.io/py/scip-cli.svg)](https://badge.fury.io/py/scip-cli)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Fast code intelligence CLI for TypeScript/JavaScript projects. Query SCIP indexes directly via SQLite for instant results.

## Features

- **Fast**: Direct SQLite queries, 100-500x faster than bash wrappers
- **Simple**: Single binary with subcommands
- **Auto-indexing**: Automatically indexes projects on first query
- **Token-efficient**: Clean, minimal output optimized for AI consumption

## Installation

### 1. Install scip-cli

```bash
pip install scip-cli
```

### 2. Install prerequisites (optional)

scip-cli can automatically download the required indexing tools when needed, or you can install them globally for faster performance:

**Option A: Let scip-cli handle it (recommended)**

Just use scip-cli - it will automatically download the required tools via `npx` on first use. No global installation needed.

**Option B: Install globally for better performance**

```bash
# Install scip-typescript (SCIP indexer)
npm install -g @sourcegraph/scip-typescript

# Install scip (SCIP CLI for index conversion)
npm install -g @sourcegraph/scip
```

**Verify installation:**

```bash
scip-cli --help
scip-typescript --version  # Only if you chose Option B
scip --version             # Only if you chose Option B
```

## Prerequisites

- Python 3.7+
- `scip-typescript` (for indexing TypeScript/JavaScript)
- `scip` CLI (for converting indexes)

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

1. On first query, automatically indexes the project using `scip-typescript`
2. Converts the SCIP index to SQLite using `scip expt-convert`
3. Caches the database in `~/.cache/scip-query/projects/<hash>/index.db`
4. Subsequent queries are instant SQLite lookups

## Performance

Compared to bash wrappers:
- `refs`: 6.4s → 0.03s (213x faster)
- `def`: 2.8s → 0.05s (56x faster)
- `search`: 2.6s → 0.03s (87x faster)
- `symbols`: 0.3s → 0.02s (15x faster)
- `rdeps`: 0.2s → 0.02s (10x faster)
- `members`: 3.1s → 0.03s (103x faster)

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
    └── skill.py
```

## License

MIT
