# Implementation Plan: Fixup Commit Approach

**Status:** Planning Phase
**Complexity:** High
**Estimated Time:** 7-11 hours
**Dependencies:** None (can be implemented independently)

## Executive Summary

Replace the current sequential rebase-edit-amend approach with a simpler workflow: create fixup commits for each hunk, then use `git rebase -i --autosquash` to squash them in a single operation. This reduces code complexity by ~600 lines while improving reliability and performance.

## Problem Statement

### Current Implementation Issues

The current approach (src/git_autosquash/rebase_manager.py) uses sequential interactive rebases:

1. **Sequential Processing:** For each target commit, start a new `git rebase -i` session
2. **Line Number Correction:** Custom logic to translate line numbers from working tree to historical commit state
3. **Complex Patch Generation:** ~93 lines of logic in `_create_corrected_patch_for_hunks`
4. **Multiple Rebase Cycles:** O(n) rebase operations where n = number of unique target commits
5. **State Management:** Complex tracking across multiple rebase start/stop cycles

**Pain Points:**
- Line number correction is error-prone for complex changes
- Multiple failure points (each rebase can fail independently)
- Hard to debug (state spread across multiple rebases)
- ~700 lines of complex rebase orchestration code
- Difficult to maintain and extend

### Key Insight

The complexity exists to handle applying hunks from working tree state to historical commit states with different line numbers. The fixup approach sidesteps this by:
1. Creating commits in current state (no line number correction needed)
2. Letting git's 3-way merge handle complexity during autosquash

---

## Current Architecture Analysis

### Current Flow (src/git_autosquash/rebase_manager.py:48-128)

```
execute_squash()
├─ Group hunks by target commit
├─ Get commit order (chronological)
└─ For each target commit:
   ├─ _apply_hunks_to_commit()
   │  ├─ _start_rebase_edit(target_commit)  # git rebase -i <commit>^
   │  ├─ _create_corrected_patch_for_hunks() # Complex line number logic
   │  ├─ _apply_patch()                      # git apply
   │  ├─ _amend_commit()                     # git commit --amend
   │  └─ _continue_rebase()                  # git rebase --continue
   └─ Handle conflicts/errors
```

### Complex Methods (To Be Replaced)

**File:** `src/git_autosquash/rebase_manager.py`

| Method | Lines | Purpose | Complexity |
|--------|-------|---------|------------|
| `_apply_hunks_to_commit` | 80 | Orchestrate single commit rebase | High |
| `_create_corrected_patch_for_hunks` | 93 | Line number correction | Very High |
| `_consolidate_overlapping_changes` | 55 | Merge overlapping hunks | High |
| `_create_consolidated_hunk` | 80 | Build merged hunk | High |
| `_create_corrected_hunk_for_change` | 48 | Correct single hunk lines | Medium |
| `_create_corrected_hunk` | 71 | Create corrected patch | Medium |
| `_create_patch_for_hunks` | 34 | Generate patch content | Low |
| `_start_rebase_edit` | 50 | Start interactive rebase | Medium |
| `_apply_patch` | 48 | Apply patch with git | Medium |
| `_amend_commit` | 37 | Amend commit with changes | Medium |
| `_continue_rebase` | 52 | Continue rebase operation | Medium |
| `_generate_rebase_todo` | 102 | Generate rebase todo file | High |

**Total lines to remove:** ~750 lines

---

## Proposed Architecture

### New Flow

```
execute_squash()
├─ Initialize FixupCommitManager
├─ Create fixup commits (all at once, atomic)
│  └─ For each mapping:
│     ├─ Apply hunk to working tree (current state)
│     ├─ Stage file: git add <file>
│     ├─ Get target subject: git log -1 --format=%s <target>
│     └─ Create fixup: git commit --no-verify -m "fixup! <subject>"
│
└─ Execute single autosquash rebase
   └─ git rebase -i --autosquash <merge_base>
      └─ Git automatically places fixup! commits after targets
```

### Comparison: Current vs Proposed

| Aspect | Current | Proposed |
|--------|---------|----------|
| **Rebase operations** | O(n) sequential | O(1) single rebase |
| **Line number handling** | Custom correction logic | Git's 3-way merge |
| **Complexity** | ~750 lines | ~200 lines |
| **Failure points** | Multiple (per-commit) | Single (one rebase) |
| **Conflict resolution** | Per-commit | Single session |
| **Performance** | Slower (multiple rebases) | Faster (one rebase) |
| **Maintainability** | Complex custom logic | Standard git operations |
| **Hook execution** | Per amend (multiple) | Per fixup + final squash |

