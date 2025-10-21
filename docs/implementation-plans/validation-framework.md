# Implementation Plan: Validation Framework

**Status:** ✅ COMPLETE (Implemented in Phase 3)
**Complexity:** Medium
**Actual Time:** ~8 hours (matched estimate)
**Dependencies:** None (implemented independently)
**Commits:** 97288df, 346a802, 9074397

## Executive Summary

Add a comprehensive validation framework that normalizes all input sources (working-tree, index, commit) to a single commit for processing, then validates the final result via `git diff <start> <end>` to guarantee zero data corruption. This provides strong safety guarantees while simplifying input handling.

## Problem Statement

### Current Implementation Issues

The current approach handles different input sources inconsistently:

1. **Multiple code paths:** Different logic for working-tree, index, HEAD, and commit SHA inputs
2. **No validation:** No end-to-end check that processing completed correctly
3. **Inconsistent starting points:** Different baseline states for line numbers
4. **No corruption detection:** Silent failures can cause data loss
5. **Complex error recovery:** Unclear what state the repo is in after failure

**Pain Points:**
- `HunkParser.get_diff_hunks()` has 57 lines of branching logic for different sources (lines 53-110)
- No guarantee that hunks were applied correctly
- Line number correction depends on accurate starting state
- Difficult to debug when something goes wrong
- No automated way to detect data corruption

### Key Insight

By normalizing all inputs to a single commit first:
1. Processing always starts from consistent state (a commit)
2. Simple before/after validation via `git diff`
3. Easier to reason about and debug
4. Strong guarantee: if `git diff <start> <end>` is empty, no corruption occurred

---

## Current Architecture Analysis

### Current Input Handling (src/git_autosquash/hunk_parser.py:53-110)

```python
def get_diff_hunks(self, line_by_line: bool = False, source: str = "auto") -> List[DiffHunk]:
    if source == "auto":
        status = self.git_ops.get_working_tree_status()

        if status["is_clean"]:
            # Diff HEAD~1
        elif status["has_staged"] and not status["has_unstaged"]:
            # git diff --cached
        elif not status["has_staged"] and status["has_unstaged"]:
            # git diff
        else:
            # git diff --cached (ignore unstaged)

    elif source == "working-tree":
        # git diff
    elif source == "index":
        # git diff --cached
    elif source == "head" or source == "HEAD":
        # git show --format= HEAD
    else:
        # git show --format= <commit>
```

**Problems:**
- 5 different code paths
- No validation of results
- Inconsistent baseline for line numbers
- Working tree state can change between parsing and processing

### Current Context Management (src/git_autosquash/squash_context.py:34-81)

```python
@classmethod
def from_source(cls, source: str, git_ops: GitOps) -> "SquashContext":
    if source_lower in ["head"]:
        blame_ref = "HEAD~1"
        source_commit_value = None
    elif source_lower in ["auto", "working-tree", "index"]:
        blame_ref = "HEAD"
        source_commit_value = None
    else:
        blame_ref = f"{source}~1"
        source_commit_value = source
```

**Problems:**
- Tracks source indirectly via blame_ref
- No actual commit hash for working-tree/index
- Cannot validate against starting point

---

## Proposed Architecture

### New Flow

```
Input (any source)
    ↓
SourceNormalizer.normalize_to_commit()
    ├─ working-tree → create temp commit (--no-verify)
    ├─ index       → create temp commit (--no-verify)
    ├─ HEAD        → use HEAD hash
    └─ <commit>    → validate and use
    ↓
Record starting_commit hash
    ↓
Process hunks (fixup commits / current approach)
    ↓
ProcessingValidator.validate_processing()
    ├─ git diff <starting_commit> HEAD
    ├─ Assert: diff is empty
    └─ Raise ValidationError if differences found
    ↓
Cleanup temp commit (if created)
```

### Benefits

1. **Single code path:** All inputs normalized to commit before processing
2. **Validation guarantee:** `git diff <start> <end>` must be empty
3. **Simpler logic:** No conditional branching on source type
4. **Better debugging:** Always have starting commit hash for comparison
5. **Corruption detection:** Automatic detection of data loss/corruption
6. **Easier testing:** Consistent test setup (always from commits)

