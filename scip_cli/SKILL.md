---
name: scip-cli
description: Read when needing symbols, definitions, refs, members, or SQL health dashboards in TS/JS or Python
---

TypeScript/JavaScript (.ts, .tsx, .js, .jsx) and Python (.py) — not GraphQL, CSS, or other files.

All commands are sub-commands of `scip-cli`. Run from the project root.

## Quick Decision Guide

| Question                                  | Use                 | What you get                                                                              |
| ----------------------------------------- | ------------------- | ----------------------------------------------------------------------------------------- |
| "Where is X defined and what does it do?" | `code X`             | Definition snippet (capped at 80 lines by default). Use `members Class` for large classes |
| "Where is X used/called?"                 | `refs X`            | Up to `--limit` file:line refs (default 10). Use `--limit` to raise cap        |
| "What's in this file?"                    | `symbols file`      | Up to `--limit` symbols (default 10). Bare filename works (`helper.ts`)                     |
| "Find symbols by name"                    | `search name`       | Functions, types, interfaces, classes |
| "What files depend on this file?"         | `rdeps file`        | Importers — bare name works                                                               |
| "What methods does this class have?"      | `members ClassName` | All methods/fields with line ranges                                                       |
| "Health / risk / stale code?"             | `analyze`           | Multi-section SQL dashboard — omit target (project), pass file, or symbol                 |

## Gotchas

- **Bare names** resolve functions, types (aliases + interfaces), and classes. Use dotted qualifiers to disambiguate members: `code Widget.run`, `refs Foo.setBar`, `search MyClass.myMethod`, `members pkg.MyClass`. Type/object fields use the same form: `search Options.verbose`, `code Options.verbose`. Consts/let/var are not kept in the index (too many rows, single-line defs) — use `rg` or read the file. Class methods need `members ClassName`, not bare `code methodName`.
- **Ambiguous types** (e.g. `Opts` in multiple hooks) — `code`/`refs` return all matches up to `--limit`; `members` and `analyze` pick the first match with a stderr warning. Use dotted qualifiers or `--path` to narrow.
- **Stale index** — the cache is a snapshot; run `scip-cli reindex` after substantive code changes (no automatic invalidation).
- **Query `--path` vs `reindex --path`** — query `--path` filters results only. `reindex --path` persists scope and **replaces** the cached index with only those tsconfig projects; run full `reindex` (no `--path`) to restore.
- **First run** in a project may auto-index (one-time wait; large monorepos with many `tsconfig.json` files take longer). Projects index in parallel by default (`SCIP_CLI_INDEX_WORKERS`; merge is serial). Repos with more than 10 tsconfig projects log per-project progress to stderr. JS-only projects (no `tsconfig.json`) are supported automatically.
- **Monorepos** are indexed by walking for `tsconfig*.json` under the repo (skips `node_modules`, `.git`, etc.). Nested parent/child projects are deduped. Add extra roots or limit indexing with `.scip-cli.json` (see README). Use query `--path packages/api` to scope lookups.
- **Prerequisites**: Node.js (for `npx` indexers). The `scip` converter auto-downloads on first use if missing; `scip-typescript` / `scip-python` download via `npx`. Optional `.scip-cli.json` for extra index roots or heap tuning. `brew install scip` installs an unrelated optimization solver — scip-cli ignores it and downloads the real binary.

## Details

### code

```bash
code [--kind <kind>] [--limit N] [--max-lines N] [--offset N] [--full] [--path PATH] [--snippet] [--line-numbers] <symbol> [<symbol> ...]
```

Kinds: `function`, `method`, `class`, `property` — use `--kind` when the bare name isn't in the default set above.

`--limit` caps how many matching symbols are shown per query (default 10). Pass multiple symbol names to fetch several definitions in one run; when more than one definition is printed, each block is prefixed with the query name on stdout. `--max-lines` caps source lines **per definition body** (default 80); bodies are also capped at 32 000 characters unless `--full` or `--max-lines 0`. `--snippet` shows only file, line range, and first line (not full body). `--offset N` skips the first N lines **of the definition body** (not file-absolute); the truncation hint uses the same body-relative offset. `--line-numbers` prefixes each line with its line number. Override line cap via `SCIP_CLI_MAX_DEF_LINES`.

