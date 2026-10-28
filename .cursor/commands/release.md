---
argument-hint: "[major | minor | patch]"
---

# Release scip-cli (tag + GitHub)

Bump level: **`$ARGUMENTS`** — must be exactly `major`, `minor`, or `patch`. Compute the next semver from `scip_cli/__init__.py` (same rules as `scripts/publish.sh`: patch +1; minor +1 and patch 0; major +1 and minor/patch 0). Tag and release **`vX.Y.Z`** for that computed version.

## Commit messages (this repo)

- **Day-to-day:** sentence case, verb first — e.g. `Add entrypoint fixtures`, `Pass indexer binary name to npx fallback`. **Not** Conventional Commits (`feat(scope):`, `chore:`, …).
- **Version bump commit:** subject **only** `vX.Y.Z` (same string as the tag), e.g. `v3.2.0`.

Do not commit, tag, or push unless the user invoked this release command.

## Preflight

1. Repo root; working tree clean before the bump commit.
2. `./scripts/test.sh`
3. If `$ARGUMENTS` is missing or not `major`/`minor`/`patch`, stop and ask.
4. After bump, `git rev-parse "vX.Y.Z"` must fail (tag must not exist yet).

## Bump version

Use the bump logic in `scripts/publish.sh` (or run that script’s Python block with `BUMP_LEVEL=$ARGUMENTS`). Then:

```bash
git add scip_cli/__init__.py
git commit -m "vX.Y.Z"
```

## Tag (non-interactive — never open the editor)

Always pass **both** tag name and message on the command line:

```bash
git tag -a "vX.Y.Z" -m "vX.Y.Z"
```

Do **not** run bare `git tag vX.Y.Z` (Git may open an editor for the annotation).

Push branch and tag:

```bash
git push origin HEAD "vX.Y.Z"
```

## GitHub release (`gh`)

Read `~/.claude/skills/gh/references/releases.md`. Use the repo scripts:

```bash
GH_SCRIPTS="${GH_SCRIPTS:-$HOME/.claude/skills/gh/scripts}"
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo flesler/scip-cli)"

"$GH_SCRIPTS/release-notes.sh" X.Y.Z --install '```bash
pip install scip-cli=={{VERSION}}
```'

"$GH_SCRIPTS/sync-github-release.sh" "$REPO" X.Y.Z \
  --install '```bash
pip install scip-cli=={{VERSION}}
```' \
  --execute
```

**Do not** run `gh release create` by hand unless the user rejects the script path. **Do not** upload PyPI (`twine`) or run full `./scripts/publish.sh` unless the user explicitly asks.

Report: bump level, new version, tag pushed, release URL, PyPI skipped unless requested.
