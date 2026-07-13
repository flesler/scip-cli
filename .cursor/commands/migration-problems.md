# Document migration problems

Review this session (and any ports you just touched) and append **only** language / tooling walls to `migration-problems.md`.

## Where to write

| Repo | File |
|------|------|
| `scip-cli-go` | `migration-problems.md` |
| `scip-cli-rust` | `migration-problems.md` |
| `scip-cli-zig` | `migration-problems.md` |
| `scip-cli` (Python) | Usually **none** — Python is the reference, not a port. Only add a note if the user asks. |

If the workspace is one of the ports, edit that repo’s file. If several ports were touched, update each relevant file. Match existing numbering and section style in that file.

Do **not** invent entries from first principles — only document walls you (or a subagent) actually hit in this work.

---

## Why this file exists

These repos are an experiment: **which language is better for AI to code in?**

`migration-problems.md` is evidence for that question. A reader should learn something about the **language, compiler, stdlib, or ecosystem tooling** — not about scip-cli product bugs or “we forgot a branch.”

Ask before writing:

> *If we ported a different CLI tomorrow, would this entry still teach something about coding in this language with an AI?*

If **no** → do not add it.

---

## What TO put (include)

Fundamental friction that slows or confuses an AI agent because of the **language or its tools**:

| Category | Examples |
|----------|----------|
| **Compiler / type system** | Borrow checker traps; Zig shadowing rules; Go’s `module/v2` path rules; errors that force many tiny fix loops |
| **Stdlib / API drift** | Zig 0.17 removed `std.fs.cwd`; training data assumes older APIs; crate APIs that don’t match Python intuition (`regex` no lookbehind) |
| **Tooling loop cost** | Full `zig build -Doptimize=ReleaseFast` ~25s+ → fewer AI iterations; `gofmt`/`cargo fmt` rewrite every commit; clippy/rustc so strict the agent flails for N cycles |
| **Ecosystem surprises** | CGO vs pure-Go SQLite; `anyhow::bail!` prefixes user errors; package name vs import path traps |
| **Agent × language interaction** | Persistent shell + language-specific env scripts hanging; test runners with no skip → vacuously green |

Entry shape (adapt to the file’s existing voice):

- **Symptom** — what the agent saw (compile error, hang, parity fail)
- **Cause** — language/tooling root cause (not “we missed a line of business logic”)
- **Lesson** — what an AI (or human) should remember next time in this language
- Optional: time sink / iteration count if it was large

Prefer **one sharp entry** over a dump of every compile error.

---

## What NOT to put (exclude)

| Do not document | Why |
|-----------------|-----|
| Product / logic bugs (“search printed duplicates”, “forgot DER fallback”) | Same bug in any language; says nothing about Go vs Rust vs Zig |
| “We forgot to port X” / incomplete ports | Process failure, not language |
| TODOs, wishlists, backlog | Wrong file (`todo.md` / docs) |
| One-off typos, wrong SQL, missed edge cases in *our* code | Not language-fundamental |
| Parity mismatches that are just divergent implementations | Unless caused by a real language constraint |
| Generic “AI made a mistake” | Only if the language *systematically* induces that mistake (e.g. trained on old Zig stdlib) |

**Litmus test:** Removing scip-cli from the story — does the entry still make sense?
- ✅ “Zig ReleaseFast builds dominate the edit–compile loop”
- ❌ “Search must dedupe Prisma typeLiterals by file:line”

---

## How to run this command

1. Skim the conversation / diffs for walls that burned time.
2. Open the target `migration-problems.md`; read the last few entries so style and numbers match.
3. For each candidate, apply the litmus test. Drop application-logic noise.
4. Append new entries (or fix an existing entry if you previously wrote the wrong *kind* of note).
5. Do **not** commit unless the user asks. Briefly tell the user what you added (or that nothing qualified).

If nothing in the session qualifies, say so — **empty is better than polluting the experiment.**
