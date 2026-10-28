---
argument-hint: "[major | minor | patch]"
---

# Release scip-cli (GitHub + PyPI)

Bump level: **`$ARGUMENTS`** — must be `major`, `minor`, or `patch`.

Run **both** scripts from repo root in order (user invoked release — do both unless they say GitHub-only or PyPI-only):

```bash
./scripts/release.sh $ARGUMENTS
./scripts/publish.sh
```

| Script | Does |
|--------|------|
| **`release.sh`** | `test.sh` → bump → commit `vX.Y.Z` → `git tag -a vX.Y.Z -m vX.Y.Z` → push → GitHub release |
| **`publish.sh`** | `test.sh` → build → PyPI (`PYPI_TOKEN` in `.env`) → pip smoke → `pip install -e ".[dev]"` |

Requires clean tree before `release.sh`. Do not hand-roll tag/gh/twine unless a script failed mid-way.

## Commit messages

- Day-to-day: sentence case, verb first — not Conventional Commits.
- Version bump: subject only `vX.Y.Z` (`release.sh`).

## Resume

- GitHub done, PyPI not: `./scripts/publish.sh` only.
- Never re-run `release.sh` or re-upload if that version is already on GitHub/PyPI.

Report: version, GitHub release URL, PyPI URL, smoke OK.
