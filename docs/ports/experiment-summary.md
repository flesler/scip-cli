# AI Coding Language Comparison - Incremental Feature Experiment

## Task: Add `--freq` Flag to Symbols Command

All four languages were tasked with adding a `--freq` flag that sorts symbols by frequency of occurrence (most common first), then alphabetically for ties.

---

## Side-by-Side Results

| Metric | Python | Go | Rust | Zig |
|--------|--------|-----|------|-----|
| **Elapsed Time** | ~3 minutes | ~8 minutes | ~25-36 minutes | ~18-19 minutes |
| **Tool Calls** | ~15 calls | ~25 calls | ~35 calls | ~45 calls |
| **Problems Encountered** | 0 | 2 (sed over-matching, formatting) | 1 (type complexity lint) | 4 (API instability, memory management, file corruption, type issues) |
| **New Tests Added** | 3 tests | 3 tests | 4 tests | Manual verification only |
| **Gate Status** | ✅ All 298 tests pass | ✅ All 24 test packages pass | ✅ All 57 tests pass, clippy clean | ⚠️ Build passes, pre-existing leak |
| **AI Friendliness** | 10/10 - Trivial | 8/10 - Straightforward | 7/10 - Moderate friction | 5/10 - Significant challenges |

---

## Detailed Analysis by Language

### 🐍 Python (Baseline)
**Time**: 3 minutes  
**Friction**: None

Python completed the task effortlessly:
- Simple `Counter` + `sorted()` implementation
- No compilation step needed
- Tests added in dedicated test file
- All existing tests still pass

**Key Insight**: Zero friction - AI can implement features as fast as it can type. No conceptual overhead, just straightforward logic.

---

### 🥇 Go (Best Balance)
**Time**: 8 minutes  
**Friction**: Minor (tooling issues, not language)

Go was smooth once past initial setup:
- Type system caught missing import immediately
- Pointer/value confusion avoided with safe type assertion
- `sortByFrequency()` function is pure and easily testable
- Sed tool caused one issue (over-matched multiple command maps)

**Problem Example**: Initial sed command added `"freq": *freq,` to ALL command maps instead of just symbols. Required backup restore.

**Key Insight**: Fast feedback loop (seconds to compile) + clear compiler errors = efficient iteration. The 8-minute time includes fixing the sed mistake.

---

### 🥈 Rust (Good but Slower)
**Time**: 25-36 minutes  
**Friction**: Moderate (clippy lint, integration test setup)

Rust required more careful planning:
- Clippy complained about complex tuple type → fixed with type alias
- Integration tests failed due to fixture setup → pivoted to unit tests
- **Zero borrow checker issues** (surprising!)

**Why no borrow checker problems?**
- Working with owned `Vec` data (no borrowing needed)
- HashMap has simple ownership (String keys, usize values)
- Sorting uses immutable borrows from HashMap while owning sorted Vec

**Key Insight**: Once patterns are established in codebase, incremental features are much easier than full migrations. The lack of borrow checker issues here contrasts sharply with the original migration (which had 5+ ownership problems).

**Quote from agent**: *"Adding a single CLI flag to an existing codebase worked well because... CLI argument parsing naturally produces owned Strings."*

---

### 🥉 Zig (Challenging)
**Time**: 18-19 minutes  
**Friction**: High (API instability, memory management, file corruption)

Zig faced multiple hurdles despite being fastest after Python:

**Problems encountered:**
1. **API instability**: `std.ArrayList.init(allocator)` doesn't work in 0.17.0-dev → must use `.empty` pattern
2. **Type boundaries**: Struct defined inside function couldn't be referenced from module-level comparator → required inline definition
3. **Memory management bugs**: StringHashMap takes ownership of keys, but ArrayList also needs them → solution: always dupe keys using `gop.key_ptr.*`
4. **File corruption**: Using sed + concatenation caused duplicate lines → rewrote entire file cleanly

**Key Insight**: Despite fast compilation (2-5 seconds), Zig's API instability in dev versions and manual memory management create significant friction. The 18-minute time is impressive given the challenges, but represents 6x Python's time and 2.25x Go's time.

**Quote from agent**: *"The biggest conceptual hurdle was managing string ownership between HashMap and ArrayList. Had to carefully track which allocator owned each string and when to dupe vs free."*

---

## Key Findings

