---
name: scip-cli
description: Read when needing symbol lookup or SQL health dashboards in code.
---

TypeScript/JavaScript (.ts, .tsx, .js, .jsx), Python (.py), Go (.go), and Rust (.rs) — not GraphQL, CSS, or other files.

All commands are sub-commands of `scip-cli`. Run from the project root.

**Contributors:** keep `pip install -e .` (or `pip install -e ".[dev]"` in this repo) so bare `scip-cli` on PATH runs your live checkout — not a venv-relative path.

## Quick Decision Guide

|Question|Use|What you get|
|---|---|---|
|"Where is X defined and what does it do?"|`code X`|Definition snippet (capped at 80 lines by default). Use `members Class` for large classes|
|"Where is X used/called?"|`refs X`|Up to `--limit` file:line refs (default 10). Use `--limit` to raise cap|
|"What's in this file?"|`symbols file`|Up to `--limit` symbols (default 10). Bare filename works (`helper.ts`)|
|"Find symbols by name"|`search name`|Functions, types, interfaces, classes|
|"What files depend on this file?"|`rdeps file`|Importers — bare name works|
|"What does this symbol/file depend on?"|`deps target`|Outbound dependencies — symbols referenced within a function or file|
|"What methods does this class have?"|`members ClassName`|All methods/fields with line ranges|
|"Health / risk / stale code?"|`analyze`|Multi-section SQL dashboard — omit target (project), pass file, or symbol|

## Gotchas

- **Bare names** resolve functions, types (aliases + interfaces), and classes. Use dotted qualifiers to disambiguate members: `code Widget.run`, `refs Foo.setBar`, `search MyClass.myMethod`, `members pkg.MyClass`. Type/object fields use the same form: `search Options.verbose`, `code Options.verbose`. Consts/let/var are not kept in the index (too many rows, single-line defs) — use `rg` or read the file. Class methods need `members ClassName`, not bare `code methodName`.
- **Ambiguous types** (e.g. `Opts` in multiple hooks) — `code`/`refs` return all matches up to `--limit`; `members` and `analyze` pick the first match with a stderr warning. Use dotted qualifiers or `--path` to narrow.
- **Stale index** — the cache is a snapshot; run `scip-cli reindex` after substantive code changes (no automatic invalidation).
- **Query `--path` vs `reindex --path` / `--tsconfig`** — query `--path` filters results only. `reindex --path` is a **TypeScript-only** directory prefix on discovered projects. `reindex --tsconfig 'pkg/tsconfig.*.json'` indexes those files directly (globs ok; one heap per file). Both persist scope and **replace** the cache; run full `reindex` (no `--path`/`--tsconfig`) to restore.
- **allowJs** — when a tsconfig (after `extends`) has `allowJs: true`, matching `.js`/`.jsx` under that config's `include`/`files` are indexed too. Unset/`false` skips JS. JS-only repos with no `tsconfig.json` still use `--infer-tsconfig`.
- **First run** in a project may auto-index (one-time wait; large monorepos with many `tsconfig.json` files take longer). Projects index in parallel by default (`SCIP_CLI_INDEX_WORKERS`; merge is serial). Repos with more than 10 tsconfig projects log per-project progress to stderr. JS-only projects (no `tsconfig.json`) are supported automatically.
- **Monorepos** are indexed by walking for `tsconfig*.json` under the repo (skips `node_modules`, `.git`, etc.). Nested parent/child projects are deduped. Add extra roots or limit indexing with `.scip-cli.json` (see README). Use query `--path packages/api` to scope lookups.
- **Prerequisites**: Node.js (for TypeScript/Python via `npx`), Go toolchain (for Go via `go install`), or Rust toolchain (for Rust via `rustup`). The `scip` converter auto-downloads on first use if missing; `scip-typescript` / `scip-python` download via `npx`; `scip-go` downloads via `go install` to `~/go/bin`; `rust-analyzer` installs via `rustup component add`. Optional `.scip-cli.json` for extra index roots or heap tuning. `brew install scip` installs an unrelated optimization solver — scip-cli ignores it and downloads the real binary.

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

|Goal|Pipeline|
|---|---|
|Blast radius of a file|`scip-cli rdeps file.ts \|xargs -I{} scip-cli symbols {}`|
|Pre-change / health briefing|`scip-cli analyze --limit 40 --per-check-limit 5` (or a file / symbol)|
|Files that import a symbol|`scip-cli refs Foo --paths-only`|
|Symbols in referencing files|`scip-cli refs Foo --paths-only \|xargs -I{} scip-cli symbols {}` (barrel files may have no symbols; prefer `search Foo --paths-only` for definition files)|
|Find classes, list members|`scip-cli search Handler --kind class --names-only \|xargs -I{} scip-cli members {}`|
|Members → definitions|`scip-cli members Widget --names-only \|xargs -I{} scip-cli code Widget.{}`|
|Find functions, show callers|`scip-cli search Publish --kind function --names-only \|xargs -I{} scip-cli refs {} --paths-only`|
|Files touching a topic|`scip-cli search Dynamo --paths-only`|
|Count importers|`scip-cli rdeps file.ts \|wc -l`|
|Outbound dependency files|`scip-cli deps file.ts --paths-only`|