---

## Detailed Implementation

### Phase 1: FixupCommitManager Class

**New File:** `src/git_autosquash/fixup_commit_manager.py`

```python
"""Manager for fixup commit creation and autosquash rebase execution."""

from typing import List, Optional
import logging
from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.git_ops import GitOps

logger = logging.getLogger(__name__)


class FixupCreationError(Exception):
    """Raised when fixup commit creation fails."""
    pass


class FixupCommitManager:
    """Manage fixup commit creation and autosquash rebase execution.

    This class handles:
    1. Creating fixup commits for hunks (with atomic rollback)
    2. Executing autosquash rebase
    3. Cleanup on failure
    """

    def __init__(self, git_ops: GitOps):
        """Initialize the fixup commit manager.

        Args:
            git_ops: GitOps instance for git command execution
        """
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)
        self.created_commits: List[str] = []

    def create_fixup_commits_atomic(
        self,
        mappings: List[HunkTargetMapping]
    ) -> List[str]:
        """Create all fixup commits atomically (all-or-nothing).

        Creates a fixup commit for each hunk-to-commit mapping. If any
        fixup creation fails, all created commits are rolled back.

        Args:
            mappings: List of hunk to target commit mappings

        Returns:
            List of created fixup commit SHAs

        Raises:
            FixupCreationError: If any fixup creation fails
        """
        if not mappings:
            return []

        original_head = self._get_head_hash()
        self.created_commits = []

        try:
            self.logger.info(f"Creating {len(mappings)} fixup commits...")

            for i, mapping in enumerate(mappings, 1):
                commit_sha = self._create_single_fixup(mapping)
                self.created_commits.append(commit_sha)
                self.logger.debug(
                    f"Created fixup {i}/{len(mappings)}: {commit_sha[:8]} "
                    f"for {mapping.hunk.file_path}"
                )

            self.logger.info(f"✓ Created {len(self.created_commits)} fixup commits")
            return self.created_commits

        except Exception as e:
            # Rollback: reset to original HEAD
            self.logger.error(f"Fixup creation failed, rolling back: {e}")
            self.git_ops.run_git_command(["reset", "--hard", original_head])
            self.created_commits.clear()
            raise FixupCreationError(
                f"Failed to create fixup commits: {e}. All changes rolled back."
            )

    def _create_single_fixup(self, mapping: HunkTargetMapping) -> str:
        """Create a single fixup commit for a hunk.

        The hunk is applied in the current working tree state, so no line
        number correction is needed. Git's autosquash will handle the merge
        during rebase.

        Args:
            mapping: Hunk to target commit mapping

        Returns:
            SHA of created fixup commit

        Raises:
            FixupCreationError: If commit creation fails
        """
        hunk = mapping.hunk
        target_commit = mapping.target_commit

        # Apply hunk to working tree (in current state)
        self._apply_hunk_to_working_tree(hunk)

        # Stage the file
        result = self.git_ops.run_git_command(["add", hunk.file_path])
        if result.returncode != 0:
            raise FixupCreationError(
                f"Failed to stage {hunk.file_path}: {result.stderr}"
            )

        # Get target commit subject for fixup message
        subject = self._get_commit_subject(target_commit)

        # Create fixup commit (skip pre-commit hooks with --no-verify)
        result = self.git_ops.run_git_command([
            "commit",
            "--no-verify",  # Skip hooks for temporary fixup commits
            "-m", f"fixup! {subject}"
        ])

        if result.returncode != 0:
            raise FixupCreationError(
                f"Failed to create fixup commit: {result.stderr}"
            )

        return self._get_head_hash()

    def _apply_hunk_to_working_tree(self, hunk) -> None:
        """Apply a hunk to the working tree.

        Creates a minimal patch and applies it using git apply.

        Args:
            hunk: DiffHunk to apply

        Raises:
            FixupCreationError: If patch application fails
        """
        # Create minimal patch for this hunk
        patch_content = self._create_hunk_patch(hunk)

        # Apply patch to working tree
        result = self.git_ops.run_git_command_with_input(
            ["apply", "--unidiff-zero"],  # Allow context-free patches
            patch_content
        )

        if result.returncode != 0:
            raise FixupCreationError(
                f"Failed to apply hunk to {hunk.file_path}: {result.stderr}"
            )

    def _create_hunk_patch(self, hunk) -> str:
        """Create a git patch for a single hunk.

        Args:
            hunk: DiffHunk to create patch for

        Returns:
            Patch content as string
        """
        patch_lines = [
            f"diff --git a/{hunk.file_path} b/{hunk.file_path}",
            f"--- a/{hunk.file_path}",
            f"+++ b/{hunk.file_path}",
        ]

        # Add hunk content directly
        patch_lines.extend(hunk.lines)

        return "\n".join(patch_lines) + "\n"

    def _get_commit_subject(self, commit_hash: str) -> str:
        """Get the subject line of a commit.

        Args:
            commit_hash: Commit to get subject from

        Returns:
            Commit subject (first line of message)
        """
        result = self.git_ops.run_git_command([
            "log", "-1", "--format=%s", commit_hash
        ])

        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return commit_hash[:8]  # Fallback to short hash

    def _get_head_hash(self) -> str:
        """Get current HEAD commit hash.

        Returns:
            Full SHA of HEAD
        """
        result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
        return result.stdout.strip()

    def execute_autosquash_rebase(self, merge_base: str) -> bool:
        """Execute single autosquash rebase.

        Uses git's built-in autosquash to squash all fixup! commits
        into their target commits. Pre-commit hooks will run during
        this phase (not suppressed).

        Args:
            merge_base: Base commit for rebase

        Returns:
            True if rebase succeeded, False otherwise
        """
        self.logger.info("Executing autosquash rebase...")

        # Set GIT_SEQUENCE_EDITOR to auto-accept the todo list
        # The todo list will already have fixup commits properly placed
        import os
        env = os.environ.copy()
        env["GIT_SEQUENCE_EDITOR"] = ":"  # No-op editor (auto-accept)

        result = self.git_ops.run_git_command(
            ["rebase", "-i", "--autosquash", merge_base],
            env=env
        )

        if result.returncode == 0:
            self.logger.info("✓ Autosquash rebase completed successfully")
            return True
        else:
            self.logger.error(f"Autosquash rebase failed: {result.stderr}")
            return False

    def cleanup_fixup_commits(self) -> None:
        """Remove created fixup commits (called on failure).

        Resets to the commit before the first fixup was created.
        """
        if not self.created_commits:
            return

        first_fixup = self.created_commits[0]
        self.logger.info("Cleaning up fixup commits...")

        # Reset to parent of first fixup
        result = self.git_ops.run_git_command([
            "reset", "--hard", f"{first_fixup}~1"
        ])

        if result.returncode == 0:
            self.logger.info("✓ Fixup commits removed")
        else:
            self.logger.warning(
                f"Failed to cleanup fixup commits: {result.stderr}"
            )

        self.created_commits.clear()
```

