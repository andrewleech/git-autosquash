# Split-Commit Strategy Expansion

**Date:** 2025-10-30
**Status:** Bug Fix Required
**Priority:** HIGH - Affects common use case

## Problem Summary

**User Report:** "Squashing a line removal into the commit that added those lines" fails with patch application error.

**Root Cause:** The tool uses TWO different strategies, but only one is reliable:

### Current Strategy Selection (main.py:575)

```python
if context.source_commit:
    # Use split-commit + cherry-pick (RELIABLE)
    splitter = HunkCommitSplitter(git_ops)
    split_commits, hunks = splitter.split_commit_into_hunks(starting_commit)
else:
    # Use patch-based approach (FRAGILE)
    hunk_parser = HunkParser(git_ops)
    hunks = hunk_parser.get_diff_hunks(line_by_line, from_commit=starting_commit)
```

### Why This Fails

**Scenario:** HEAD commit removes lines that were added by commit `abc123`

**With patch-based approach:**
1. Tool generates text patch: `- uint16_t configured_phy_speed;`
2. Starts rebase to edit commit `abc123`
3. Tries to apply patch to commit `abc123`
4. **FAILS:** The line doesn't exist yet in `abc123` (because that's the commit that ADDS it!)

**Git error:**
```
error: repository lacks the necessary blob to perform 3-way merge.
Falling back to direct application...
error: patch failed: ports/stm32/eth.c:124
error: ports/stm32/eth.c: patch does not apply
```

### Why Split-Commit Approach Works

**With split-commit + cherry-pick approach:**
1. Tool creates temporary commit with the removals
2. Uses `git cherry-pick --no-commit <split-commit>` to apply
3. Git's 3-way merge algorithm handles it:
   - Base: Common ancestor
   - Ours: Target commit state
   - Theirs: Split commit changes
4. **SUCCESS:** Git understands the intent and applies changes correctly

## Evidence

### Test Case
```bash
cd /home/corona/mpy/stm32_eth
git log --oneline -3
# 47d1a7fe stm32/eth: Remove unused configured_phy_speed field.
# ae07a78e stm32/eth: Restore CLK_SLEEP_ENABLE...
# daa24cf2 stm32/eth: Consolidate DHCP restart logic...

git-autosquash --auto-accept
# ✗ Rebase execution failed: Patch application failed
```

**Blame analysis correctly identifies:** Line removals should go to commit `2d40d3b4` (the commit that added them)

**Patch application fails:** Can't remove lines that don't exist yet in `2d40d3b4`

### Proof Split-Commit Works

The `HunkCommitSplitter` already exists and works:
- **File:** `src/git_autosquash/hunk_commit_splitter.py`
- **Purpose:** "Split source commits into per-hunk commits for reliable 3-way merge"
- **Method:** Creates real git commits that git can use for proper conflict resolution
- **Used when:** `--source <commit>` flag is provided

## Solution

**Expand split-commit strategy to ALL cases, not just `--source` cases.**

### Proposed Change

**File:** `src/git_autosquash/main.py`, around line 571-592

**Current:**
```python
# Phase 2: Split source commit into per-hunk commits (if using --source)
splitter: Optional[HunkCommitSplitter] = None
split_commits: List[str] = []
if context.source_commit:  # ← ONLY for --source cases!
    splitter = HunkCommitSplitter(git_ops)
    try:
        split_commits, hunks = splitter.split_commit_into_hunks(starting_commit)
    except Exception as e:
        # Fall back to normal patch-based approach
        splitter = None
        split_commits = []

# Phase 3: Parse hunks (use hunks from splitter if available)
if not split_commits:
    hunk_parser = HunkParser(git_ops)
    hunks = hunk_parser.get_diff_hunks(line_by_line, from_commit=starting_commit)
```

**Proposed:**
```python
# Phase 2: Split source commit into per-hunk commits (ALWAYS for reliability)
splitter: Optional[HunkCommitSplitter] = None
split_commits: List[str] = []
# ALWAYS use split-commit approach for reliable 3-way merge
logging.debug("Splitting source commit into per-hunk commits for reliable 3-way merge")
splitter = HunkCommitSplitter(git_ops)
try:
    split_commits, hunks = splitter.split_commit_into_hunks(starting_commit)
    logging.debug(f"Created {len(split_commits)} split commits")
except Exception as e:
    logging.debug(f"Failed to split commit: {e}")
    # Fall back to normal patch-based approach only if split fails
    logging.warning("Falling back to patch-based approach (may fail for line removals)")
    splitter = None
    split_commits = []

# Phase 3: Parse hunks (use hunks from splitter if available)
if not split_commits:
    hunk_parser = HunkParser(git_ops)
    hunks = hunk_parser.get_diff_hunks(line_by_line, from_commit=starting_commit)
```

### Testing Required

1. **Test the reported failure case:**
   ```bash
   cd /home/corona/mpy/stm32_eth
   git-autosquash --auto-accept --verbose
   # Should now succeed
   ```

2. **Test working tree changes:**
   ```bash
   echo "test" >> file.txt
   git-autosquash --dry-run
   # Should work with split-commit approach
   ```

3. **Test existing --source behavior:**
   ```bash
   git-autosquash --source <commit> --dry-run
   # Should still work (no regression)
   ```

4. **Run full test suite:**
   ```bash
   uv run pytest tests/ -v
   # All tests should pass
   ```

## Benefits

1. **Fixes critical bug:** "Remove lines from commit that added them" now works
2. **Single code path:** Eliminates patch-based approach complexity
3. **More reliable:** Git's 3-way merge is battle-tested
4. **Simpler codebase:** Can eventually remove patch-based fallback entirely

## Potential Issues

### Issue 1: Performance
**Impact:** Split-commit creates temporary commits (slightly slower)
**Mitigation:** Acceptable trade-off for reliability

### Issue 2: Git Version
**Impact:** Requires git with cherry-pick --no-commit
**Mitigation:** This has been in git since 2006 (git 1.4.0)

### Issue 3: Fallback Still Needed
**Impact:** Some edge cases might fail split-commit
**Mitigation:** Keep patch-based as fallback (with warning)

## Implementation Estimate

**Effort:** 30-60 minutes
- Change: 5 lines in main.py
- Testing: 30 minutes
- Validation: 15 minutes

**Risk:** Low - just expanding existing working code to more cases

## Alternative: Full Fixup-Commit Approach

The archived plan `docs/archived-plans/fixup-commit-approach.md` proposes an even simpler approach:
1. Create fixup commits for all hunks
2. Single `git rebase -i --autosquash` to squash them all

**Benefits:** Even simpler, single rebase operation
**Effort:** 7-11 hours (much larger refactor)
**Status:** Future enhancement

**Recommendation:** Do the quick fix now (split-commit expansion), consider fixup approach later.

## Related Files

- `src/git_autosquash/main.py`: Strategy selection logic
- `src/git_autosquash/hunk_commit_splitter.py`: Split-commit implementation (already works!)
- `src/git_autosquash/rebase_manager.py`: Cherry-pick application (already works!)
- `docs/archived-plans/fixup-commit-approach.md`: Long-term architectural plan

## Conclusion

**The tool already has the right approach (split-commit + cherry-pick), but only uses it for `--source` cases.**

**Fix:** Use it for ALL cases to make the critical "remove lines from adding commit" use case work.
