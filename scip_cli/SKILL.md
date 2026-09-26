---
name: scip-cli
description: Read when needing symbol lookup or SQL health dashboards in code.
---

TypeScript/JavaScript, Python, Go, Rust — not GraphQL, CSS, or other files. Run from project root.

**Contributors:** `pip install -e ".[dev]"` so bare `scip-cli` on PATH is this checkout.

## Quick guide

|Question|Command|Output|
|---|---|---|
|Definition / body|`code X`|Snippet (default 80 lines/def; `members Class` for big types)|
|Usages|`refs X`|`file:line` refs|
|Symbols in file|`symbols file`|`start-end kind name` (bare filename ok)|
|Find by name|`search pattern`|Matching symbols|
|Who imports this file?|`rdeps file`|Importer paths|
|What does this use?|`deps target`|Outbound deps (symbol or file)|
|Class members|`members Class`|Methods/fields + line ranges|
|Health / risk|`analyze`|SQL dashboard — project, dir, file, or symbol|
|Raw SQL|`query "SELECT …"`|Rows from `index.db` (`--format tsv|csv|json`)|

Default `--limit` is **10** on query commands unless noted. Stdout = records; stderr = warnings/progress. Pipe with `--paths-only` / `--names-only`.

## Gotchas

- **Bare names** — functions, types, classes. Members need qualifiers: `code Widget.run`, `members pkg.MyClass`. Consts/vars are not indexed — use `rg`. Class methods: `members Class`, not bare `code method`.
- **Ambiguity** — `code`/`refs` return up to `--limit` matches; `members`/`analyze` pick first with stderr warning. Narrow with dotted names or query `--path`.
- **Stale index** — run `reindex` after substantive edits (no auto-invalidation).
- **Query `--path` ≠ reindex scope** — query `--path` filters results only. `reindex --path` / `--tsconfig` persist TS scope and replace cache; full `reindex` restores.
- **Monorepos** — walks `tsconfig*.json` (skips `node_modules`, `.git`). Dedupes nested projects. Extra roots: `.scip-cli.json` (README). Query scope: `--path packages/api`.
- **allowJs** — when tsconfig `allowJs: true`, matching `.js`/`.jsx` under `include`/`files` are indexed. No root `tsconfig.json`: `--infer-tsconfig`.
- **First run** may auto-index (parallel by default, `SCIP_CLI_INDEX_WORKERS`). >10 tsconfigs log progress. Prerequisites: Node (TS/Python), Go, or Rust toolchain; `scip` converter auto-downloads. `brew install scip` is the wrong package.

## Pipelines

|Goal|Pipeline|
|---|---|
|Blast radius|`scip-cli rdeps file.ts \|xargs -I{} scip-cli symbols {}`|
|Health briefing|`scip-cli analyze --limit 40 --per-check-limit 5`|
|Importer files|`scip-cli refs Foo --paths-only`|
|Symbols in importers|`scip-cli refs Foo --paths-only \|xargs -I{} scip-cli symbols {}`|
|Classes → members|`scip-cli search Handler --kind class --names-only \|xargs -I{} scip-cli members {}`|
|Members → defs|`scip-cli members Widget --names-only \|xargs -I{} scip-cli code Widget.{}`|
|Topic files|`scip-cli search Dynamo --paths-only`|
|Outbound files|`scip-cli deps file.ts --paths-only`|

`xargs` reopens the index each call — cap fan-out with `--limit` on the first command.

## Commands

### code

```bash
code [--kind KIND] [--limit N] [--max-lines N] [--offset N] [--full] [--path PATH] [--snippet] [--line-numbers] <symbol> [...]
```

`--kind`: `function`, `method`, `class`, `property`. Multiple symbols: each block prefixed on stdout. `--max-lines` per body (default 80; also 32k char cap unless `--full` or `--max-lines 0`). `--offset` is body-relative. `SCIP_CLI_MAX_DEF_LINES` overrides cap.

### refs

```bash
refs [--limit N] [--path PATH] [--paths-only] <symbol> [...]
```

`file:line` per ref (reads source for lines). Multi-symbol groups prefixed on stdout.

### search

```bash
search [--kind KIND] [--limit N] [--path PATH] [--names-only] [--paths-only] <pattern> [...]
```

`file:line kind name`. Patterns OR'd. Filters noisy symbols.

### symbols

```bash
symbols [--limit N] [--path PATH] <file>
```

### rdeps

```bash
rdeps [--limit N] [--path PATH] <file>
```

Bare importer paths on stdout.

### deps

```bash
deps [--limit N] [--path PATH] [--paths-only] <symbol|file>
```

Symbol: deps inside definition range. File: external symbols referenced. Format `file:line  symbol`; `--paths-only` dedupes files.

### members

```bash
members [--limit N] [--path PATH] [--names-only] <symbol>
```

`start:end kind name`. Prefix match under parent; missing ranges filled from source when needed.

### query

```bash
query [--format tsv|csv|json] <sql> [...]
```

Read-only SQL against the cached project `index.db`. Default `--format` is **tsv** (header row + tab-separated values). `csv` and `json` (array of objects) are also supported. Connection uses the same read-only pragmas as other commands.

### analyze

```bash
analyze [--limit N] [--per-check-limit N] [--path PATH] [--include-tests] [--priority LEVEL] [--check NAME] [target]
```

|Target|Scope|
|---|---|
|_(omit)_|Project dashboards|
|directory|Dir dashboards + per-file sections (indexed files under dir)|
|file|File dashboards + top symbols by external consumers|
|symbol|Pressure, consumers, deps, affected|

Priority **high → medium → low**. `--limit` = total finding rows (default 20); headers/truncation don't count. `--per-check-limit` caps each section. Agents: `--limit 40 --per-check-limit 5`. `--priority high` or `high,medium` (`1`/`2`/`3`) skips lower tiers. `--check NAME` (repeatable/comma) ANDs with priority.

**Easy wins:** cycles, dead exports, dead files (production). Stale types = types with no external refs. Dead = no cross-file refs in index, not `vulture`. Empty `rdeps` on a hit is often a SCIP miss — verify with `rg -F STEM` (basename in `(...)`, same-file hits ignored).

### reindex

```bash
reindex [--path DIR ...] [--tsconfig GLOB ...] [--exclude [GLOB ...]] [--fresh] [--no-incremental] [--unversioned] [--with-external]
```

`--path` and `--tsconfig` are TS-only and mutually exclusive. `--tsconfig` globs expanded in-tool; one heap per file by default (`SCIP_CLI_TS_INDEX_BATCH_SIZE` overrides). Scope/exclude persist in `metadata.json`.

`--exclude GLOB` drops matching docs post-convert (repeatable; merges `.scip-cli.json` `excludeGlobs`). Bare `--exclude` clears list; `--exclude foo --exclude` keeps `foo`. No `/` = basename; with `/` = repo-relative.

`--fresh` clears persisted metadata (unless combined with scope flags on same command).

**Incremental by default** in git TypeScript repos: reuses `shards/manifest.json` (`git_commit` + per-shard `tsconfig_digest`); skips clean shards. Dirty: git delta ∪ importer closure → fork `--files` → upsert live `index.db`; deletions remove documents. `--no-incremental` or `--fresh` forces full reindex and clears the manifest. Non-git, `--unversioned`, or non-TypeScript projects always full-reindex.
