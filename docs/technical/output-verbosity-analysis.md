# Output Verbosity Analysis and Reduction Plan

**Date:** 2025-10-30
**Status:** Proposal
**Issue:** Tool output is excessively verbose in normal use cases

## Severity Assessment

**CRITICAL:** The tool has **118 DEBUG print statements** across the codebase that output during normal operations. In a typical successful run, the user sees **~150+ lines of DEBUG output** before the final success message. This is unacceptable for production use.

### Real Output Example Analysis

From actual user run (4 hunks, 2 target commits):
- **Total output lines:** ~160
- **DEBUG lines:** ~140 (88% of output)
- **Useful lines:** ~20 (12% of output)
- **Full patches printed:** 2 (3000+ characters each in boxes)

## Current Output Audit

### Category 1: DEBUG Output (MUST REMOVE - CRITICAL)

**Total DEBUG statements: 118 across codebase**
- main.py: ~6 DEBUG statements
- rebase_manager.py: **83 DEBUG statements** (primary culprit)
- git_native_handler.py: Additional DEBUG output

#### Examples from Actual Output

**main.py:**
```python
print("DEBUG: Splitting source commit into per-hunk commits for reliable 3-way merge")
print(f"DEBUG: Created {len(split_commits)} split commits")
print(f"DEBUG: Mapped hunk {i + 1} to split commit {split_commits[i][:8]}")
```

**rebase_manager.py (83 statements!):**
```python
print(f"DEBUG: Processing target commit {target_commit[:8]} with {len(hunks)} hunks")
print(f"DEBUG: Applying {len(hunks)} hunks to commit {target_commit[:8]}")
print(f"DEBUG: Hunk {i + 1}: {hunk.file_path} @@ {hunk.lines[0]}")
print("DEBUG: Starting interactive rebase to edit...")
print("DEBUG: Using comprehensive rebase approach...")
print("DEBUG: Generated todo content for...")
print(f"DEBUG: Starting rebase with: git rebase -i...")
print(f"DEBUG: Rebase command returned: {code}")
print(f"DEBUG: Rebase stderr: {stderr}")
print("DEBUG: Interactive rebase started successfully")
print(f"DEBUG: Current HEAD during rebase: {current_head[:8]}")
print(f"DEBUG: Target commit: {target_commit[:8]}")
print(f"DEBUG: Line 87 content: '{lines[86].strip()}'")  # Why line 87/111 specifically??
print(f"DEBUG: Line 111 content: '{lines[110].strip()}'")
print("DEBUG: Creating patch from original hunk text")
print(f"DEBUG: Created patch content ({len(patch_content)} chars):")
print("="*50)
print(patch_content)  # PRINTS ENTIRE PATCH (1000+ chars)
print("="*50)
print(f"DEBUG: Wrote patch to temporary file: {patch_file}")
print(f"DEBUG: Running git apply --3way --recount {patch_file}")
print(f"DEBUG: git apply returned code: {code}")
print("DEBUG: Patch applied successfully")
print("DEBUG: Amending commit with changes")
print("DEBUG: Commit amended successfully")
print("DEBUG: Continuing rebase")
print(f"DEBUG: git rebase --continue returned: {code}")
print("DEBUG: git rebase --continue stdout:")
print("DEBUG: git rebase --continue stderr: {stderr}")
print("DEBUG: Rebase completed successfully")
print("DEBUG: Rebase continued successfully")
print("DEBUG: Successfully applied hunks to commit...")
print("="*80)  # Separator between commits
```

**Impact:** For a simple 4-hunk operation with 2 target commits, this produces **~140 lines of DEBUG output** including two full patches (3000+ chars each).

**Recommendation:**
- **IMMEDIATE:** Remove ALL 118 DEBUG print statements
- Replace with proper Python logging module at DEBUG level
- Add `--verbose` / `-v` flag that enables logging.DEBUG
- Default to logging.INFO which shows only essential messages

---

### Category 2: Low-Value/Redundant Output (Should Remove or Simplify)

**Line 552** (main.py)
```python
print(f"Processing from commit: {starting_commit[:8]}")
```
**Issue:** Technical detail not useful to end users. Only matters for debugging source normalization.
**Recommendation:** Remove or move to --verbose