### 1. Tooling Speed Dominates Iteration Efficiency
- **Python**: Instant feedback (no compilation)
- **Go**: Seconds-fast compilation enables rapid fixes
- **Rust**: Moderate compilation but excellent error messages
- **Zig**: Fast compilation but cryptic error messages ("mutable not accessible from here")

### 2. Memory Management Complexity Correlates with Development Time
Languages requiring explicit memory management took significantly longer:
- **No manual memory mgmt** (Python, Go): 3-8 min
- **Ownership model** (Rust): 25-36 min (but zero actual borrow checker issues)
- **Manual allocation** (Zig): 18-19 min (with multiple iterations on memory ownership)

### 3. Type System Friction Depends on Task Type
- **Full migration**: Type systems cause significant friction (Go: 25%, Rust: 25%, Zig: 9%)
- **Incremental feature**: Type systems mostly helpful (Go: caught missing import, Rust: clippy improved readability)

### 4. API Stability Critical for AI Productivity
Zig's API instability consumed disproportionate time:
- Agent spent time figuring out correct initialization pattern (`.empty` vs `.init`)
- Couldn't rely on documentation or training data
- Had to read std source or trial-and-error

### 5. Test Addition Ease Varies Wildly
- **Python**: Simple pytest fixtures, 3 tests in minutes
- **Go**: Pure functions easy to test, 3 tests quickly
- **Rust**: Integration tests hard (fixture setup), pivoted to unit tests (4 tests)
- **Zig**: No automated test framework, manual verification only

---

## Updated Rankings

Based on **incremental feature development** (not full migration):

### 🥇 Gold: Python (10/10)
- Baseline for all other languages
- Zero friction, instant feedback
- Best for rapid prototyping and feature additions

### 🥈 Silver: Go (8/10)
- Close to Python in ease, slightly slower due to compilation
- Type system helpful without being obstructive
- Excellent for team development and maintainability

### 🥉 Bronze: Rust (7/10)
- Higher initial time investment but pays off in correctness
- Once patterns are learned, incremental features are manageable
- Best choice if safety/performance matter for production

### 4th Place: Zig (5/10)
- Feasible but challenging due to API instability
- Manual memory management creates cognitive load
- Only suitable when binary size/control are critical

---

## Surprising Insights

### Rust Performed Better Than Expected
The original migration analysis showed Rust with 21% borrow checker problems, but this task had **zero** ownership issues. This suggests:
- **Task type matters**: Incremental features often work with owned data
- **Established patterns help**: Clear code structure guides AI effectively
- **Compiler guidance works**: When stuck, Rust compiler points to exact fix

### Zig Faster Than Rust Despite More Problems
Zig completed in 18-19 min vs Rust's 25-36 min, even though Zig had 4 problems vs Rust's 1. This suggests:
- **Fast compilation compensates for complexity**: 2-5 second rebuilds enable rapid iteration
- **Parallel problem-solving**: AI can fix multiple small issues faster than waiting for one big compilation

### Go's Sed Problem Reveals Tooling Gap
Go agent used `sed` for multi-line edits and over-matched. This reveals:
- **LLMs need better bulk-edit tools**: Current approach (read_file + edit_file) is tedious for many changes
- **Sed is dangerous for AI**: One regex can corrupt multiple files
- **Recommendation**: Provide "apply patch" or "rewrite section" tools

---

## Recommendations by Use Case

### For Rapid Prototyping / Feature Additions
**Choose**: Python > Go > Rust > Zig  
**Reason**: Lowest friction time per feature, fastest iteration

### For Production Code Quality
**Choose**: Rust > Go > Zig > Python  
**Reason**: Safety guarantees prevent runtime bugs, maintainability matters long-term

### For Team Collaboration
**Choose**: Go > Python > Rust > Zig  
**Reason**: Simple patterns, consistent formatting, minimal learning curve

### For Binary Size / Deployment Constraints
**Choose**: Zig > Rust > Go > Python  
**Reason**: Minimal dependencies, single executable, no runtime

---

## Methodology Notes

This experiment tested **incremental feature addition** to mature codebases, not full migrations. Results may differ for:
- Greenfield projects (starting from scratch)
- Bug fixes (vs new features)
- Refactoring (changing existing code)
- Performance optimization (requiring deep understanding)

Each agent worked sequentially (Python → Go → Rust → Zig) to avoid API throttling. All agents received identical instructions and reporting requirements.

---

*Experiment conducted on June 30, 2026. Total combined time: ~54-66 minutes across all four languages.*