For large classes, prefer `members ClassName` first, then `code Class.method` for one member.

### refs

```bash
refs [--limit N] [--path PATH] [--paths-only] <symbol> [<symbol> ...]
```

Returns `file:line` for each reference. Reads source files to find exact line numbers.

Default `--limit` is 10 **reference lines** per symbol query (not mention chunks). When more than one symbol is output, each group is prefixed on stdout with the query name (or `name (path)` when one query matches multiple symbols). Use `--paths-only` for unique file paths (pipe-friendly).

### Pipelines

Commands emit one record per line on stdout; warnings and progress go to stderr. Use `--paths-only` / `--names-only` when piping into another `scip-cli` command.

| Goal                         | Pipeline                                                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Blast radius of a file       | `scip-cli rdeps file.ts \| xargs -I{} scip-cli symbols {}`                                                                                                   |
| Pre-change / health briefing | `scip-cli analyze` or `scip-cli analyze path/to/file.ts` or `scip-cli analyze SymbolName`                                                                    |
| Files that import a symbol   | `scip-cli refs Foo --paths-only`                                                                                                                             |
| Symbols in referencing files | `scip-cli refs Foo --paths-only \| xargs -I{} scip-cli symbols {}` (barrel files may have no symbols; prefer `search Foo --paths-only` for definition files) |
| Find classes, list members   | `scip-cli search Handler --kind class --names-only \| xargs -I{} scip-cli members {}`                                                                        |
| Members → definitions        | `scip-cli members Widget --names-only \| xargs -I{} scip-cli code Widget.{}`                                                                            |
| Find functions, show callers | `scip-cli search Publish --kind function --names-only \| xargs -I{} scip-cli refs {} --paths-only`                                                           |
| Files touching a topic       | `scip-cli search Dynamo --paths-only`                                                                                                                        |
| Count importers              | `scip-cli rdeps file.ts \| wc -l`                                                                                                                            |

`rdeps` already prints bare paths. `refs` defaults to `path:line`; add `--paths-only` to dedupe files. `search` / `members` need `--names-only` or `--paths-only` instead of `awk`.

Each `xargs` invocation reopens the index (fast on cache hit). Use `--limit` on the first command to cap fan-out.

### search

```bash
search [--kind <kind>] [--limit N] [--path PATH] [--names-only] [--paths-only] <pattern> [<pattern> ...]
```

Returns `file:line kind symbolName` (kinds are lowercase: `function`, `class`, etc.). Multiple patterns are OR'd. Filters noisy symbols (file-level, parameters, type literals).

Default `--limit` is 10.

### symbols

```bash
symbols [--limit N] [--path PATH] <file>
```

Returns `startLine-endLine kind name` for each symbol in the file.

Default `--limit` is 10.

### rdeps

```bash
rdeps [--limit N] [--path PATH] <file>
```

Returns list of files that import from this file.

Default `--limit` is 10.

### members

```bash
members [--limit N] [--path PATH] [--names-only] <symbol>
```

Returns `startLine:endLine kind name` for each member. Members are found via SCIP symbol-prefix matching under the parent; line ranges may be missing and are filled by scanning the parent source when needed.

### analyze

```bash
analyze [--limit N] [--path PATH] [--include-tests] [target]
```

Project-wide (no target): bottlenecks, hotspots, cycles, stale types, dead exports, coupling. File path → change-surface, dead exports in file, consumers. Symbol → pressure, dependencies, affected.

**Dogfood loop:** `reindex` → `analyze --limit 25` → `analyze scip_cli/hot_file.py` on suspects. Skips test paths by default (`tests/`, `*.test.*`, `*.spec.*`); use `--include-tests` to include them.

**Easy pickings:** **Cycles** and **dead exports** (production paths only) — cross-file cleanup candidates. **Stale types** — low-use classes. Ignore `analyze/*` helpers in dead exports (same-file section runners). “Dead” = no refs from *other* files in the index, not `vulture`. `--path` scopes file/symbol targets only, not project-wide runs.