**Lines 886-889** (main.py)
```python
print(f"Found target commits for {len(automatic_mappings)} hunks")
print(f"Found {len(fallback_mappings)} hunks requiring manual target selection")
```
**Issue:** Low-value status messages before TUI. User will see this info in the TUI.
**Actual output:** "Found target commits for 3 hunks" / "Found 1 hunks requiring manual target selection"
**Recommendation:** Remove or combine into single line: `Processing 4 hunks...`

**Lines 190-203** (main.py) - Execution Plan Display
```python
print(f"Distributing {len(approved_mappings)} hunks to their target commits:")
commit_counts = {}
for mapping in approved_mappings:
    # ... count hunks per commit ...
for commit_hash, count in commit_counts.items():
    commit_summary = resolver.get_commit_summary(commit_hash)
    print(f"  {count} hunk{'s' if count > 1 else ''} → {commit_summary}")
```
**Issue:** User just finished approving these in the TUI. This is redundant confirmation.
**Recommendation:** Remove entirely. User already knows what they approved.

**Line 205** (main.py)
```python
print("\nStarting rebase operation...")
```
**Issue:** Unnecessary status message. Git will output during rebase anyway.
**Recommendation:** Remove

**Lines 298-304** (main.py) - _display_automatic_mappings
```python
print(f"\nFound {len(mappings)} hunks with automatic blame-identified targets:")
for mapping in mappings:
    commit_summary = mapping.target_commit[:8] if mapping.target_commit else "unknown"
    print(f"  → {mapping.hunk.file_path}: {commit_summary}")
```
**Issue:** When using TUI (default mode), this prints before the TUI launches, then user sees the same info in TUI.
**Recommendation:** Only show summary count, not individual mappings. Or skip entirely in interactive mode.

---

### Category 3: Auto-Accept Mode Verbosity (Should Simplify)

**Lines 630-638** (main.py)
```python
print(f"\n✓ Auto-accepting {len(automatic_mappings)} hunks with blame-identified targets")
for mapping in automatic_mappings:
    commit_summary = mapping.target_commit[:8] if mapping.target_commit else "unknown"
    print(f"  → {mapping.hunk.file_path}: {commit_summary}")
```
**Issue:** Lists every single hunk. For large changes (20+ hunks), this is noise.
**Recommendation:** Show summary only:
```python
print(f"\n✓ Auto-accepting {len(automatic_mappings)} hunks across {len(files)} files")
```
Or add `--verbose` flag to show full details.

---

### Category 4: Essential Output (Keep)

**Line 950** (main.py)
```python
print("[+] Validation passed - no corruption detected")
```
**Value:** Critical safety confirmation. Users need to know validation succeeded.
**Recommendation:** Keep

**Lines 957, 959** (main.py)
```python
print("✓ Operation completed successfully!")
print("✗ Operation failed or was cancelled.")
```
**Value:** Essential outcome feedback
**Recommendation:** Keep

**Lines 219-241** (main.py) - Conflict Resolution Guidance
```python
print("\n⚠️ Rebase conflicts detected:")
for file_path in conflicts:
    print(f"  {file_path}")
print("\nTo resolve conflicts:")
print("1. Edit the conflicted files to resolve conflicts")
# ... etc
```
**Value:** Critical for user recovery from conflicts
**Recommendation:** Keep all conflict guidance

**Lines 259-267** (main.py) - Error Messages
```python
print(f"\n✗ Rebase execution failed: {e}")
print("Repository restored to original state")
```
**Value:** Critical error communication
**Recommendation:** Keep

---

### Category 5: Dry-Run Mode (Keep Current Verbosity)

**Lines 730-786** (main.py) - Dry run output
```python
print("\n=== DRY RUN MODE ===")
print("Showing what would be done without making any changes\n")
# ... detailed output ...
```
**Value:** Dry-run explicitly asks for verbose preview
**Recommendation:** Keep current level of detail for dry-run mode

---

## Proposed Changes

### Phase 1: Remove DEBUG Output (Immediate)

1. Remove all `print("DEBUG: ...")` statements (lines 559, 565, 567, 597-599, 227-230)
2. Replace with proper logging framework calls that respect `--verbose` flag

### Phase 2: Simplify Normal Output (Immediate)

