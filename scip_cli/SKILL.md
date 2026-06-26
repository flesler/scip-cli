---
name: scip-cli
description: Read when needing to find symbols, definitions, references, or members in TypeScript/JavaScript or Python code
---

TypeScript/JavaScript (.ts, .tsx, .js, .jsx) and Python (.py) — not GraphQL, CSS, or other files.

All commands are sub-commands of `scip-cli`. Run from the project root.

## Quick Decision Guide

| Question | Use | What you get |
|----------|-----|--------------|
| "Where is X defined and what does it do?" | `def X` | Functions: full body. Classes: full definition. Use `--limit` to cap results |
| "Where is X used/called?" | `refs X` | All file:line locations. Shows refs for all matching symbols. Use `--limit` to cap |
| "What's in this file?" | `symbols file` | All symbols — bare filename works (`HistoryTab`, `usePatientEntries`) |
| "Find symbols by name" | `search name` | Functions, types, interfaces, classes. Use `--kind variable` for consts |
| "What files depend on this file?" | `rdeps file` | Importers — bare name works |
| "What methods does this class have?" | `members ClassName` | All methods/fields with line ranges |

## Gotchas

- **Bare names** resolve functions, types (aliases + interfaces), and classes. Consts/variables need `def --kind variable X` or `search --kind variable X`. Class methods need `members ClassName`, not bare `def methodName`.
- **Ambiguous types** (e.g. `Opts` in multiple hooks) — `def` returns all matches; `refs` returns refs for all matching symbols. Use `--limit N` to cap results, or use `search` with a more specific pattern to disambiguate.
- **First run** in a project may auto-index (one-time wait, ~10-30s for large codebases). JS-only projects (no `tsconfig.json`) are supported automatically.

## Details

### def

```bash
def [--kind <kind>] [--limit N] <symbol>
```

Kinds: `function`, `method`, `class`, `property`, `variable` — use `--kind` when the bare name isn't in the default set above.

Default `--limit` is 10. Use `--limit 0` for unlimited (not recommended for large codebases).

### refs

```bash
refs [--limit N] <symbol>
```

Returns `file:line` for each reference. Reads source files to find exact line numbers.

Default `--limit` is 10. When multiple symbols match, refs are grouped by symbol with `# <symbol>` headers.

### search

```bash
search [--kind <kind>] [--limit N] <pattern>
```

Returns `file:line Kind symbolName`. Filters noisy symbols (file-level, parameters, type literals).

Default `--limit` is 10.

### symbols

```bash
symbols [--limit N] <file>
```

Returns `startLine-endLine kind name` for each symbol in the file.

Default `--limit` is 10.

### rdeps

```bash
rdeps [--limit N] <file>
```

Returns list of files that import from this file.

Default `--limit` is 10.

### members

```bash
members [--limit N] <symbol>
```

Returns `startLine:endLine kind name` for each member. Note: limited by database coverage — `enclosing_symbol` data is sparse for many indexers.
