---
name: scip-cli
description: Read when needing to find symbols, definitions, references, or members in TypeScript/JavaScript or Python code
---

TypeScript/JavaScript (.ts, .tsx, .js, .jsx) and Python (.py) — not GraphQL, CSS, or other files.

All commands are sub-commands of `scip-cli`. Run from the project root.

## Quick Decision Guide

| Question | Use | What you get |
|----------|-----|--------------|
| "Where is X defined and what does it do?" | `def X` | Functions: full body. Classes: full definition. Multiple exact matches returned together |
| "Where is X used/called?" | `refs X` | All file:line locations. Ambiguous bare names → first match only |
| "What's in this file?" | `symbols file` | All symbols — bare filename works (`HistoryTab`, `usePatientEntries`) |
| "Find symbols by name" | `search name` | Functions, types, interfaces, classes. Use `--kind variable` for consts |
| "What files depend on this file?" | `rdeps file` | Importers — bare name works |
| "What methods does this class have?" | `members ClassName` | All methods/fields with line ranges |

## Gotchas

- **Bare names** resolve functions, types (aliases + interfaces), and classes. Consts/variables need `def --kind variable X` or `search --kind variable X`. Class methods need `members ClassName`, not bare `def methodName`.
- **Ambiguous types** (e.g. `Opts` in multiple hooks) — `def` returns all; `refs` picks the first and warns. Use `search` with a more specific pattern to disambiguate.
- **First run** in a project may auto-index (one-time wait, ~10-30s for large codebases). JS-only projects (no `tsconfig.json`) are supported automatically.

## Details

### def

```bash
def [--kind <kind>] <symbol>
```

Kinds: `function`, `method`, `class`, `property`, `variable` — use `--kind` when the bare name isn't in the default set above.

### refs

```bash
refs <symbol>
```

Returns `file:line` for each reference. Reads source files to find exact line numbers.

### search

```bash
search [--kind <kind>] <pattern>
```

Returns `file:line Kind symbolName`. Filters noisy symbols (file-level, parameters, type literals).

### symbols

```bash
symbols <file>
```

Returns `startLine-endLine kind name` for each symbol in the file.

### rdeps

```bash
rdeps <file>
```

Returns list of files that import from this file.

### members

```bash
members <symbol>
```

Returns `startLine:endLine kind name` for each member. Note: limited by database coverage — `enclosing_symbol` data is sparse for many indexers.
