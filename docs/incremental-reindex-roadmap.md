# Incremental reindex (settled)

## Model

Two modes only:

| Mode | Trigger | Behaviour |
|------|---------|-----------|
| **Git incremental (default)** | `reindex` in a git TypeScript repo (not `--unversioned`) | Manifest stores `git_commit` + per-shard `tsconfig_digest`. Shard skip when git delta empty for shard. Partial reindex via `--files` on dirty paths ∪ importers. Upsert into live `index.db`. |
| **Full reindex** | `--no-incremental`, `--fresh`, `--unversioned`, or non-git | Clears shard manifest. Full indexer per shard. |

**Removed:** content hashes, stat fast-path, `SCIP_CLI_FINGERPRINT=*`, `SCIP_CLI_FINGERPRINT_DISCOVERY=*`, `SCIP_CLI_FINGERPRINT_CACHE`, manifest `file_hashes` / `fingerprint`.

## Git delta (change detection)

Since `manifest.git_commit`:

1. `git diff <commit>..HEAD` (committed)
2. `git diff` (unstaged)
3. `git diff --cached` (staged)
4. `git ls-files --others --exclude-standard` (untracked)

`git mv` is treated as **delete old path + add new path** (implementation disables git rename folding so the old path lands in the removal set).

Deletions flow to `remove_documents_by_paths`. Modifications/additions filtered through tsconfig include/exclude, then importer closure for partial scope.

## Manifest v4

```json
{
  "version": 4,
  "git_commit": "<HEAD at last successful index>",
  "shards": {
    "packages/a/tsconfig.json": {
      "tsconfig_digest": "<hex sha256 — see below>"
    }
  }
}
```

### `tsconfig_digest`

Per-shard **SHA-256 hex** of the tsconfig *chain* (not source files). Built in `tsconfig_chain_digest()`:

1. Shard key (`packages/a/tsconfig.json` posix path) + `\0`
2. For each file in `extends` chain (root tsconfig first, then parents), in order:
   - absolute path string + `\0`
   - raw file bytes + `\0`

Any change to the shard tsconfig or an extended parent (include/exclude/files, compiler options, path) changes the digest → **full shard reindex** even when git reports no file changes.

Shard skip: `tsconfig_digest` unchanged **and** no paths in git delta intersect this shard (via tsconfig include/exclude rules).

## Env

| Variable | Default | Purpose |
|----------|---------|---------|

## Benchmarks

See [benchmarks.md](benchmarks.md).

```bash
scripts/bench_incremental_gate.sh --branch fixture
scripts/bench_fingerprint_smoke.py   # requires local smoke.local.json
SCIP_CLI_INDEX_TIMING=1 scip-cli reindex
```

## Upstream (scip-typescript)

| | |
|---|---|
| **Upstream** | https://github.com/sourcegraph/scip-typescript |
| **Fork** | https://github.com/flesler/scip-typescript (`feat/partial-files`, `--files` only) |
| **Pin** | `ce6e9c9` on `feat/partial-files` |
