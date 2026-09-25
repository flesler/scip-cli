# Incremental reindex benchmarks

Results from benchmarking `scip-cli reindex --incremental` on ephemeral fixtures.  
**Do not name customer repos, paths, or symbols in this file.** Large-monorepo numbers use a local tmpfs checkout (16 shard tsconfigs, ~14k source files, ~90 MB index).

Related: [incremental-reindex-roadmap.md](incremental-reindex-roadmap.md) (phases and design).

**Fork:** `github:flesler/scip-typescript#feat/partial-files` (`SCIP_TYPESCRIPT_NPX_PACKAGE`).  
**Upstream:** https://github.com/sourcegraph/scip-typescript — PR to upstream **pending** (not opened).  
Local dev: `npm link` from a clone of that branch (>= `ce6e9c9`).

---

## Progress log (newest first)

| Date | Change | Result |
|------|--------|--------|
| 2026-09-25 | **Git-only incremental** (drop hashes/stat/mtime; `--incremental` requires git) | Shard skip = git delta + `tsconfig_digest`; warm git-delta scan **~0.04s** on 4-shard fixture |
| 2026-09-25 | **Fork squashed for upstream PR** (`ce6e9c9`, `--files` only on `sourcegraph/main`) | One commit; TSC `--incremental` dropped from fork branch |
| 2026-09-25 | **Large monorepo cold discovery** (16 shards, ~21k source paths, no node_modules) | **Git ls-files ~12.6s** vs **skip-dir glob ~26.6s**; warm incremental **~0.2s** 16/0 |
| 2026-09-25 | **Git-aware + skip-dir discovery** (`FINGERPRINT_DISCOVERY=auto`) | Old `**/*` glob walked `node_modules` (~4s); skip-dir glob skips `SKIP_DIR_NAMES` |
| 2026-09-25 | **Fingerprint path cache** (`file_stats` + `tsconfig_digest`, stat fast-path) | Warm **4.1s → 0.2s**; modify_large **~7s → ~3s**; glob was 4s, hash reads 0.14s |
| 2026-09-25 | **`PARTIAL_REINDEX_MAX_RATIO=1.0`** (disable full-shard fallback) | modify_large partial ~3s; forced full (`ratio=0.002`) ~100s |
| 2026-09-25 | **mtime rejected** (re-benchmarked) | Fingerprint-only ~2% faster than hash; warm **136s** when mtimes retouched |
| 2026-09-25 | **Fork `a985dfc`:** map Commander `options.files` → `indexFiles` (CLI `--files` was ignored) | `scip_typescript` **8.5s → 1.7s**; modify_large **~15s → ~7s** |
| 2026-09-25 | **Fork `22afafb`:** `--files` paths as `createProgram` rootNames (not full shard list) | Program sources **1760 → 662**; `createProgram` ~2s → ~1s (minor alone; matters with fix above) |
| 2026-09-25 | **scip-cli:** direct-only incremental path; in-place `index.db` upsert | Warm **~4.1s** before fingerprint cache |
| 2026-09-25 | Postprocess skip on partial part DBs (`skip_postprocess` when `index_files` set) | modify_large **~105s → ~10s** (pre-`--files` fix) |
| Earlier | Phase 1 shard reuse | Warm **~9s** vs full **~117s** |

### Fork commit (feat/partial-files)

Single squashed commit for upstream PR (`ce6e9c9` on fork; rebased onto `sourcegraph/main`):

| Piece | What |
|-------|------|
| `--files` CLI | Repeatable repo-relative paths; Commander `.files` → `.indexFiles` |
| `resolveIndexRootNames()` | Only `--files` entries passed as `createProgram` rootNames |
| Partial index loop | FileIndexer runs on subset; stderr logs loaded vs total project sources |

Stderr when partial index works:

```text
partial index: 4 document(s), 662/1760 project sources in program
+ apps/api/tsconfig.shard-03.json (139ms)
```

---

## Current architecture (settled)

- **Git incremental:** `reindex --incremental` in a git repo stores `manifest.git_commit` + per-shard `tsconfig_digest`. Shard skip when git delta empty for shard. Partial: git delta → importer closure → `--files` → upsert into live `index.db`.
- **Full reindex:** plain `reindex`, `--unversioned`, or non-git (no incremental).
- **Env:** `SCIP_CLI_FILE_INCREMENTAL=1`. Profiling: `SCIP_CLI_INDEX_TIMING=1`.

---

## Current performance (large monorepo smoke, git-only + fork `ce6e9c9`)

Numbers from a private local checkout — not reproducible from the public repo alone. Copy `scripts/smoke.local.example.json` to a gitignored `smoke.local.json` beside it and set `root` to your monorepo.

| Scenario | Wall | Dominant phases |
|----------|------|-----------------|
| **Warm 16/0** | **~0.2s** | `git_delta_scan` — git diff + per-shard tsconfig digest compare |
| **modify_large 15/1** (partial 4/1760) | **~3s** | `scip_typescript` ~1.7s + upsert ~0.1s |
| **seed_cold** | ~125s | 16 shards full index |

