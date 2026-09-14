# v2.8.0 multi-port board

**Goal:** Ship Python v2.8.0 (exclude globs), then port full v2.6.0→v2.8.0 gap to go/rust/zig in `/tmp`, direct-to-main, smoke-tested. Mirror GitHub releases optional.

**Frozen reference:** `/tmp/scip-cli-2.8.0-freeze.patch` (pre-commit snapshot)

## Gap to port (per mirror)

| Release | Features | Manual port |
|---|---|---|
| v2.7.0 | `analyze --check`, `dead_files`, section FP warnings | analyze/*, commands/analyze, tests |
| v2.8.0 | `reindex --exclude`, `excludeGlobs`, post-process prune | exclude, indexing, config, reindex, tests |

`scripts/sync-upstream.sh --ref v2.8.0` covers SKILL, fixtures, templates only.

## Lanes

| Lane | Path | Status | Notes |
|---|---|---|---|
| P0 Python | `~/Code/scip-cli` | in progress | commit → v2.8.0 → push → release |
| G1-go | `/tmp/scip-cli-go` | pending | direct-to-main |
| G1-rust | `/tmp/scip-cli-rust` | pending | direct-to-main |
| G1-zig | `/tmp/scip-cli-zig` | pending | direct-to-main |

## Verify log

| Check | Python | Go | Rust | Zig |
|---|---|---|---|---|
| scripts/test.sh | | | | |
| exclude dogfood | | | | |
| analyze --check | n/a | | | |
| readonly /iterate review | | | | |