**Current normal run output:**
```
Processing from commit: abc12345
DEBUG: Splitting source commit into per-hunk commits for reliable 3-way merge
DEBUG: Created 5 split commits
Found 8 hunks with automatic blame-identified targets:
  → src/main.py: abc12345
  → src/util.py: def67890
  → tests/test.py: abc12345
  [... 5 more lines ...]

[TUI launches]
[User approves hunks]

Distributing 8 hunks to their target commits:
  3 hunks → abc12345 (feat: add feature X)
  2 hunks → def67890 (fix: correct bug Y)
  3 hunks → ghi12345 (refactor: improve Z)

Starting rebase operation...
[git output]
[+] Validation passed - no corruption detected
✓ Operation completed successfully!
```

**Proposed normal run output:**
```
[TUI launches]
[User approves hunks]

[git output during rebase]
[+] Validation passed - no corruption detected
✓ Operation completed successfully!
```

**Reduction:** ~12 lines removed, only essential output remains

### Phase 3: Add --verbose Flag (Future Enhancement)

Add `--verbose` / `-v` flag that enables:
- Source commit normalization details
- Hunk-to-commit mapping preview
- Split commit creation details
- Execution plan before rebase

### Phase 4: Simplify Auto-Accept Mode (Immediate)

**Current auto-accept output:**
```
✓ Auto-accepting 15 hunks with blame-identified targets
  → src/auth.py: abc12345
  → src/db.py: def67890
  → src/api.py: abc12345
  [... 12 more lines ...]

Distributing 15 hunks to their target commits:
  5 hunks → abc12345 (feat: add auth)
  7 hunks → def67890 (feat: add database)
  3 hunks → ghi12345 (refactor: API)

Starting rebase operation...
[git output]
[+] Validation passed - no corruption detected
✓ Operation completed successfully!
```

**Proposed auto-accept output:**
```
✓ Auto-accepting 15 hunks across 8 files
[git output during rebase]
[+] Validation passed - no corruption detected
✓ Operation completed successfully!
```

**Reduction:** ~18 lines removed in typical case

---

## Implementation Priority

### CRITICAL - Must Fix Immediately
1. **Remove ALL 118 DEBUG print statements**
   - rebase_manager.py: 83 statements
   - main.py: 6 statements
   - Other files: Additional statements
   - **Impact:** Reduces output by 88% in typical cases
   - **Effort:** 2-3 hours (search/replace + testing)

### High Priority - Remove Redundant Output
2. **Remove "Processing from commit" message** (main.py:552)
3. **Remove "Found target commits for X hunks"** (main.py:886)
4. **Remove "Found X hunks requiring manual target selection"** (main.py:889)
5. **Remove execution plan display** (main.py:190-203)
6. **Remove "Starting rebase operation"** (main.py:205)
7. **Simplify auto-accept hunk list** (main.py:630-638)
   - **Impact:** Eliminates remaining noise
   - **Effort:** 30 minutes

### Medium Priority - Add Verbose Flag
8. **Add --verbose flag and logging framework**
   - Convert removed DEBUG statements to logging.debug()
   - Add --verbose/-v flag to enable debug logging
   - **Benefit:** Power users can still get detailed output when needed
   - **Effort:** 1-2 hours

### Low Priority - Future Enhancement
9. **Add structured logging with log levels**
   - Proper logging configuration
   - Log to file option
   - **Benefit:** Better debugging infrastructure
   - **Effort:** 2-3 hours

---

## User Experience Goals