---

## Detailed Implementation

### Phase 1: SourceNormalizer Class

**New File:** `src/git_autosquash/source_normalizer.py`

```python
"""Normalize different input sources to single commit for processing."""

from typing import Optional
import logging
from git_autosquash.git_ops import GitOps

logger = logging.getLogger(__name__)


class SourceNormalizationError(Exception):
    """Raised when source normalization fails."""
    pass


class SourceNormalizer:
    """Normalize any input source to a single commit.

    This class handles converting working-tree changes, index changes,
    or commit references into a single commit hash that can be used as
    a consistent starting point for hunk processing.

    Attributes:
        git_ops: GitOps instance for git commands
        temp_commit_created: True if we created a temporary commit
        starting_commit: The normalized commit hash
    """

    def __init__(self, git_ops: GitOps):
        """Initialize the source normalizer.

        Args:
            git_ops: GitOps instance for git command execution
        """
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)
        self.temp_commit_created = False
        self.starting_commit: Optional[str] = None

    def normalize_to_commit(self, source: str) -> str:
        """Convert any source to a commit hash.

        This method handles all input source types and converts them
        to a single commit hash. For working-tree and index sources,
        it creates temporary commits (with --no-verify to skip hooks).

        Args:
            source: Input source specification:
                - 'working-tree': Unstaged changes in working tree
                - 'index': Staged changes in index
                - 'head' or 'HEAD': Current HEAD commit
                - 'auto': Auto-detect based on working tree status
                - '<commit>': Specific commit SHA or reference

        Returns:
            Commit hash to use as starting point

        Raises:
            SourceNormalizationError: If normalization fails

        Sets:
            self.temp_commit_created: True if temporary commit created
            self.starting_commit: The normalized commit hash
        """
        self.logger.info(f"Normalizing source: {source}")

        source_lower = source.lower()

        try:
            if source_lower == "working-tree":
                commit_hash = self._commit_working_tree()
                self.temp_commit_created = True

            elif source_lower == "index":
                commit_hash = self._commit_index()
                self.temp_commit_created = True

            elif source_lower in ["head"]:
                commit_hash = self._get_head_hash()
                self.temp_commit_created = False

            elif source_lower == "auto":
                commit_hash = self._auto_detect_and_commit()
                # temp_commit_created set by helper

            else:
                # Assume commit SHA or reference
                commit_hash = self._validate_and_resolve_commit(source)
                self.temp_commit_created = False

            self.starting_commit = commit_hash
            self.logger.info(
                f"Normalized to commit: {commit_hash[:8]} "
                f"(temp={self.temp_commit_created})"
            )
            return commit_hash

        except Exception as e:
            raise SourceNormalizationError(
                f"Failed to normalize source '{source}': {e}"
            )

    def _commit_working_tree(self) -> str:
        """Create temporary commit from working tree changes.

        Stages all changes (including untracked files) and creates a
        temporary commit with pre-commit hooks skipped.

        Returns:
            Commit hash of temporary commit

        Raises:
            SourceNormalizationError: If commit creation fails
        """
        self.logger.debug("Creating temporary commit from working tree")

        # Stage all changes (including untracked)
        result = self.git_ops.run_git_command(["add", "-A"])
        if result.returncode != 0:
            raise SourceNormalizationError(
                f"Failed to stage changes: {result.stderr}"
            )

        # Check if there are actually changes to commit
        result = self.git_ops.run_git_command(["diff", "--cached", "--quiet"])
        if result.returncode == 0:
            # No changes staged - use HEAD instead
            self.logger.debug("No changes to commit, using HEAD")
            return self._get_head_hash()

        # Create temporary commit (skip hooks with --no-verify)
        result = self.git_ops.run_git_command([
            "commit",
            "--no-verify",
            "-m", "TEMP: git-autosquash working tree snapshot"
        ])

        if result.returncode != 0:
            raise SourceNormalizationError(
                f"Failed to create temp commit: {result.stderr}"
            )

        return self._get_head_hash()

    def _commit_index(self) -> str:
        """Create temporary commit from staged changes only.

        Creates a temporary commit from the current index state,
        skipping pre-commit hooks.

        Returns:
            Commit hash of temporary commit

        Raises:
            SourceNormalizationError: If commit creation fails
        """
        self.logger.debug("Creating temporary commit from index")

        # Check if there are staged changes
        result = self.git_ops.run_git_command(["diff", "--cached", "--quiet"])
        if result.returncode == 0:
            # No staged changes - use HEAD instead
            self.logger.debug("No staged changes, using HEAD")
            return self._get_head_hash()

        # Create temporary commit (skip hooks with --no-verify)
        result = self.git_ops.run_git_command([
            "commit",
            "--no-verify",
            "-m", "TEMP: git-autosquash index snapshot"
        ])

        if result.returncode != 0:
            raise SourceNormalizationError(
                f"Failed to create temp commit: {result.stderr}"
            )

        return self._get_head_hash()

    def _auto_detect_and_commit(self) -> str:
        """Auto-detect state and create commit if needed.

        Detects the current working tree state and decides what to commit:
        - Clean: Use HEAD
        - Staged only: Commit index
        - Unstaged only: Commit working tree
        - Both: Commit index (unstaged handled by stash)

        Returns:
            Commit hash to use

        Sets:
            self.temp_commit_created: True if commit created
        """
        status = self.git_ops.get_working_tree_status()

        if status["is_clean"]:
            # Use HEAD
            self.temp_commit_created = False
            return self._get_head_hash()

        elif status["has_staged"] and not status["has_unstaged"]:
            # Commit staged changes only
            self.temp_commit_created = True
            return self._commit_index()

        elif not status["has_staged"] and status["has_unstaged"]:
            # Commit working tree
            self.temp_commit_created = True
            return self._commit_working_tree()

        else:
            # Both staged and unstaged - commit staged
            # (unstaged will be handled by stash in RebaseManager)
            self.temp_commit_created = True
            return self._commit_index()

    def _validate_and_resolve_commit(self, commit_ref: str) -> str:
        """Validate and resolve a commit reference to full SHA.

        Args:
            commit_ref: Commit SHA or reference (e.g., 'abc123', 'HEAD~1')

        Returns:
            Full commit SHA

        Raises:
            SourceNormalizationError: If commit doesn't exist
        """
        result = self.git_ops.run_git_command(["rev-parse", commit_ref])

        if result.returncode != 0:
            raise SourceNormalizationError(
                f"Invalid commit reference: {commit_ref}"
            )

        commit_sha = result.stdout.strip()

        # Verify commit exists
        result = self.git_ops.run_git_command(["cat-file", "-t", commit_sha])
        if result.returncode != 0 or result.stdout.strip() != "commit":
            raise SourceNormalizationError(
                f"Not a valid commit: {commit_ref}"
            )

        return commit_sha

    def _get_head_hash(self) -> str:
        """Get current HEAD commit hash.

        Returns:
            Full SHA of HEAD

        Raises:
            SourceNormalizationError: If HEAD cannot be resolved
        """
        result = self.git_ops.run_git_command(["rev-parse", "HEAD"])

        if result.returncode != 0:
            raise SourceNormalizationError(
                "Failed to get HEAD hash (detached HEAD?)"
            )

        return result.stdout.strip()

    def cleanup_temp_commit(self) -> None:
        """Remove temporary commit if we created one.

        Uses soft reset to remove the commit while preserving changes
        in the index/working tree.
        """
        if not self.temp_commit_created or not self.starting_commit:
            return

        self.logger.info("Cleaning up temporary commit")

        # Soft reset to parent (preserves changes)
        result = self.git_ops.run_git_command([
            "reset",
            "--soft",
            f"{self.starting_commit}~1"
        ])

        if result.returncode == 0:
            self.logger.debug("✓ Temporary commit removed")
            self.temp_commit_created = False
        else:
            self.logger.warning(
                f"Failed to cleanup temp commit: {result.stderr}"
            )
```

