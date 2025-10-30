# Strategy System Cleanup Plan

**Date:** 2025-10-30
**Status:** Implementation Plan
**Priority:** HIGH - Documentation is misleading

## Executive Summary

The codebase has **orphaned strategy infrastructure** that is never used in production but documented as active. This creates confusion about how the tool actually works.

**Reality:** git-autosquash uses a **single split-commit approach** via RebaseManager.

**Documentation:** Claims multiple strategies (index/legacy/worktree) with fallback logic.

## Current State Analysis

### Production Code Path (What Actually Runs)

```
main.py line 225:
    rebase_manager.execute_squash(approved_mappings, ignored_mappings, context)
        ↓
RebaseManager.execute_squash() (rebase_manager.py:49-162)
    ├─ Approved hunks → _apply_hunks_to_commit()
    │   ├─ Cherry-pick split commits (lines 673-700) ← PRIMARY
    │   └─ Patch-based fallback (lines 702-710) ← FALLBACK
    └─ Ignored hunks → _process_source_with_ignored_hunks()
        └─ Preserve in split commits for manual review (lines 1866-1919)
```

**That's it. No other execution paths in production.**

### Orphaned Code (Never Called from main.py)

| File | Lines | Purpose | Status | Used By |
|------|-------|---------|--------|---------|
| `git_native_complete_handler.py` | 287 | Multi-strategy orchestrator | ORPHANED | Tests only |
| `git_native_handler.py` | 588 | Index strategy for ignored hunks | ORPHANED | Tests only |
| `cli_strategy.py` | 181 | Strategy management commands | MISLEADING | Configures nothing |
| `strategy_base.py` | 131 | Abstract base class | ORPHANED | Dead code only |

**Total:** 1,187 lines of orphaned strategy infrastructure

### Test Files Depending on Orphaned Code

| Test File | Lines | Tests | Purpose |
|-----------|-------|-------|---------|
| `test_git_native_handler.py` | 706 | ~25 | Tests GitNativeIgnoreHandler directly |
| `test_git_native_complete_handler.py` | 391 | ~15 | Tests GitNativeCompleteHandler directly |
| `test_git_native_integration.py` | 230 | ~8 | Tests index strategy integration |
| `test_production_optimizations.py` | ~50 | 3 | Tests handler caching |
| `test_security_edge_cases.py` | ~30 | 2 | Tests handler path security |

**Total:** ~1,327 lines of tests for orphaned code

---

## Why This Happened

### Historical Context

**Phase 1: Original Design (multiple strategies)**
- Worktree strategy
- Index strategy
- Legacy strategy
- GitNativeCompleteHandler to orchestrate them

**Phase 2: Worktree Removal**
- Worktree strategy removed (commit d150fa8)
- Documentation updated to say "simplified architecture"
- BUT: Index/legacy strategy infrastructure left in place

**Phase 3: Split-Commit Addition (recent)**
- Added HunkCommitSplitter for --source cases
- RebaseManager became the de-facto orchestrator
- GitNativeCompleteHandler never integrated into main flow

**Phase 4: Split-Commit Expansion (today)**
- Split-commit now used for ALL cases
- Patch-based is just a fallback
- Strategy system completely bypassed

**Result:** Orphaned infrastructure that was never removed.

---

## Cleanup Options

### Option A: Aggressive Cleanup (Recommended)

**Remove:**
- Delete all 4 orphaned strategy files
- Delete all 5 test files for orphaned code
- Remove cli_strategy.py integration from main.py
- Update all documentation

**Benefits:**
- Clean, honest codebase
- Documentation matches reality
- -2,500 lines of dead code removed
- Clear architecture

**Risks:**
- Large change
- Loses test coverage for unused code (acceptable)

**Effort:** 2-3 hours

### Option B: Conservative Cleanup (Safer)

**Keep files but mark as deprecated:**
- Add deprecation notices to all 4 strategy files
- Keep tests (they still provide some git operation testing)
- Remove cli_strategy commands from main.py
- Update documentation to reflect reality

**Benefits:**
- Safer incremental approach
- Keep tests as integration tests
- Can delete files later if confident

**Risks:**
- Confusing to have deprecated code in codebase
- Tests test code that doesn't run

**Effort:** 1-2 hours

### Option C: Minimal Documentation Update (Quick)

**Only update documentation:**
- Fix CLAUDE.md to say "single split-commit strategy"
- Update README/architecture.md to explain split-commit
- Leave orphaned code as-is (for now)

**Benefits:**
- Quick fix (30 minutes)
- Documentation accurate
- No test breakage risk

**Risks:**
- Leaves dead code in codebase
- Future confusion remains