Example `INDEX_TIMING:summary` (modify_large):

```text
INDEX_TIMING:summary git_delta_scan=12ms parallel_index=2792ms \
  scip_typescript=1778ms scip_convert=61ms apply_updates=101ms \
  shards_reused=15 shards_dirty=1 postprocess_skipped=1 \
  notes=apps/api/tsconfig.shard-03.json:partial 4/1760 dirty=1
```

### Where time goes (modify_large)

| Phase | ~ms | Notes |
|-------|-----|-------|
| `git_delta_scan` | **~10–50** | Git subprocess + tsconfig filter per shard (no file content reads) |
| `scip_typescript` | 1700 | Was **8500** before `--files` CLI fix |
| `scip_convert` | 60 | Small partial `.scip` |
| `apply_updates` | 100 | Targeted upsert into large `index.db` |

## How we benchmark

### Gate runner

```bash
cp scripts/smoke.local.example.json scripts/smoke.local.json
# edit root + touch_large for your local monorepo checkout

scripts/bench_incremental_gate.sh --branch smoke    # warm + modify_large
scripts/bench_incremental_gate.sh --branch fixture  # mini fixture (no local config)
```

**Monorepo smoke:** `scripts/smoke.local.json` (gitignored) points at a local checkout with persisted scope (`metadata.json` lists shard tsconfigs).

**Scenarios:** `seed_cold`, `seed_warm`, `warm` (16/0), `modify_large` (touch configured `touch_large` path).

**Rules:**

- **One benchmark at a time** — no parallel gate + manual runs on the smoke checkout.
- Background runs OK; **wait for exit** before starting another or reporting numbers.
- `SCIP_CLI_INDEX_TIMING=1` for per-phase breakdown.

Gate artifacts and baselines are written under the repo's gitignored benchmark directory (see `scripts/bench_incremental_gate.py`).

### Other

| Tool | Purpose |
|------|---------|
| `scripts/bench_incremental.sh` | Smaller fixture loops |
| `scripts/bench_fingerprint_smoke.py` | monorepo warm incremental + git-delta scan timing |
| `SCIP_CLI_INDEX_TIMING=1` | `INDEX_TIMING:<phase>=Nms` on stderr |

### Tests

`tests/test_incremental_equivalence.py` — incremental fixture flows (real `scip-typescript` via npx fork).

---

## Historical results (superseded)

<details>
<summary>Gate branches before direct-only + fork fixes (2026-09-25 morning)</summary>

### fingerprint

| Scenario | hash | mtime |
|----------|------|-------|
| warm | 9.2s / 16/0 | 25.9s / 15/1 |

### phase3

| modify_large | FILE_INCREMENTAL=0 | =1 |
|--------------|-------------------|-----|
| | 104s | 26s* |

\*Postprocess-skip + broken `--files` CLI masked true partial SCIP time.

### direct vs legacy (shard DB + merge)

| Scenario | legacy | direct |
|----------|--------|--------|
| warm | 4.88s | 4.39s |
| modify_large | 15.15s | 15.88s |

Direct won warm + disk; modify_large looked slower due to SCIP variance — actually `--files` was not applied.

</details>

---

## Improvements (chronological)

1. **Phase 1 — shard reuse** — warm ~9s vs full ~117s.
2. **Phase 2 — TSC incremental** — no win; off by default.
3. **Phase 3 — `--files` + upsert** — designed for partial shard reindex (CLI wiring broken until fork `a985dfc`).
4. **Postprocess skip** — skip symbol trim on partial part DBs (`skip_postprocess` in convert).
5. **Direct-only incremental** — manifest + in-place upsert; no shard `.db` files (~40 MB cache saved).
6. **Fork rootNames** — smaller TypeScript program when `--files` set (example shard: 1760 → 662 sources).
7. **Fork `--files` CLI fix** — **largest win:** indexer ran on all shard files despite `--files` flag.
8. **Fingerprint path cache** — warm ~4s → ~0.2s (superseded by git-only incremental).
9. **Git-only incremental** — manifest stores `git_commit` + `tsconfig_digest` only; no per-file hashes.

---

## Known limitations / next work

1. **TS program closure** — 4 `--files` paths may still pull hundreds of sources into the TypeScript program (fork).
2. **Importer closure** — scip-cli expands 1 dirty file to N paths via SQLite (`expand_reindex_paths`); distinct from TS program closure.
3. **Further fork ideas** — shrink checker work on non-indexed files (hard).

---

## Reproduce (fixture only — no customer paths)

```bash
pip install -e ".[dev]"
npm link   # from scip-typescript clone on feat/partial-files (commit >= ce6e9c9)

pytest tests/test_incremental_equivalence.py
scripts/bench_incremental_gate.sh --branch fixture
```

For a large monorepo, copy `scripts/smoke.local.example.json` to `scripts/smoke.local.json` and run the smoke gate locally.
