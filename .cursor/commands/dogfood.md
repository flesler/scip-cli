# Dogfood analyze on this repo

Human-invoked pass before broad review. From repo root with editable `scip-cli` on PATH:

```bash
scip-cli reindex
scip-cli analyze --limit 25
scip-cli analyze --priority high --limit 25
scip-cli analyze scip_cli --limit 15
scip-cli analyze scip_cli/queries.py --limit 20
```

Interpret README § *Finding easy wins with analyze* (cycles → dead exports → same-file → stale types). Fix or extend `analyze` per `agent.mdc` § Analyze feedback loop before spawning review subagents.

Do not commit unless the user asks.
