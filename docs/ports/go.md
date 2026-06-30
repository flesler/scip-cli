# Go AI Coding Analysis

## Migration Overview
- **Total estimated migration time**: ~5 hours 40 minutes (340 minutes) of documented friction time across 49+ distinct problems
- **Number of distinct problems encountered**: 49 major issues documented, plus numerous smaller fixes
- **Key success metrics**: 
  - Full Python-to-Go parity achieved on sample-project fixture
  - All cross-comparison tests passing (version, search, code, refs, symbols)
  - Binary functional with `scip-cli-go 2.3.0`

## Problem Categories

### Type System Issues

**Time cost**: ~85 minutes across multiple sessions

The type system caused significant friction during migration, particularly around:

1. **Pointer vs value mismatches**: `ResolveMaxDefLines` takes `*int` not `int`; `FormatLineRange` takes `*int` not `int`. AI repeatedly tried arithmetic on `*int` pointers without dereferencing. (~10 minutes fixing)

2. **Generic function adoption**: `output.LimitAndWarn` initially took `[]interface{}` but callers passed typed slices (`[]queries.SymbolResult`, `[]string`, `[]searchResult`). AI needed to update to generics `LimitAndWarn[T any](items []T, limit int, label string) []T`. (~10 minutes)

3. **SQL.NullString confusion**: Test compilation failed with `invalid operation: res[0].DisplayName != "myFunc"` due to mismatched types `sql.NullString` and untyped string. AI didn't understand Go's nullable SQL types. (~5 minutes per instance)

4. **Package naming conflicts**: Directory `internal/sql` named package `sqlhelp` to avoid stdlib conflict. Files imported inconsistently — some with alias `sqlhelp "github.com/sourcegraph/scip-cli-go/internal/sql"`, some without. This flip-flopping consumed ~45+ minutes across sessions as the single largest type-system blocker. Root cause: directory name ≠ package name is a Go footgun.

5. **Undefined references after refactoring**: After refactoring `getExactRefs` to fix chunk grouping, left references to undefined `chunks` variable. Compiler caught immediately but required multiple iterations. (~5 minutes)

**Pattern**: Type errors were caught quickly by compiler (strength), but AI often guessed at signatures instead of checking call sites first. The strict type system prevented runtime errors but slowed initial porting velocity significantly.

### API/Learning Curve Issues

**Time cost**: ~75 minutes

LLM knowledge gaps appeared in several areas:

1. **SQLite driver confusion**: `indexing.go` imported `github.com/mattn/go-sqlite3` (CGO-based) while `merge.go` imported `modernc.org/sqlite` (pure Go). AI used outdated or inconsistent SQLite drivers. (~15 minutes)

2. **ESCAPE syntax in SQL**: Python uses `ESCAPE '\\'` in SQL strings. In Go **backtick** raw strings, `\\` is two literal backslashes → SQLite error "ESCAPE expression must be a single character". AI didn't understand Go string literal escaping differences. (~40 minutes — single largest API issue)

3. **CLI flag parsing**: `search greet --limit 3` treated `--limit` as a search pattern because Parse() did `append(argv[i:]...); break` on first non-flag. AI assumed Python-style argparse behavior. (~15 minutes)

4. **Subpackage assumptions**: `commands/analyze.go` imported non-existent subpackages `internal/analyze/sections` and `internal/analyze/targets`. AI assumed Python module structure would map directly to Go packages. (~20 minutes)

5. **Go version format**: `go.mod` specified `go 1.25.0` but system had Go 1.18.1. Error message "invalid go version '1.25.0': must match format 1.23" was confusing. AI didn't recognize that Go 1.25 doesn't exist yet (project actually needs Go 1.21+). (~15 minutes)

6. **Missing wrapper functions**: `commands/analyze.go` called `analyze.ParsePriorities`, `analyze.NewRowBudget`, `analyze.RunProjectSections`, etc. — none existed. AI assumed these were part of the analyze package based on Python structure. (~15 minutes)

**Pattern**: AI's training data included outdated Go APIs (especially for SQLite and CLI parsing). Documentation quality was good, but AI didn't always read it before coding.

### Tooling Friction

**Time cost**: ~40 minutes + ongoing

Tooling speed was generally acceptable but had specific pain points:

1. **Compilation cascade failures**: When one package failed (e.g., `internal/cross` depends on `internal/commands`), all dependent packages couldn't compile. AI saw 4-5 failing packages but root cause was single file. (~5 minutes diagnosing each occurrence)

2. **golangci-lint not installed**: Project expected `golangci-lint` but it wasn't in PATH. AI had to install manually with `go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest`. (~5 minutes)

