# Run scip-cli tests

1. Read `.cursor/skills/test/SKILL.md`.
2. From repo root, run the narrowest suite that covers the user's change (or their named target):
   - Default before commit: `scripts/test.sh`
   - CLI / fixture only: `pytest tests/test_e2e.py tests/test_e2e_analyze_patterns.py -q`
   - User gave a pytest node id or file: run that with `-q`
3. On failure: fix, re-run the same command; do not claim done until green.
4. Reply with command run, pass/fail, and one line on what failed if applicable.

Do not commit unless the user asks.