### Phase 2: ProcessingValidator Class

**New File:** `src/git_autosquash/validation.py`

```python
"""Validation framework for ensuring processing integrity."""

from typing import List
import logging
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when processing validation fails.

    This indicates potential data corruption or loss during processing.
    """
    pass


class ProcessingValidator:
    """Validate that processing completed without data corruption.

    This class provides end-to-end validation by comparing the starting
    commit with the final result. If `git diff <start> HEAD` shows any
    differences, data corruption occurred during processing.
    """

    def __init__(self, git_ops: GitOps):
        """Initialize the processing validator.

        Args:
            git_ops: GitOps instance for git command execution
        """
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)

    def validate_processing(
        self,
        starting_commit: str,
        description: str = "processing"
    ) -> bool:
        """Validate that current HEAD has same changes as starting commit.

        This is the primary validation method. It compares the starting
        commit (before processing) with current HEAD (after processing).
        If any differences exist, data corruption occurred.

        Args:
            starting_commit: The commit hash we started with
            description: Description for error messages

        Returns:
            True if validation passes

        Raises:
            ValidationError: If differences detected (data corruption)
        """
        self.logger.info(f"Validating {description}...")

        # Get current HEAD
        current_head = self._get_head_hash()

        self.logger.debug(
            f"Comparing {starting_commit[:8]} → {current_head[:8]}"
        )

        # Compare starting commit with current HEAD
        result = self.git_ops.run_git_command([
            "diff",
            "--exit-code",  # Exit with 1 if differences found
            starting_commit,
            current_head
        ])

        if result.returncode == 0:
            # No differences - validation passed
            self.logger.info(f"✓ Validation passed: {description}")
            return True

        elif result.returncode == 1:
            # Differences found - this is data corruption
            diff_output = result.stdout[:1000]  # First 1000 chars
            if len(result.stdout) > 1000:
                diff_output += "\n... (truncated)"

            raise ValidationError(
                f"Data corruption detected during {description}!\n"
                f"Starting commit: {starting_commit}\n"
                f"Current HEAD:    {current_head}\n"
                f"\nDifferences found:\n{diff_output}\n\n"
                f"This indicates that processing did not preserve all changes.\n"
                f"Use 'git diff {starting_commit[:8]} {current_head[:8]}' "
                f"to see full differences."
            )

        else:
            # Git command failed
            raise ValidationError(
                f"Validation failed to run: {result.stderr}"
            )

    def validate_hunk_coverage(
        self,
        starting_commit: str,
        processed_hunks: List[DiffHunk]
    ) -> bool:
        """Validate that all hunks from starting commit were processed.

        This is a pre-flight validation to ensure we're not missing any hunks.

        Args:
            starting_commit: The commit to validate against
            processed_hunks: The hunks we plan to process

        Returns:
            True if validation passes

        Raises:
            ValidationError: If hunk counts don't match
        """
        self.logger.debug("Validating hunk coverage...")

        # Get hunks from starting commit
        from git_autosquash.hunk_parser import HunkParser
        parser = HunkParser(self.git_ops)

        result = self.git_ops.run_git_command([
            "show", "--format=", starting_commit
        ])

        if result.returncode != 0:
            raise ValidationError(
                f"Failed to get hunks from {starting_commit}: {result.stderr}"
            )

        original_hunks = parser._parse_diff_output(result.stdout)

        # Compare counts
        original_count = len(original_hunks)
        processed_count = len(processed_hunks)

        if original_count != processed_count:
            raise ValidationError(
                f"Hunk count mismatch: {original_count} original, "
                f"{processed_count} to be processed. "
                f"This indicates hunks were lost during parsing."
            )

        self.logger.debug(
            f"✓ Hunk coverage validated: {processed_count} hunks"
        )
        return True

    def _get_head_hash(self) -> str:
        """Get current HEAD commit hash.

        Returns:
            Full SHA of HEAD
        """
        result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
        return result.stdout.strip()
```

