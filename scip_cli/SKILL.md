---
name: scip-cli
description: Read when needing to find symbols, definitions, references, or members in TypeScript/JavaScript or Python code
---

TypeScript/JavaScript (.ts, .tsx, .js, .jsx) and Python (.py) — not GraphQL, CSS, or other files.

All commands are sub-commands of `scip-cli`. Run from the project root.

## Quick Decision Guide

| Question                                  | Use                 | What you get                                                                              |
| ----------------------------------------- | ------------------- | ----------------------------------------------------------------------------------------- |
| "Where is X defined and what does it do?" | `def X`             | Definition snippet (capped at 80 lines by default). Use `members Class` for large classes |
| "Where is X used/called?"                 | `refs X`            | All file:line locations. Shows refs for all matching symbols. Use `--limit` to cap        |
| "What's in this file?"                    | `symbols file`      | All symbols — bare filename works (`helper.ts`, `widget.ts`)                     |
| "Find symbols by name"                    | `search name`       | Functions, types, interfaces, classes. Use `--kind variable` for consts                   |
| "What files depend on this file?"         | `rdeps file`        | Importers — bare name works                                                               |
| "What methods does this class have?"      | `members ClassName` | All methods/fields with line ranges                                                       |

## Gotchas

- **Bare names** resolve functions, types (aliases + interfaces), and classes. Use dotted qualifiers to disambiguate members: `def Widget.run`, `refs Foo.setBar`, `search MyClass.myMethod`, `members pkg.MyClass`. Consts/variables need `def --kind variable X` or `search --kind variable X`. Class methods need `members ClassName`, not bare `def methodName`.
- **Ambiguous types** (e.g. `Opts` in multiple hooks) — `def` returns all matches; `refs` returns refs for all matching symbols. Use `--limit N` to cap results, or use `search` with a more specific pattern to disambiguate.
- **First run** in a project may auto-index (one-time wait; large monorepos with many `tsconfig.json` files take longer). JS-only projects (no `tsconfig.json`) are supported automatically.
- **Monorepos** are indexed by walking for `tsconfig*.json` under the repo (skips `node_modules`, `.git`, etc.). Nested parent/child projects are deduped. Add extra roots or limit indexing with `.scip-cli.json` (see README). Use `--path packages/api` (or any file/dir) to scope queries.
- **Prerequisites**: Node.js (for `npx` indexers). The `scip` converter auto-downloads on first use if missing; `scip-typescript` / `scip-python` download via `npx`. Optional `.scip-cli.json` for extra index roots or heap tuning. `brew install scip` installs an unrelated optimization solver — scip-cli ignores it and downloads the real binary.

## Details

### def

```bash
def [--kind <kind>] [--limit N] [--max-lines N] [--path PATH] <symbol>
```

Kinds: `function`, `method`, `class`, `property`, `variable` — use `--kind` when the bare name isn't in the default set above.

`--limit` caps how many matching symbols are shown (default 10). `--max-lines` caps source lines **per definition body** (default 80) so huge functions/classes do not flood context. Use `--max-lines 0` for the full body. Override default via `SCIP_CLI_MAX_DEF_LINES`.

For large classes, prefer `members ClassName` first, then `def Class.method` for one member.

### refs

```bash
refs [--limit N] [--path PATH] [--paths-only] <symbol>
```

Returns `file:line` for each reference. Reads source files to find exact line numbers.

Default `--limit` is 10. When multiple symbols match, refs are grouped by symbol with `# <symbol>` headers. Use `--paths-only` for unique file paths (pipe-friendly).

### Pipelines

Commands emit one record per line on stdout; warnings and progress go to stderr. Use `--paths-only` / `--names-only` when piping into another `scip-cli` command.

| Goal                         | Pipeline                                                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Blast radius of a file       | `scip-cli rdeps file.ts \| xargs -I{} scip-cli symbols {}`                                                                                                   |
| Files that import a symbol   | `scip-cli refs Foo --paths-only`                                                                                                                             |
| Symbols in referencing files | `scip-cli refs Foo --paths-only \| xargs -I{} scip-cli symbols {}` (barrel files may have no symbols; prefer `search Foo --paths-only` for definition files) |
| Find classes, list members   | `scip-cli search Handler --kind class --names-only \| xargs -I{} scip-cli members {}`                                                                        |
| Members → definitions        | `scip-cli members Widget --names-only \| xargs -I{} scip-cli def Widget.{}`                                                                            |
| Find functions, show callers | `scip-cli search Publish --kind function --names-only \| xargs -I{} scip-cli refs {} --paths-only`                                                           |
| Files touching a topic       | `scip-cli search Dynamo --paths-only`                                                                                                                        |
| Count importers              | `scip-cli rdeps file.ts \| wc -l`                                                                                                                            |

`rdeps` already prints bare paths. `refs` defaults to `path:line`; add `--paths-only` to dedupe files. `search` / `members` need `--names-only` or `--paths-only` instead of `awk`.

Each `xargs` invocation reopens the index (fast on cache hit). Use `--limit` on the first command to cap fan-out.

### search

```bash
search [--kind <kind>] [--limit N] [--path PATH] [--names-only] [--paths-only] <pattern>
```

Returns `file:line Kind symbolName`. Filters noisy symbols (file-level, parameters, type literals).

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

Returns `startLine:endLine kind name` for each member. Note: limited by database coverage — `enclosing_symbol` data is sparse for many indexers.