### Phase 2: RebaseManager Refactoring

**File:** `src/git_autosquash/rebase_manager.py`

#### Modified: execute_squash Method

Replace lines 48-128 with:

```python
def execute_squash(
    self,
    mappings: List[HunkTargetMapping],
    context: SquashContext,
) -> bool:
    """Execute squash using fixup commits + autosquash.

    This simplified implementation:
    1. Creates fixup commits for each hunk (atomic)
    2. Executes single autosquash rebase
    3. Handles stash restoration

    Args:
        mappings: List of approved hunk to commit mappings
        context: SquashContext for configuration

    Returns:
        True if successful, False if user aborted

    Raises:
        RebaseConflictError: If conflicts occur during rebase
        subprocess.SubprocessError: If git operations fail
    """
    if not mappings:
        return True

    self._context = context

    # Store original branch for cleanup
    self._original_branch = self.git_ops.get_current_branch()
    if not self._original_branch:
        raise ValueError("Cannot determine current branch")

    # Initialize fixup manager
    fixup_manager = FixupCommitManager(self.git_ops)

    try:
        # Handle working tree state (existing stash logic)
        self._handle_working_tree_state()

        # Create all fixup commits atomically
        fixup_commits = fixup_manager.create_fixup_commits_atomic(mappings)
        logger.info(f"Created {len(fixup_commits)} fixup commits")

        # Execute single autosquash rebase
        success = fixup_manager.execute_autosquash_rebase(self.merge_base)

        if not success:
            logger.error("Autosquash rebase failed")
            fixup_manager.cleanup_fixup_commits()
            return False

        # Restore stash if we created one (success path)
        if self._stash_ref:
            try:
                success = self._restore_stash_by_sha(self._stash_ref)
                if not success:
                    logger.error(f"Failed to restore stash: {self._stash_ref[:12]}")
                    logger.info(f"Manual restore: git stash apply {self._stash_ref[:12]}")
            except Exception as e:
                logger.error(f"Error restoring stash: {e}")
                logger.info(f"Manual restore: git stash apply {self._stash_ref[:12]}")
            finally:
                self._stash_ref = None

        logger.info("✓ Squash operation completed successfully")
        return True

    except RebaseConflictError:
        # Don't cleanup on rebase conflicts - let user resolve manually
        raise
    except Exception as e:
        # Cleanup on any other error
        logger.error(f"Squash operation failed: {e}")
        fixup_manager.cleanup_fixup_commits()
        self._cleanup_on_error()
        raise
```

