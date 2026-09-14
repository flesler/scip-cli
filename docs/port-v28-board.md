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

| Lane | Path | Status | SHA |
|---|---|---|---|
| P0 Python | `~/Code/scip-cli` | **done** | `5d00007` v2.8.0 PyPI + GH release |
| G1-go | `/tmp/scip-cli-go` | **done** | `342f4fb` main, no GH release |
| G1-rust | `/tmp/scip-cli-rust` | **done** | `8620ddb` main, no GH release |
| G1-zig | `/tmp/scip-cli-zig` | **done** | `6b8bedf` main, no GH release |

## Verify log (parent re-ran)

| Check | Python | Go | Rust | Zig |
|---|---|---|---|---|
| scripts/test.sh | pass | pass | pass (83 tests) | pass |
| PyPI / GH release | v2.8.0 shipped | skipped | skipped | skipped |
| exclude dogfood | pass | pass (agent) | pass (agent) | pass (agent) |
| analyze --check | n/a | pass | pass | pass |
| readonly /iterate review | n/a | pass | Bugbot clean | 1 fix kept |