`rdeps` already prints bare paths. `deps --paths-only` deduplicates to unique files. `refs` defaults to `path:line`; add `--paths-only` to dedupe files. `search` / `members` need `--names-only` or `--paths-only` instead of `awk`.

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

### deps

```bash
deps [--limit N] [--path PATH] [--paths-only] <symbol|file>
```

Returns outbound dependencies — symbols referenced within a function/method or file.

For a symbol target, finds all symbols mentioned within the definition range (function body). For a file target, finds all external symbols referenced in that file (excluding the file's own symbols).

Output format: `file:line  symbolName` for each dependency. Use `--paths-only` to output unique file paths only (pipe-friendly).

Default `--limit` is 10.

### members

```bash
members [--limit N] [--path PATH] [--names-only] <symbol>
```

Returns `startLine:endLine kind name` for each member. Members are found via SCIP symbol-prefix matching under the parent; line ranges may be missing and are filled by scanning the parent source when needed.

### analyze

```bash
analyze [--limit N] [--per-check-limit N] [--path PATH] [--include-tests] [--priority LEVEL] [--check NAME] [target]
```

|Target|Output|
|---|---|
|_(omit)_|Project-wide dashboards only|
|**directory** (`scip_cli`, `src/pkg/`)|Scoped project dashboards + per-file sections for each indexed file under the dir|
|**file**|Scoped project dashboards for that file + per-file sections + top symbols by external consumers|
|**symbol**|Symbol pressure, consumers, dependencies, affected|

Sections are ordered **high → medium → low**. `[high]` cycles, dead exports, dead files, stale types (unreferenced is skipped when dead exports is on — same survivors; file-target unreferenced-in-file is skipped when dead-in-file is on); `[medium]` same-file-only, change surface (file); `[low]` test-only consumers (noisy on Python), coupling, bottlenecks, hotspots.

`--limit` caps **result rows across the whole run** (default 20); remaining checks are skipped once the cap is reached. `(none)` sections, headers, and `… truncated` / `[note]` lines do not count as findings. `--per-check-limit N` additionally caps each section (default: unlimited) so one noisy check cannot spend the whole budget. Agents: `analyze --limit 40 --per-check-limit 5`.

Directory `analyze some/dir` spends the **same global `--limit`** on per-file sections after dashboards (max 30 files). Prefer project/dir dashboards, then `analyze` one file.

`--priority high` or `--priority high,medium` (also `1`/`2`/`3`) skips lower tiers.

`--check NAME` (repeatable or comma-separated) runs only those sections and ANDs with `--priority`. Unknown names error. A name that exists for another target (e.g. `unused_imports` on a project-wide run) yields no matching sections.

Directory detection uses the filesystem when present, otherwise an indexed path prefix. `--path` narrows ambiguous file/symbol resolution only (not directory scope — pass the dir as `target`).

**Easy pickings:** **Cycles**, **dead exports**, and **dead files** (production paths) — cross-file cleanup. **Stale types** — types with no external refs in the index. Ignore `analyze/*` section helpers in dead exports. “Dead” = no refs from _other_ files in the index, not `vulture`. Empty `scip-cli rdeps` on a hit is usually a SCIP miss (`require()`, named imports, barrels), not proof unused. Unreferenced is omitted when dead exports is on (same survivors). Sections with hits print one `Warn:`; for each row run `rg -F STEM` where STEM is the **file basename inside `(...)`**, no extension — ignore hits in that same file. Do not `rg` the symbol name.

### reindex

```bash
reindex [--path DIR ...] [--tsconfig FILE_OR_GLOB ...] [--exclude [GLOB ...]] [--fresh] [--with-external]
```

`--path` and `--tsconfig` cannot be combined (**TypeScript only**). `--tsconfig` takes `tsconfig*.json` files (repeatable; globs expanded inside the tool). File-based runs default to one `scip-typescript` process per file so each gets its own heap (`SCIP_CLI_TS_INDEX_BATCH_SIZE` still overrides). Scope and exclude defaults are persisted in `metadata.json` next to `index.db` and reused on later `reindex` runs.

`--exclude GLOB` omits matching files from the SQLite index after conversion (repeatable; merged with `excludeGlobs` in `.scip-cli.json`). Passing `--exclude` updates the persisted exclude list; a lone bare `--exclude` (no globs on that flag) clears it — `--exclude foo --exclude` keeps `foo`. Patterns without `/` match basenames (`*.test.ts`); patterns with `/` match repo-relative paths (`tests/**`, `**/__tests__/**`). Indexers still parse excluded files when production code imports them — post-process removal is authoritative.

`--fresh` ignores persisted `metadata.json` and clears it before indexing unless `--path`, `--tsconfig`, or `--exclude` are set on the same command (use `reindex --fresh` to restore a full index).

`--incremental` (**TypeScript only**) reuses cached per-tsconfig shard DBs under `shards/` in the cache dir when inputs are unchanged. Forces one `scip-typescript` run per project. A plain `reindex` clears the shard cache; run `reindex --incremental` after an initial full index to benefit. Cannot combine with `--fresh`.