#### Methods to Remove

Delete the following methods (no longer needed):

1. `_apply_hunks_to_commit` (lines 599-678)
2. `_consolidate_hunks_by_file` (lines 680-689)
3. `_extract_hunk_changes` (lines 691-749)
4. `_find_target_with_context` (lines 751-827)
5. `_create_corrected_patch_for_hunks` (lines 829-922)
6. `_consolidate_overlapping_changes` (lines 924-979)
7. `_create_consolidated_hunk` (lines 981-1061)
8. `_create_corrected_hunk_for_change` (lines 1063-1111)
9. `_generate_rebase_todo` (lines 1113-1215)
10. `_commit_might_conflict_with_target` (lines 1217-1268)
11. `_should_use_simple_rebase` (lines 1270-1316)
12. `_create_corrected_hunk` (lines 1318-1389)
13. `_create_patch_for_hunks` (lines 1391-1425)
14. `_start_rebase_edit` (lines 1427-1477)
15. `_cleanup_rebase_state` (lines 1479-1489)
16. `_apply_patch` (lines 1491-1540)
17. `_amend_commit` (lines 1542-1579)
18. `_continue_rebase` (lines 1581-1633)
19. `_abort_rebase` (lines 1635-1641)

**Total lines removed:** ~750 lines

#### Methods to Keep

Retain stash management (working correctly):
- `_handle_working_tree_state`
- `_create_and_store_stash`
- `_create_stash_with_options`
- `_create_staged_only_stash`
- `_create_keep_index_stash`
- `_validate_stash_sha`
- `_verify_stash_exists`
- `_find_stash_ref_by_sha`
- `_restore_stash_by_sha`
- `_get_conflicted_files`
- `_cleanup_on_error`
- `abort_operation`
- `is_rebase_in_progress`
- `get_rebase_status`

---

## Hook Management

### Pre-commit Hook Strategy

**Fixup commit creation (Phase 1):**
```bash
git commit --no-verify -m "fixup! <subject>"
```

- **Purpose:** Skip all pre-commit hooks during fixup creation
- **Rationale:** Fixup commits are temporary; no need for validation
- **Benefits:**
  - Faster commit creation
  - No formatting/linting overhead
  - No risk of hook failures blocking fixup creation

**Autosquash rebase (Phase 2):**
```bash
git rebase -i --autosquash <merge_base>
```

- **Purpose:** Hooks run normally during the final rebase
- **Rationale:** Hooks apply to final squashed commits (actual history)
- **Benefits:**
  - Code quality maintained
  - Formatting applied to final commits
  - Standard git workflow

### Hook Modification Handling

If pre-commit hooks modify files during autosquash:
1. Git automatically re-stages modified files
2. Rebase continues with hook modifications included
3. No special handling needed (standard git behavior)

**Example:**
```bash
# Pre-commit hook runs ruff format
# Hook modifies file and returns 1 (modification made)
# Git sees:
#   - Hook modified files
#   - Files automatically staged
#   - Commit proceeds with formatted code
```

---

## Conflict Resolution

### Conflict Detection