**Effort:** 30 minutes

---

## Recommended Approach: Option B (Conservative)

Given the scope and test dependencies, I recommend **Option B** for now:

### Phase 1: Documentation Updates (Immediate)

1. **Update CLAUDE.md:**
   - Remove GitNativeCompleteHandler from component hierarchy
   - Remove "Strategy Management Commands" section
   - Document split-commit as THE approach
   - Add note that handler files are deprecated

2. **Update README.md:**
   - Add "How It Works (Technical)" section
   - Explain split-commit algorithm
   - Explain 3-way merge benefits
   - Remove vague "blame analysis" description

3. **Update docs/technical/architecture.md:**
   - Add HunkCommitSplitter component section
   - Document split-commit flow
   - Update execution diagrams
   - Remove strategy selection references

4. **Add deprecation notices:**
   - git_native_complete_handler.py: "DEPRECATED: Not used in production"
   - git_native_handler.py: "DEPRECATED: Not used in production"
   - cli_strategy.py: "DEPRECATED: Commands configure nothing"
   - strategy_base.py: "DEPRECATED: Abstract base for deprecated code"

### Phase 2: Remove CLI Strategy Commands (Immediate)

1. **main.py line 11:** Remove `from git_autosquash.cli_strategy import strategy_app`
2. **main.py line 316:** Remove `app.add_typer(strategy_app)`
3. **Verify:** `git-autosquash strategy-info` no longer works

### Phase 3: Future Deletion (Later)

After documentation is accurate and stable:
- Delete all 4 orphaned strategy files
- Delete all 5 test files
- -2,500 lines removed

---

## Documentation Content: Split-Commit Algorithm

### For README.md (User-facing)

```markdown
## How It Works

git-autosquash uses a sophisticated split-commit approach for reliable hunk squashing:

### 1. Blame Analysis
Analyzes git blame to identify which historical commit last modified each changed line.

### 2. Source Normalization
Converts all input sources (working tree, staged changes, HEAD) to a single commit using SourceNormalizer.

### 3. Commit Splitting
Creates temporary commits, one per hunk, using HunkCommitSplitter. Each commit contains exactly one change.

### 4. Cherry-Pick with 3-Way Merge
For each approved hunk:
- Uses `git cherry-pick --no-commit` to apply the split commit
- Git's 3-way merge machinery handles complexity
- Supports difficult cases like removing lines from the commit that added them

### 5. Interactive Rebase
Rebases through target commits chronologically, amending each with its hunks.

### 6. Validation
Post-flight validation via `git diff` ensures no data corruption occurred.

### Why This Works

Git's 3-way merge understands the full history context:
- **Base:** Common ancestor of source and target
- **Ours:** Target commit state
- **Theirs:** Changes from split commit

This allows git to correctly handle cases that would fail with simple text patches, including:
- Removing lines from the commit that added them
- Modifying lines across intervening commits
- Resolving conflicts automatically when safe
```

### For docs/technical/architecture.md

Add new section **"HunkCommitSplitter & Split-Commit Strategy"** between ProcessingValidator and HunkParser sections.

---

## Implementation Checklist

### Immediate (Today)
- [ ] Add deprecation notices to 4 strategy files
- [ ] Remove cli_strategy integration from main.py
- [ ] Update CLAUDE.md (remove strategy references)
- [ ] Update README.md (add split-commit algorithm)
- [ ] Update architecture.md (add HunkCommitSplitter section)
- [ ] Run tests to verify nothing broke
- [ ] Commit changes

### Future (Next Session)
- [ ] Delete 4 deprecated strategy files
- [ ] Delete 5 test files for deprecated code
- [ ] Update architecture diagrams
- [ ] Verify -2,500 line reduction

---

## Risk Assessment

### Low Risk (Documentation only)
- Updating CLAUDE.md: No code impact
- Updating README.md: No code impact
- Updating architecture.md: No code impact

### Medium Risk (Code changes)
- Removing cli_strategy from main.py: May break if tests invoke strategy commands
- Adding deprecation notices: No functional impact

### High Risk (Future deletion)
- Deleting strategy files: Breaks 5 test files
- Need to decide if tests provide value or just test dead code

---

## Success Criteria

After Phase 1 completion:
- [ ] Documentation accurately describes split-commit approach
- [ ] No references to "multiple strategies" in user-facing docs
- [ ] CLAUDE.md clearly states handler files are deprecated
- [ ] README explains the actual algorithm
- [ ] Architecture docs show HunkCommitSplitter in component hierarchy
- [ ] cli_strategy commands removed from help output
- [ ] All 549 tests still pass
