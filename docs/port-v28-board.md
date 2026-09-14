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
| G1-go | `/tmp/scip-cli-go` | **parity done** | `6fa4d19` main |
| G1-rust | `/tmp/scip-cli-rust` | **parity done** | `9b9bdde` main |
| G1-zig | `/tmp/scip-cli-zig` | **parity done** | `4ab9536` main |

## Verify log (parent re-ran parity wave)

| Check | Python | Go | Rust | Zig |
|---|---|---|---|---|
| publish gate | pass | pass | pass (86 tests) | pass |
| cross-parity gate | n/a | `make test-cross` pass | 14 parity tests pass | `zig build test-cross` 6/6 |
| PyPI / GH release | v2.8.0 shipped | skipped | skipped | skipped |
| Python ref binary | `scip-cli==2.8.0` on PATH | yes | yes | yes (pinned in resolver) |