### Phase 3: Integration Points

#### 3.1 Update RebaseManager

**File:** `src/git_autosquash/rebase_manager.py`

Add to execute_squash method:

```python
from git_autosquash.source_normalizer import SourceNormalizer
from git_autosquash.validation import ProcessingValidator, ValidationError

def execute_squash(
    self,
    mappings: List[HunkTargetMapping],
    context: SquashContext,
) -> bool:
    """Execute squash with input normalization and validation."""
    if not mappings:
        return True

    # Initialize components
    normalizer = SourceNormalizer(self.git_ops)
    validator = ProcessingValidator(self.git_ops)

    try:
        # Phase 1: Normalize input to commit
        # Note: source comes from context or needs to be passed separately
        source = context.source_commit or "auto"
        starting_commit = normalizer.normalize_to_commit(source)
        logger.info(f"Processing from commit: {starting_commit[:8]}")

        # Phase 2: Validate hunk coverage (pre-flight check)
        validator.validate_hunk_coverage(
            starting_commit,
            [m.hunk for m in mappings]
        )

        # Phase 3: Handle working tree state
        self._handle_working_tree_state()

        # Phase 4: Execute processing (fixup or current approach)
        # ... existing processing logic ...

        # Phase 5: CRITICAL VALIDATION
        validator.validate_processing(
            starting_commit,
            description="squash operation"
        )
        logger.info("✓ Processing validated - no corruption detected")

        # Phase 6: Cleanup temp commit if created
        normalizer.cleanup_temp_commit()

        # Phase 7: Restore stash if needed
        if self._stash_ref:
            self._restore_stash_by_sha(self._stash_ref)

        return True

    except ValidationError as e:
        # CRITICAL: Data corruption detected
        logger.error(f"VALIDATION FAILED: {e}")
        logger.error("Aborting to prevent data corruption")

        # Abort any in-progress operations
        if self.is_rebase_in_progress():
            self.git_ops.run_git_command(["rebase", "--abort"])

        # Cleanup temp commit
        normalizer.cleanup_temp_commit()

        # Restore working tree
        self._cleanup_on_error()

        raise

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        normalizer.cleanup_temp_commit()
        self._cleanup_on_error()
        raise
```