### Normal Interactive Mode
- **Before TUI:** Silent or minimal (no pre-TUI spam)
- **During TUI:** Rich interactive UI
- **After approval:** Only git output + validation + success/failure
- **Target:** 3-5 lines of output total (excluding git's own output)

### Auto-Accept Mode
- **Output:** Summary of actions + validation + outcome
- **Target:** 3-4 lines of output total (excluding git's own output)

### Dry-Run Mode
- **Output:** Detailed preview of what would happen
- **Target:** Current verbosity is appropriate

### Error/Conflict Cases
- **Output:** Full diagnostic information with recovery guidance
- **Target:** Keep current verbosity for error cases

---

## Examples: Before & After

### Example 1: Interactive Mode Success (ACTUAL OUTPUT)

**Before (~160 lines - severely trimmed for readability):**
```
Processing from commit: 23d48082
Found target commits for 3 hunks
Found 1 hunks requiring manual target selection
Distributing 4 hunks to their target commits:
  1 hunk → bde7dbdd94 tests: Add Ctrl-C interrupt tests for REPL and execution.
  3 hunks → b8be5b827f tests/run-tests: Add itest_ framework for interactive PTY tests.

Starting rebase operation...
DEBUG: Processing 2 target commits in order: ['bde7dbdd', 'b8be5b82']
DEBUG: Processing target commit bde7dbdd with 1 hunks
DEBUG: Applying 1 hunks to commit bde7dbdd
DEBUG: Hunk 1: tests/ports/unix/itest_ctrl_c_interrupt.py @@ @@ -3,29 +3,16 @@ Test that Ctrl-C...
DEBUG: Starting interactive rebase to edit bde7dbdd
DEBUG: Using comprehensive rebase approach for bde7dbdd with 2 commits
DEBUG: Generated todo content for bde7dbdd:
edit bde7dbdd94a5ebc423bcd36305564a77d79cbb27
pick 23d4808208cdcc6cae384cd7e89bb323401fa103

DEBUG: Starting rebase with: git rebase -i bde7dbdd94a5ebc423bcd36305564a77d79cbb27^
DEBUG: Rebase command returned: 0
DEBUG: Rebase stderr: Rebasing (1/2)

Stopped at bde7dbdd94...
You can amend the commit now, with

  git commit --amend

Once you are satisfied with your changes, run

  git rebase --continue

DEBUG: Interactive rebase started successfully
DEBUG: Current HEAD during rebase: bde7dbdd
DEBUG: Target commit: bde7dbdd
DEBUG: Line 87 content: 'ctx->constants = frozen->constants;'
DEBUG: Line 111 content: 'mp_parse_tree_t parse_tree = mp_parse(lex, input_kind);'
DEBUG: Creating patch from original hunk text
DEBUG: Created patch content (1058 chars):
==================================================
--- a/tests/ports/unix/itest_ctrl_c_interrupt.py
+++ b/tests/ports/unix/itest_ctrl_c_interrupt.py
@@ -3,29 +3,16 @@ Test that Ctrl-C interrupts running code in the REPL.

 This test is run by run-tests.py which sets up a PTY with ISIG enabled
 and spawns MicroPython with the PTY as its controlling terminal.
-The global 'master' variable (PTY master fd) is provided by run-tests.py.
+
+Globals provided by run-tests.py:
+- master: PTY master file descriptor
[... FULL 1000+ character patch printed ...]
==================================================
DEBUG: Wrote patch to temporary file: /tmp/tmpjehwt392.patch
DEBUG: Running git apply --3way --recount /tmp/tmpjehwt392.patch
DEBUG: git apply returned code: 0
DEBUG: Patch applied successfully
DEBUG: Amending commit with changes
DEBUG: Commit amended successfully
DEBUG: Continuing rebase
DEBUG: git rebase --continue returned: 0
DEBUG: git rebase --continue stdout:
DEBUG: git rebase --continue stderr: Rebasing (2/2)

Successfully rebased and updated refs/heads/unix_pyexec.

DEBUG: Rebase completed successfully
DEBUG: Rebase continued successfully
DEBUG: Successfully applied hunks to commit bde7dbdd
================================================================================
[... REPEATS for second commit with another 70+ DEBUG lines ...]
✓ Successfully applied selected hunks
[+] Validation passed - no corruption detected
✓ Operation completed successfully!
```

**After (3 lines):**
```
[TUI shows info interactively]
[User approves 4, ignores 1]
[git rebase output - only git's own messages]
[+] Validation passed - no corruption detected
✓ Operation completed successfully!
```

**Reduction: 160 lines → 3 lines (98% reduction)**

### Example 2: Auto-Accept Mode Success

**Before (21 lines):**
```
Processing from commit: a1b2c3d4
✓ Auto-accepting 12 hunks with blame-identified targets
  → src/auth.py: a1b2c3d4
  → src/db.py: e5f6g7h8
  → src/api.py: a1b2c3d4
  → src/models.py: i9j0k1l2
  → tests/test_auth.py: a1b2c3d4
  → tests/test_db.py: e5f6g7h8
  → tests/test_api.py: a1b2c3d4
  → docs/api.md: i9j0k1l2
  → src/utils.py: e5f6g7h8
  → src/config.py: a1b2c3d4
  → tests/test_utils.py: e5f6g7h8
  → README.md: i9j0k1l2

Distributing 12 hunks to their target commits:
  5 hunks → a1b2c3d4 (feat: add authentication)
  4 hunks → e5f6g7h8 (feat: add database layer)
  3 hunks → i9j0k1l2 (docs: update API documentation)

Starting rebase operation...
[git rebase output]
[+] Validation passed - no corruption detected
✓ Operation completed successfully!
```

**After (4 lines):**
```
✓ Auto-accepting 12 hunks across 6 files
[git rebase output]
[+] Validation passed - no corruption detected
✓ Operation completed successfully!
```

### Example 3: Conflict Case (Keep Verbose)

**Before & After (Same - Keep current output):**
```
[git rebase output]

⚠️ Rebase conflicts detected:
  src/main.py
  src/util.py

To resolve conflicts:
1. Edit the conflicted files to resolve conflicts
2. Stage the resolved files: git add <files>
3. Continue the rebase: git rebase --continue
4. Or abort the rebase: git rebase --abort

Rebase was automatically aborted due to conflicts.
Repository has been restored to its original state.
```

---

## Implementation Notes

### Files to Modify
- `src/git_autosquash/main.py`: Primary file with all print statements

### Backward Compatibility
- No backward compatibility concerns (output format is not an API)
- May want to add `--verbose` flag before removing output for power users

### Testing
- Manual testing of all modes: interactive, auto-accept, dry-run
- Verify error messages still appear correctly
- Check conflict resolution guidance still works

### Documentation Updates
- Update README if it mentions specific output format
- Update user guide to reflect cleaner output

---

## Decision Matrix

| Output | Current State | Keep? | Reason |
|--------|--------------|-------|---------|
| DEBUG statements | Always shown | ❌ | Development leftovers |
| "Processing from commit" | Always shown | ❌ | Low value, debugging only |
| Automatic mappings list | Before TUI | ❌ | Redundant with TUI |
| "Starting rebase operation" | Always shown | ❌ | Unnecessary status |
| Execution plan breakdown | After TUI | ❌ | Redundant after approval |
| Auto-accept hunk list | Auto-accept mode | ❌ | Too verbose, summarize instead |
| Validation success | Always shown | ✅ | Critical safety confirmation |
| Success/failure | Always shown | ✅ | Essential outcome |
| Conflict guidance | On conflicts | ✅ | Critical recovery info |
| Error messages | On errors | ✅ | Essential diagnostics |
| Dry-run detail | Dry-run only | ✅ | Expected verbosity |

---

## Estimated Impact

### Lines of Output Reduced (Based on Actual Output)
- **Interactive mode:** ~160 lines → ~5 lines (97% reduction)
  - Current: DEBUG spam + redundant messages + git output + validation
  - Proposed: Only git output + validation + success message
- **Auto-accept mode:** ~150 lines → ~4 lines (97% reduction)
  - Current: DEBUG spam + hunk lists + execution plan + git output
  - Proposed: Summary + git output + validation + success
- **Dry-run mode:** No change (appropriate verbosity for preview)
- **Error cases:** No change (need full diagnostics)

### User Experience Improvement
- **Massive reduction in noise:** 88% of typical output is DEBUG spam
- **Clear signal-to-noise ratio:** Only essential information displayed
- **Professional appearance:** No development debugging visible to users
- **Faster outcome recognition:** Success/failure immediately visible
- **Still detailed when needed:** Full diagnostics on errors, optional --verbose
- **Readable git output:** No longer buried in DEBUG lines

### Development Time

**Phase 1: Remove DEBUG statements (CRITICAL)**
- Find and remove 118 DEBUG print() calls: 1 hour
- Test all code paths still work: 1 hour
- Verify no broken error handling: 30 minutes
- **Subtotal: 2.5 hours**

**Phase 2: Remove redundant output (HIGH)**
- Remove/simplify 7 redundant output locations: 30 minutes
- Test interactive/auto-accept/dry-run modes: 30 minutes
- **Subtotal: 1 hour**

**Phase 3: Add --verbose flag (MEDIUM)**
- Convert print() → logging.debug(): 30 minutes
- Add --verbose CLI flag: 15 minutes
- Wire up logging configuration: 30 minutes
- Test verbose mode works: 15 minutes
- **Subtotal: 1.5 hours**

**Total: 5 hours** (Phases 1-2 are 3.5 hours for immediate fix)