3. **Lint configuration tuning**: Initial lint run produced many violations. AI configured `.golangci.yaml` to exclude common patterns (`.*Close`, `os.Remove`, `Exec`, `Rollback`, `Scan`, `Sscanf`) and ignore `errcheck` in `_test.go` files. Multiple iterations needed. (~10 minutes)

4. **Test binary prerequisite**: Cross-comparison tests expected `bin/scip-cli-go` to exist but didn't build it first. AI added `go build` step in `TestMain`. (~5 minutes)

5. **Go toolchain version management**: System had Go 1.18.1; project needed Go 1.21+. Installing to `/home/flesler/.local/go-sdk/go/` and updating PATH worked but was manual. (~15 minutes)

**Positive**: Compilation speed was fast (seconds for most changes). `go vet` was clean after fixes. No complaints about test execution speed once tests ran.

### Ecosystem Challenges

**Time cost**: ~30 minutes

Package ecosystem was mostly mature but had gaps:

1. **Missing dependency in go.mod**: `modernc.org/sqlite` not added to `go.mod` initially. AI needed to run `go get modernc.org/sqlite`. (~5 minutes)

2. **Standard library coverage gaps**: No built-in CLI flag parser comparable to Python's argparse. AI used basic `flag` package which required manual positional argument handling. (~15 minutes for flag parsing issues)

3. **Third-party library availability**: Good for SQLite (`modernc.org/sqlite`), but no direct equivalent to Python's pytest fixtures. AI created custom test helpers (`testdb/builder.go`, `fixture_catalog.py` adaptation). (~10 minutes)

**Positive**: Standard library covered most needs (io, os, filepath, strings). Third-party packages available via Go modules when needed.

### Language Strictness Issues

**Time cost**: ~60 minutes

Go's rigidity caused frequent corrections in predictable ways:

1. **Import path consistency**: Every import must use exact package path. AI frequently used wrong paths (`internal/sqlhelp` instead of `internal/sql`) or forgot aliases. Each error caught by compiler but required iteration. (~20 minutes cumulative)

2. **Function signature matching**: All call sites must agree on signatures before implementation. AI implemented `ResolveDefLocation` stub that didn't match needed signature, then updated. (~15 minutes)

3. **No optional parameters**: Unlike Python, Go requires explicit parameters. AI tried calling functions with fewer arguments than required. (~10 minutes)

4. **Error handling verbosity**: Every error check requires `if err != nil`. AI sometimes ignored errors (e.g., `rows.Scan` failure with `continue`) leading to silent data loss. Later fixed with proper error propagation. (~15 minutes)

5. **Directory name ≠ package name**: Footgun where directory `internal/sql` could have package name `sqlhelp`. AI confused the two repeatedly until directory was renamed. (~45 minutes total across sessions)

**Pattern**: Strictness prevented runtime bugs but slowed development. AI spent more time satisfying compiler than writing logic.

## Transcript Evidence

### Type System Struggles

> "All three commands failed with the same error: `go: errors parsing go.mod: /home/flesler/Code/scip-cli-go/go.mod:3: invalid go version '1.25.0': must match format 1.23`"

> "`code.go` type mismatches with output package: `ResolveMaxDefLines` takes `*int` not `int`; `FormatLineRange` takes `*int` not `int`; `endLine - startLine` on `*int` pointers."

> "Type literal fields like `Options.verbose` have no `defn_enclosing_ranges` row; Python uses `resolve_def_location` with source-file scan fallback. Go `code` called `queries.GetDefLocation` only → `Warning: no definition location`."

### API Learning Curve

> "Python uses `ESCAPE '\\'` in SQL strings. In Go **backtick** raw strings, `\\` is two literal backslashes → SQLite error 'ESCAPE expression must be a single character'. Time Lost: ~40 minutes"

> "`search greet --limit 3` treated `--limit` as a search pattern because Parse() did `append(argv[i:]...); break` on first non-flag."

> "`commands/analyze.go` imported non-existent subpackages `internal/analyze/sections` and `internal/analyze/targets`. The analyze functionality was split across multiple Python files but in Go these should be part of the main `analyze` package."

### Tooling Frustrations

> "Build failed before tests ran — checking the project's Go version requirement and available toolchains. `make test` **failed before any tests ran** (exit code 2). Error: `../../go/pkg/mod/golang.org/x/sys@v0.44.0/unix/syscall_linux.go:16:2: package slices is not in GOROOT (/usr/lib/go-1.18/src/slices)`"

> "When one package failed (e.g., `internal/cross` depends on `internal/commands`), all dependent packages couldn't compile. AI saw 4-5 failing packages but root cause was single file."

### Workarounds and Adaptations

> "Actually, let me reconsider the approach. The Python code uses generic `fetch_all` returning tuples. Let me rewrite with a cleaner Go-idiomatic approach using a simple row scanner."