#### 3.2 Update HunkParser

**File:** `src/git_autosquash/hunk_parser.py`

Simplify to always parse from a commit:

```python
def get_diff_hunks(
    self,
    line_by_line: bool = False,
    from_commit: Optional[str] = None
) -> List[DiffHunk]:
    """Extract hunks from a commit.

    Args:
        line_by_line: If True, split hunks line-by-line
        from_commit: Commit hash to parse (required)

    Returns:
        List of DiffHunk objects

    Raises:
        ValueError: If from_commit not provided
    """
    if not from_commit:
        raise ValueError(
            "from_commit is required. Use SourceNormalizer to get commit hash."
        )

    # Parse from commit (always consistent)
    success, diff_output = self.git_ops._run_git_command(
        "show", "--format=", from_commit
    )

    if not success:
        return []

    hunks = self._parse_diff_output(diff_output)

    if line_by_line:
        hunks = self._split_hunks_line_by_line(hunks)

    return hunks
```

#### 3.3 Update main.py

**File:** `src/git_autosquash/main.py`

Update process_hunks_and_mappings:

```python
def process_hunks_and_mappings(
    git_ops: GitOps,
    merge_base: str,
    line_by_line: bool,
    source: str,
    blame_ref: str,
    context: SquashContext,
) -> tuple[List[HunkTargetMapping], List[HunkTargetMapping], str]:
    """Process hunks with source normalization.

    Returns:
        Tuple of (automatic_mappings, fallback_mappings, starting_commit)
    """
    # Normalize source to commit
    normalizer = SourceNormalizer(git_ops)
    starting_commit = normalizer.normalize_to_commit(source)
    print(f"Processing commit: {starting_commit[:8]}")

    # Parse hunks from normalized commit
    hunk_parser = HunkParser(git_ops)
    hunks = hunk_parser.get_diff_hunks(
        line_by_line=line_by_line,
        from_commit=starting_commit
    )

    if not hunks:
        print("No hunks found to process.")
        normalizer.cleanup_temp_commit()
        sys.exit(0)

    # Resolve targets
    resolver = HunkTargetResolver(git_ops, merge_base, context, blame_ref=blame_ref)
    mappings = resolver.resolve_targets(hunks)

    # Separate automatic vs fallback
    automatic_mappings = [m for m in mappings if not m.needs_user_selection]
    fallback_mappings = [m for m in mappings if m.needs_user_selection]

    return automatic_mappings, fallback_mappings, starting_commit
```