Conflicts occur during `git rebase -i --autosquash`:
- Git's 3-way merge handles context matching
- Potentially fewer conflicts than current approach (git's merge is sophisticated)
- All conflicts in single rebase session

### User Experience

Current UX maintained (no changes needed):

```
⚠️ Rebase conflicts detected:
  src/auth/login.py

To resolve conflicts:
1. Edit the conflicted files to resolve conflicts
2. Stage the resolved files: git add <files>
3. Continue the rebase: git rebase --continue
4. Or abort the rebase: git rebase --abort
```

Same `RebaseConflictError` handling as current implementation.

### Abort/Cleanup

Simpler cleanup on failure:

```python
def _cleanup_on_error(self):
    """Cleanup on error (simplified)."""
    # Abort rebase if in progress
    if self.is_rebase_in_progress():
        self.git_ops.run_git_command(["rebase", "--abort"])

    # Restore stash if needed
    if self._stash_ref:
        self._restore_stash_by_sha(self._stash_ref)
```

---

## Testing Strategy

### Unit Tests

**New test file:** `tests/test_fixup_commit_manager.py`

```python
class TestFixupCommitManager:
    """Test FixupCommitManager functionality."""

    def test_create_single_fixup_commit(self):
        """Test creating a single fixup commit."""
        # Setup: repo with target commit and hunk
        # Execute: create_fixup_commits_atomic with one mapping
        # Assert: fixup commit created with correct message
        # Assert: commit skips pre-commit hooks

    def test_create_multiple_fixup_commits(self):
        """Test creating multiple fixup commits atomically."""
        # Setup: repo with multiple target commits
        # Execute: create_fixup_commits_atomic with multiple mappings
        # Assert: all fixup commits created
        # Assert: commits in correct order

    def test_atomic_rollback_on_failure(self):
        """Test that fixup creation rolls back on failure."""
        # Setup: repo with invalid hunk (will fail to apply)
        # Execute: create_fixup_commits_atomic (should fail mid-way)
        # Assert: HEAD returned to original position
        # Assert: no fixup commits left in history

    def test_execute_autosquash_rebase_success(self):
        """Test successful autosquash rebase."""
        # Setup: repo with fixup commits created
        # Execute: execute_autosquash_rebase
        # Assert: rebase succeeds
        # Assert: fixup commits squashed into targets

    def test_execute_autosquash_rebase_conflicts(self):
        """Test autosquash rebase with conflicts."""
        # Setup: repo with conflicting fixup commits
        # Execute: execute_autosquash_rebase
        # Assert: rebase pauses at conflict
        # Assert: user can resolve and continue

    def test_cleanup_fixup_commits(self):
        """Test cleanup removes fixup commits."""
        # Setup: create fixup commits
        # Execute: cleanup_fixup_commits
        # Assert: fixup commits removed
        # Assert: HEAD at correct position
```

### Integration Tests

**Update:** `tests/test_main_integration.py`

```python
class TestFixupApproachIntegration:
    """Integration tests for fixup commit approach."""

    def test_end_to_end_single_target(self):
        """Test complete flow with single target commit."""
        # Setup: repo with changes to squash
        # Execute: full git-autosquash run
        # Assert: changes squashed correctly
        # Assert: no fixup commits left

    def test_end_to_end_multiple_targets(self):
        """Test complete flow with multiple target commits."""
        # Setup: repo with hunks for different targets
        # Execute: full git-autosquash run
        # Assert: all hunks squashed to correct targets

    def test_overlapping_hunks_same_file(self):
        """Test multiple hunks in same file."""
        # Setup: multiple non-overlapping hunks in one file
        # Execute: full git-autosquash run
        # Assert: all hunks applied correctly

    def test_conflict_resolution_workflow(self):
        """Test conflict detection and resolution."""
        # Setup: repo with conflicting changes
        # Execute: git-autosquash (should pause at conflict)
        # Simulate: user resolves conflict
        # Execute: git rebase --continue
        # Assert: rebase completes successfully

    def test_stash_preservation(self):
        """Test that unstaged changes are preserved."""
        # Setup: repo with staged + unstaged changes
        # Execute: git-autosquash on staged changes
        # Assert: unstaged changes restored after rebase
```

### Edge Cases

```python
class TestFixupEdgeCases:
    """Test edge cases in fixup approach."""

    def test_empty_hunks_skipped(self):
        """Test that empty hunks are skipped."""

    def test_binary_file_changes(self):
        """Test handling binary file hunks."""

    def test_large_files(self):
        """Test efficiency with large files."""

    def test_pre_commit_hook_failure(self):
        """Test handling when hook fails during autosquash."""

    def test_user_cancellation(self):
        """Test cleanup when user cancels rebase."""

    def test_multiple_hunks_same_target(self):
        """Test multiple fixups for same target commit."""
```

---

## Implementation Steps

### Step 1: Create FixupCommitManager (3 hours)

**Tasks:**
1. Create `src/git_autosquash/fixup_commit_manager.py`
2. Implement `FixupCommitManager` class
3. Implement `create_fixup_commits_atomic` with rollback
4. Implement `execute_autosquash_rebase`
5. Implement cleanup methods
6. Write unit tests in `tests/test_fixup_commit_manager.py`

**Deliverables:**
- ✓ New FixupCommitManager class (~200 lines)
- ✓ Unit tests (~150 lines)

### Step 2: Integrate with RebaseManager (2 hours)

**Tasks:**
1. Modify `execute_squash` to use FixupCommitManager
2. Add import for FixupCommitManager
3. Update error handling
4. Keep old methods temporarily (for safety)

**Deliverables:**
- ✓ Modified execute_squash method
- ✓ Integration working with feature flag

### Step 3: Testing & Validation (2 hours)

**Tasks:**
1. Run existing test suite
2. Add integration tests
3. Manual testing with complex scenarios:
   - Multiple target commits
   - Overlapping hunks
   - Conflicts
   - Pre-commit hook modifications

**Deliverables:**
- ✓ All tests passing
- ✓ Integration tests added
- ✓ Manual testing completed

### Step 4: Cleanup & Documentation (2 hours)

**Tasks:**
1. Remove old rebase methods (~750 lines)
2. Update docstrings
3. Update CLAUDE.md architecture section
4. Update docs/technical/rebase-strategy.md

**Deliverables:**
- ✓ Code cleaned up
- ✓ Documentation updated

### Step 5: Release (1 hour)

**Tasks:**
1. Update CHANGELOG.md
2. Version bump
3. Create release PR
4. Review and merge

**Total estimate:** 10 hours

---

## Risk Assessment

### Low Risk Areas

✓ **Git autosquash reliability:** Battle-tested git feature
✓ **Simpler code:** Fewer bugs due to reduced complexity
✓ **Standard git workflow:** Users familiar with fixup commits

### Medium Risk Areas

⚠ **Different conflict patterns:** May encounter conflicts in different places than current approach
⚠ **Pre-commit hook behavior:** Hooks run on each fixup commit creation if not suppressed
⚠ **Performance with many fixups:** Need to test with 100+ fixup commits

### Mitigation Strategies

1. **Comprehensive testing:** Edge cases, large repos, complex scenarios
2. **Gradual rollout:** Feature flag for phased deployment
3. **Keep old code:** Available for reference/regression testing
4. **Clear documentation:** Explain new workflow to users

---

## Performance Comparison

### Current Approach

```
n target commits → n rebase operations
Each rebase: start + patch + amend + continue

Example (5 target commits):
- 5× git rebase -i <commit>^
- 5× patch generation with line correction
- 5× git apply
- 5× git commit --amend
- 5× git rebase --continue
Total: ~25-30 git commands
```

### Proposed Approach

```
n hunks → n fixup commits + 1 rebase

Example (10 hunks to 5 target commits):
- 10× git commit --no-verify (fast, no hooks)
- 1× git rebase -i --autosquash
Total: ~11 git commands
```

**Expected improvement:** 50-70% fewer git operations

---

## Success Metrics

1. **Code reduction:** ~750 lines removed from RebaseManager
2. **Fewer git operations:** Single rebase vs O(n) sequential rebases
3. **Simpler logic:** No custom line number correction
4. **Maintained correctness:** All existing tests pass
5. **Better performance:** Faster execution for multiple target commits

---

## Open Questions

1. **Should we support non-autosquash git versions?**
   → Autosquash available since Git 1.7.12 (2012), likely safe to require

2. **How to handle very large numbers of fixup commits (100+)?**
   → Test performance; may need progress reporting

3. **Should fixup commits be visible to user during creation?**
   → Current plan: create silently; consider adding verbose mode

4. **What if pre-commit hooks take a long time?**
   → Hooks skipped for fixups, only run during autosquash

---

## Appendix: Git Autosquash Reference

### How Git Autosquash Works

```bash
# Manual workflow:
git commit -m "feat: add login"          # abc123
git commit -m "fixup! feat: add login"   # def456

git rebase -i --autosquash HEAD~2
# Git automatically generates todo:
#   pick abc123 feat: add login
#   fixup def456 fixup! feat: add login
```

### Fixup Commit Format

```
fixup! <subject line of target commit>
```

Git matches the subject line and places the fixup commit after its target.

### Autosquash Options

```bash
--autosquash        # Enable automatic fixup placement (default in some configs)
--no-autosquash     # Disable (manual todo editing required)
```

### Configuration

```bash
# Enable autosquash by default
git config --global rebase.autosquash true
```

Our implementation explicitly passes `--autosquash` to avoid depending on user config.