> "I need to fix the compilation errors quickly. Let me batch the fixes."

> "Root cause: Directory name != package name is a footgun in Go. Fix: Renamed directory to `internal/sqlhelp`. Import is always `\"github.com/sourcegraph/scip-cli-go/internal/sqlhelp\"` — no alias needed. Never flip again."

## Strengths Observed

### What Worked Well for AI Coding in Go

1. **Fast feedback loop**: Compilation took seconds, not minutes. `go build ./...` caught errors immediately. AI could iterate quickly once it learned to compile after each package.

2. **Clear error messages**: Go compiler errors are specific and actionable. "undefined: chunks" or "invalid operation" pointed directly to the problem line.

3. **Simple patterns**: Go's simplicity meant less conceptual overhead. Once AI learned the right pattern (e.g., pointer dereferencing, package imports), it applied consistently.

4. **Good standard library**: Most needs covered by `io`, `os`, `filepath`, `strings`, `database/sql`. Minimal third-party dependencies required.

5. **Deterministic formatting**: `gofmt` eliminated style debates. AI didn't waste time on formatting decisions.

6. **Strong tooling integration**: `go vet`, `golangci-lint`, and compiler diagnostics integrated well. Issues caught early in development cycle.

## Weaknesses Identified

### Major Pain Points That Repeatedly Caused Friction

1. **Package naming confusion**: Directory name ≠ package name caused ~45 minutes of wasted time. AI couldn't intuit this Go quirk from Python experience.

2. **Type system verbosity**: Pointer vs value, `*int` vs `int`, `sql.NullString` vs `string` — small type mismatches consumed ~85 minutes total. Strict typing prevented bugs but slowed initial development.

3. **API knowledge gaps**: LLM trained on outdated Go APIs (especially SQLite drivers, CLI parsing). ~75 minutes spent learning correct APIs through trial-and-error.

4. **Signature coordination burden**: All call sites must agree on function signatures. AI implemented functions before checking all callers, leading to ~20 minutes of rework.

5. **Error handling boilerplate**: Verbose `if err != nil` checks led to AI ignoring errors (silent data loss bugs). Required later audit to fix.

6. **Cross-file API mismatches**: Files ported independently assumed slightly different signatures. Each command file made different assumptions about output/analyze packages. Root cause: insufficient grep-before-implement discipline.

## Quantitative Summary

- **Estimated total time lost to friction**: 5 hours 40 minutes (340 minutes) across 49 documented problems
- **Most common issue type**: Type system mismatches (~85 minutes, 25% of total friction time)
- **Biggest single blocker**: Package naming conflict (`internal/sql` directory with `sqlhelp` package name) — ~45 minutes across sessions
- **Number of type-related errors**: 12+ distinct type mismatch incidents documented
- **Number of API/documentation issues**: 8+ instances of LLM using outdated or incorrect APIs
- **Compilation-related delays**: 5+ instances of cascade failures masking root cause
- **Tooling setup time**: ~40 minutes for linter installation, version management, configuration

### Issue Distribution

| Category | Time Cost | Percentage |
|----------|-----------|------------|
| Type System | ~85 min | 25% |
| API/Learning Curve | ~75 min | 22% |
| Language Strictness | ~60 min | 18% |
| Tooling Friction | ~40 min | 12% |
| Ecosystem | ~30 min | 9% |
| Other/Unspecified | ~50 min | 14% |

### Key Insight

Go's type system and strictness prevented runtime bugs but significantly slowed AI-assisted development velocity. The AI spent approximately **47% of friction time** (160 of 340 minutes) dealing with type-related issues and language rigidity. For comparison, Rust's type system (analyzed separately) may provide similar guarantees with better ergonomics for AI agents through clearer error messages and trait-based abstractions.

However, Go's strengths — fast compilation, clear error messages, simple patterns, and excellent tooling integration — made it viable for AI coding once the learning curve was overcome. The migration succeeded despite friction, achieving full Python parity on the test fixture suite.

### Recommendation for Future Migrations

Go is **moderately suitable** for AI-assisted coding when:
- ✅ Fast compilation feedback is prioritized over expressive type systems
- ✅ Simple, uniform code patterns are preferred
- ✅ Strong standard library coverage reduces third-party dependencies
- ⚠️ AI is explicitly instructed to check all call sites before implementing functions
- ⚠️ Package naming conventions are clearly documented upfront
- ❌ Complex generic programming or metaprogramming is required (Go has limited support)

For AI agents specifically, Go's predictability and fast feedback loop partially offset its verbosity and strictness. However, the high friction time (5.7 hours for a medium-sized project) suggests that languages with better type inference and clearer API documentation may yield higher AI productivity.