---

## Error Handling & Recovery

### Validation Failure (Data Corruption Detected)

**Scenario:** `git diff <start> HEAD` shows differences

**Response:**
1. Log detailed error with commit hashes
2. Abort any in-progress rebase
3. Cleanup temporary commit
4. Restore working tree to original state
5. Raise ValidationError with recovery instructions

**User sees:**
```
ERROR: Data corruption detected during squash operation!
  Starting commit: abc1234
  Current HEAD:    def5678

  Differences found:
  diff --git a/file.py b/file.py
  ... [truncated diff] ...

  This indicates that processing did not preserve all changes.
  Use 'git diff abc1234 def5678' to see full differences.

  Repository has been restored to original state.
```

### Normalization Failure

**Scenario:** Cannot create temporary commit or resolve reference

**Response:**
1. Log error details
2. Don't create any temporary commits
3. Exit cleanly
4. Provide clear error message

### Cleanup Failure

**Scenario:** Cannot remove temporary commit

**Response:**
1. Log warning (not critical error)
2. Provide manual cleanup instructions
3. Continue with validation (temp commit doesn't affect correctness)

---

## Testing Strategy

### Unit Tests

**New test file:** `tests/test_source_normalizer.py`

```python
class TestSourceNormalizer:
    """Test SourceNormalizer functionality."""

    def test_normalize_working_tree(self):
        """Test normalizing working tree to commit."""
        # Setup: repo with unstaged changes
        # Execute: normalize_to_commit("working-tree")
        # Assert: temp commit created
        # Assert: commit contains working tree changes

    def test_normalize_index(self):
        """Test normalizing index to commit."""
        # Setup: repo with staged changes
        # Execute: normalize_to_commit("index")
        # Assert: temp commit created
        # Assert: commit contains only staged changes

    def test_normalize_head(self):
        """Test normalizing HEAD (no temp commit)."""
        # Setup: clean repo
        # Execute: normalize_to_commit("HEAD")
        # Assert: no temp commit created
        # Assert: returns HEAD hash

    def test_normalize_commit_sha(self):
        """Test normalizing specific commit."""
        # Setup: repo with commit
        # Execute: normalize_to_commit("<sha>")
        # Assert: no temp commit created
        # Assert: returns validated commit hash

    def test_auto_detect_clean(self):
        """Test auto-detect with clean working tree."""
        # Setup: clean repo
        # Execute: normalize_to_commit("auto")
        # Assert: uses HEAD, no temp commit

    def test_auto_detect_staged(self):
        """Test auto-detect with staged changes."""
        # Setup: repo with staged changes
        # Execute: normalize_to_commit("auto")
        # Assert: commits index, temp commit created

    def test_cleanup_temp_commit(self):
        """Test cleanup removes temp commit."""
        # Setup: create temp commit
        # Execute: cleanup_temp_commit()
        # Assert: temp commit removed
        # Assert: changes preserved in index

    def test_normalize_invalid_commit(self):
        """Test error handling for invalid commit."""
        # Execute: normalize_to_commit("invalid")
        # Assert: raises SourceNormalizationError

    def test_normalize_empty_working_tree(self):
        """Test normalizing empty working tree falls back to HEAD."""
        # Setup: clean repo, call normalize_to_commit("working-tree")
        # Assert: returns HEAD, no temp commit
```

**New test file:** `tests/test_validation.py`

```python
class TestProcessingValidator:
    """Test ProcessingValidator functionality."""

    def test_validate_processing_success(self):
        """Test validation passes when no corruption."""
        # Setup: commit, process hunks correctly
        # Execute: validate_processing(starting_commit)
        # Assert: returns True, no exception

    def test_validate_processing_corruption_detected(self):
        """Test validation fails when corruption detected."""
        # Setup: commit, modify files incorrectly
        # Execute: validate_processing(starting_commit)
        # Assert: raises ValidationError
        # Assert: error contains diff output

    def test_validate_hunk_coverage_success(self):
        """Test hunk coverage validation passes."""
        # Setup: commit with 5 hunks, parse 5 hunks
        # Execute: validate_hunk_coverage(commit, hunks)
        # Assert: returns True

    def test_validate_hunk_coverage_mismatch(self):
        """Test hunk coverage validation fails on mismatch."""
        # Setup: commit with 5 hunks, only 4 processed
        # Execute: validate_hunk_coverage(commit, hunks)
        # Assert: raises ValidationError
        # Assert: error mentions count mismatch

    def test_validate_processing_with_conflicts(self):
        """Test validation after conflict resolution."""
        # Setup: commit, process with conflicts, resolve
        # Execute: validate_processing(starting_commit)
        # Assert: validation passes if resolved correctly
```

### Integration Tests

**Update:** `tests/test_main_integration.py`

```python
class TestValidationIntegration:
    """Integration tests for validation framework."""

    def test_end_to_end_with_validation(self):
        """Test complete flow with validation."""
        # Setup: repo with changes
        # Execute: full git-autosquash run
        # Assert: validation passes
        # Assert: temp commit cleaned up

    def test_working_tree_normalization(self):
        """Test processing working tree changes."""
        # Setup: unstaged changes
        # Execute: git-autosquash --source working-tree
        # Assert: temp commit created and cleaned up
        # Assert: validation passes

    def test_index_normalization(self):
        """Test processing index changes."""
        # Setup: staged changes
        # Execute: git-autosquash --source index
        # Assert: temp commit created and cleaned up
        # Assert: validation passes

    def test_validation_failure_recovery(self):
        """Test recovery when validation fails."""
        # Setup: inject corruption (modify files during processing)
        # Execute: git-autosquash
        # Assert: ValidationError raised
        # Assert: repo restored to original state
        # Assert: temp commit cleaned up
```

### Edge Cases

```python
class TestValidationEdgeCases:
    """Test edge cases in validation framework."""

    def test_very_large_commits(self):
        """Test validation with large commits (performance)."""

    def test_binary_files(self):
        """Test validation with binary file changes."""

    def test_detached_head_state(self):
        """Test normalization in detached HEAD state."""

    def test_merge_conflicts_during_processing(self):
        """Test validation after resolving merge conflicts."""

    def test_cleanup_failure_non_critical(self):
        """Test that cleanup failure doesn't block success."""

    def test_simultaneous_changes_to_working_tree(self):
        """Test handling when working tree modified during processing."""
```

---

## Implementation Steps

### Step 1: Create SourceNormalizer (3 hours)

**Tasks:**
1. Create `src/git_autosquash/source_normalizer.py`
2. Implement SourceNormalizer class
3. Implement normalization methods for each source type
4. Implement cleanup logic
5. Write unit tests in `tests/test_source_normalizer.py`

**Deliverables:**
- ✓ SourceNormalizer class (~200 lines)
- ✓ Unit tests (~200 lines)

### Step 2: Create ProcessingValidator (2 hours)

**Tasks:**
1. Create `src/git_autosquash/validation.py`
2. Implement ProcessingValidator class
3. Implement validation methods
4. Define ValidationError exception
5. Write unit tests in `tests/test_validation.py`

**Deliverables:**
- ✓ ProcessingValidator class (~150 lines)
- ✓ Unit tests (~150 lines)

### Step 3: Integration (2 hours)

**Tasks:**
1. Update RebaseManager.execute_squash
2. Update HunkParser.get_diff_hunks
3. Update main.py process_hunks_and_mappings
4. Update SquashContext if needed
5. Add integration tests

**Deliverables:**
- ✓ Updated RebaseManager
- ✓ Updated HunkParser
- ✓ Updated main.py
- ✓ Integration tests

### Step 4: Testing & Validation (2 hours)

**Tasks:**
1. Run full test suite
2. Test edge cases
3. Manual testing with different sources
4. Performance testing with large commits

**Deliverables:**
- ✓ All tests passing
- ✓ Edge cases handled
- ✓ Performance validated

### Step 5: Documentation (1 hour)

**Tasks:**
1. Update CLAUDE.md
2. Update docs/technical/architecture.md
3. Add validation section to docs
4. Update error handling docs

**Deliverables:**
- ✓ Documentation updated

**Total estimate:** 10 hours

---

## Safety Guarantees

### Strong Guarantees

✓ **No data loss:** Validation ensures all changes preserved
✓ **Corruption detection:** `git diff` detects any discrepancies
✓ **Atomic operations:** Temp commits cleaned up on failure
✓ **Recovery:** Clear rollback path on any error

### Validation Coverage

✓ **Pre-flight:** Hunk coverage validation before processing
✓ **Post-flight:** Full diff comparison after processing
✓ **Error handling:** Validation on failure paths
✓ **Cleanup:** Temp commit removal verified

---

## Performance Considerations

### Temporary Commit Overhead

**Cost:** O(1) git commit operation per run
**Impact:** Minimal (< 100ms for typical repos)
**Benefit:** Consistent starting point, simplifies logic

### Validation Overhead

**Cost:** O(1) git diff operation per run
**Impact:** Minimal (< 50ms for typical commits)
**Benefit:** Guarantee of correctness, catches corruption

### Memory Usage

Temporary commits use git's object store (efficient)
No additional memory overhead beyond normal git operations

---

## Success Metrics

1. **Correctness:** Zero data corruption (validated by git diff)
2. **Simplicity:** Single code path for all input sources
3. **Safety:** Automatic rollback on validation failure
4. **Debugging:** Always have starting commit for comparison
5. **Testing:** Easier test setup (always from commits)

---

## Open Questions

1. **Should we validate incrementally during processing?**
   → Current plan: single validation at end
   → Consider: checkpoints for long-running operations

2. **What to do if cleanup fails but validation passes?**
   → Current plan: log warning, provide manual instructions
   → Not critical as temp commit doesn't affect correctness

3. **Should we keep temp commits on failure for debugging?**
   → Current plan: clean up on all failures
   → Consider: --debug flag to preserve temp commits

4. **How to handle very large commits (Git performance)?**
   → Test with large repos
   → May need progress reporting for git diff

---

## Dependencies & Order

### Implementation Order Options

**Option A: Implement validation first (recommended)**
- Provides safety net for current implementation
- Can be tested independently
- Provides value even without fixup approach

**Option B: Implement with fixup approach**
- Validation integrated from the start
- Single large change
- More testing surface area

**Option C: Implement after fixup approach**
- Fixup approach provides benefits sooner
- Validation added as safety layer
- Two separate changes to review/test

### Recommendation

Implement validation framework first (Option A):
1. Provides immediate safety benefits
2. Can be tested thoroughly independently
3. Makes fixup approach implementation safer
4. Easier to review in isolation

---

## Appendix: Git Commands Reference

### Temporary Commit Creation

```bash
# Working tree to commit
git add -A
git commit --no-verify -m "TEMP: snapshot"

# Index to commit
git commit --no-verify -m "TEMP: snapshot"
```

### Validation

```bash
# Compare two commits
git diff --exit-code <start> <end>
# Exit code 0: no differences
# Exit code 1: differences found
# Exit code >1: error
```

### Cleanup

```bash
# Remove temp commit (soft reset)
git reset --soft HEAD~1
# Commits removed, changes preserved in index

# Hard reset (discard changes)
git reset --hard <commit>
```

### Commit Validation

```bash
# Resolve reference to SHA
git rev-parse <ref>

# Check if object is a commit
git cat-file -t <sha>
# Output: "commit" if valid
```
