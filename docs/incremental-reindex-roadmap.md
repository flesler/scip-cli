# Incremental reindex roadmap

Phased plan to avoid full `scip-typescript` runs on every `reindex`. Shard reuse first; file-level and upstream TSC incremental follow.

## Phase 1 — scip-cli shard reuse (shipped)

Per-tsconfig shard cache with content fingerprints. **Shippable:** unit + integration tests in-repo; large monorepos can be validated manually outside the repo (not checked in).

- [x] Roadmap doc
- [x] `shards/manifest.json` in cache dir (fingerprint + part DB path per tsconfig project)
- [x] `compute_shard_fingerprint()` — tsconfig chain + included source file content hashes + exclude globs
- [x] `reindex --incremental` — per-project shards (batch size 1), reuse unchanged part DBs
- [x] Persist shard part DBs under `cache/shards/*.db`
- [x] Full `reindex` clears shard cache (avoid stale reuse after non-incremental rebuild)
- [x] `reindex --fresh` clears shard cache
- [x] Unit tests for fingerprint, manifest merge, and warm `index_typescript` reuse
- [x] Reindex CLI flag tests (`--incremental`, rejects with `--fresh` / Python)
- [x] Stderr stats: `Incremental: N shard(s) reused, M reindexed`
- [x] Update `scip_cli/SKILL.md` and README flag list

## Phase 2 — scip-typescript fork: TSC incremental program

- [ ] Fork `sourcegraph/scip-typescript`
- [ ] `--incremental` / `--ts-build-info-file` CLI flags
- [ ] `createIncrementalProgram` + `createIncrementalCompilerHost` in `ProjectIndexer`
- [ ] Default `tsBuildInfoFile` under scip-cli cache dir (not repo root)
- [ ] scip-cli passes `--ts-build-info-file` when shard is dirty
- [ ] Benchmark dirty shard: program build time before/after

## Phase 3 — File-level incremental inside a shard

- [ ] Document-level upsert in SQLite (replace rows for changed paths; merge is insert-only today)
- [ ] `reindex --incremental` accepts optional changed-file list (content-hash manifest in cache)
- [ ] Invalidation: changed files ∪ direct importers (from existing index `mentions`)
- [ ] scip-typescript fork: skip unchanged files in `ProjectIndexer` loop (`--files` or internal dirty set)
- [ ] Optional git input via env / scip-atlas (`last_index_commit`, `git diff --name-only`) — not a hard scip-cli dependency

## Phase 4 — Polish

- [ ] Dogfood on this repo + optional large-monorepo validation (manual, outside CI)
- [ ] Submit scip-typescript fork as upstream PR (phase 2, then 3 indexer pieces)
- [ ] `scripts/bench.sh` scenario for incremental reindex
