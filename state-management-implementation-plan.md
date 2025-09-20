# Complete Implementation Plan: State Management with --continue/--abort

## Executive Summary

This document outlines a comprehensive plan to fix critical issues in git-autosquash's stash management and implement robust state recovery mechanisms. The primary goals are:

1. Fix the critical stash reference bug that could cause data loss
2. Implement persistent state management for operation recovery
3. Add `--continue` and `--abort` commands matching git's conventions
4. Provide clear user guidance during conflicts
5. Ensure no data loss in any failure scenario

## Critical Issues Being Addressed

### 1. Stash Reference Race Condition (HIGH RISK - DATA LOSS)
**Current Problem**: The code assumes `stash@{0}` always refers to the stash it just created
```python
self._stash_ref = "stash@{0}"  # WRONG - assumes no other stashes exist
```

**Risk Scenario**:
- User has existing stashes: `stash@{0}`, `stash@{1}`, `stash@{2}`
- git-autosquash creates new stash (becomes new `stash@{0}`)
- Another process creates a stash (shifts indices)
- git-autosquash tries to pop `stash@{0}` - gets wrong stash!
- **Result**: User's changes are lost or wrong changes applied

### 2. No Recovery Path from Conflicts
**Current Problem**: When rebase conflicts occur, users must manually track their stashed changes
- No persistent record of stash SHA
- No clear instructions for recovery
- State lost if terminal closes

### 3. Silent Failures in Stash Restoration
**Current Problem**: Stash restoration failures are only logged, not handled
```python
print(f"DEBUG: Failed to restore stash: {result.stderr}")
print("DEBUG: You may need to manually restore with: git stash pop")
```
- User may not see debug messages
- No specific stash reference provided
- No automated recovery mechanism

## Rollback Strategy (Git-Based)

### Before Starting Implementation

```bash
# 1. Ensure current fixes are committed
git status  # Should be clean
git log --oneline -3  # Verify commits c14bbb7 and 19dbffe are present

# 2. Create feature branch for new work
git checkout -b feature/state-management-with-recovery

# 3. Verify branch creation
git branch --show-current  # Should show: feature/state-management-with-recovery
```

### Development Strategy

Each phase will be implemented as a separate commit:
```bash
# After Phase 1
git add -A
git commit -m "fix: Replace hardcoded stash references with SHA tracking"

# After Phase 2
git add -A
git commit -m "feat: Add persistent state management for operation recovery"

# After Phase 3
git add -A
git commit -m "feat: Add --continue and --abort commands"

# And so on...
```

### If Issues Arise

```bash
# Option 1: Complete rollback
git checkout simplify-remove-worktree-strategy
# All new work disappears, back to stable state

# Option 2: Selective rollback
git reset --hard <last-good-commit>
# Keep good changes, discard problematic ones

# Option 3: Cherry-pick working parts
git checkout simplify-remove-worktree-strategy
git cherry-pick <commit-sha>  # Pick specific working commits
```

## Phase 1: Fix Critical Stash Reference Issues

### 1.1 Replace Hardcoded stash@{0} with Proper Reference Capture

**File**: `src/git_autosquash/rebase_manager.py`

**Current Code** (3 locations, lines ~180, ~197, ~208):
```python
# BROKEN - assumes stash@{0} is our stash
if result.returncode == 0:
    self._stash_ref = "stash@{0}"
```

**New Implementation**:
```python
def _create_and_store_stash(self, message: str) -> Optional[str]:
    """Create a stash and return its SHA reference.

    Uses git stash create + store to get a reliable SHA reference
    instead of assuming stash@{0}.

    Args:
        message: Description for the stash

    Returns:
        SHA of created stash, or None if failed
    """
    # Step 1: Create stash object without modifying stash list
    # This returns a SHA that uniquely identifies the stash
    create_result = self.git_ops.run_git_command(
        ["stash", "create", message]
    )

    if create_result.returncode != 0:
        logger.error(f"Failed to create stash: {create_result.stderr}")
        return None

    stash_sha = create_result.stdout.strip()
    if not stash_sha:
        # No changes to stash (working tree might be clean)
        logger.info("No changes to stash")
        return None

    # Step 2: Store the stash object in the stash list
    # This makes it visible in 'git stash list'
    store_result = self.git_ops.run_git_command(
        ["stash", "store", "-m", message, stash_sha]
    )

    if store_result.returncode != 0:
        logger.error(f"Failed to store stash {stash_sha}: {store_result.stderr}")
        # The stash object exists but isn't in the list
        # We can still use it by SHA
        logger.warning(f"Stash created but not stored in list. SHA: {stash_sha}")

    logger.info(f"Created stash with SHA: {stash_sha}")
    return stash_sha
```

**Update _handle_working_tree_state()**:
```python
def _handle_working_tree_state(self) -> None:
    """Handle working tree state before rebase."""
    status = self.git_ops.get_working_tree_status()

    # Validate status data
    if not isinstance(status, dict):
        raise ValidationError("Invalid working tree status format")

    operation_type = None
    message = None

    if status.get("has_staged", False) and status.get("has_unstaged", False):
        # Mixed changes: stash only unstaged changes, keep staged changes in index
        operation_type = "mixed"
        message = "git-autosquash: temporary stash of unstaged changes"

        # Use --keep-index to stash only unstaged changes
        stash_sha = self._create_stash_with_options(
            message, ["--keep-index"]
        )

    elif status.get("has_staged", False) and not status.get("has_unstaged", False):
        # Staged changes only: must stash before rebase
        operation_type = "staged_only"
        message = "git-autosquash: temporary stash of staged changes"

        # Use --staged to stash only staged changes
        stash_sha = self._create_stash_with_options(
            message, ["--staged"]
        )

    elif not status.get("has_staged", False) and status.get("has_unstaged", False):
        # Unstaged changes only: must stash before rebase
        operation_type = "unstaged_only"
        message = "git-autosquash: temporary stash of unstaged changes"

        # Stash all working tree changes
        stash_sha = self._create_and_store_stash(message)

    else:
        # Clean working tree, nothing to stash
        logger.debug("Working tree is clean, no stashing needed")
        return

    if stash_sha:
        self._stash_ref = stash_sha

        # Save state for recovery
        self._save_operation_state(
            stash_sha=stash_sha,
            operation_type=operation_type,
            message=message
        )

        logger.info(f"Working tree prepared. Stash SHA: {stash_sha[:8]}")
    else:
        raise GitOperationError(
            f"Failed to stash {operation_type} changes",
            recovery_suggestion="Please stash or commit your changes manually"
        )
```

### 1.2 Add Proper Logging

**Setup Logger**:
```python
# At top of rebase_manager.py
import logging
from pathlib import Path
import json
import time
import os

logger = logging.getLogger(__name__)

class RebaseManager:
    def __init__(self, git_ops, merge_base):
        self.git_ops = git_ops
        self.merge_base = merge_base
        self._stash_ref = None
        self._original_branch = None
        self._batch_ops = None

        # Initialize logging
        self._setup_logging()

        # Initialize state manager
        self.state_manager = AutoSquashState(git_ops.repo_path)

    def _setup_logging(self):
        """Configure logging for the rebase manager."""
        # Set log level from environment or default to INFO
        log_level = os.environ.get("GIT_AUTOSQUASH_LOG_LEVEL", "INFO")
        logger.setLevel(getattr(logging, log_level))

        # Add handler if none exists
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
```

**Replace Debug Prints**:
```python
# Replace all instances of:
print(f"DEBUG: {message}")

# With appropriate logging:
logger.debug(message)  # For debug info
logger.info(message)   # For user-facing info
logger.warning(message)  # For warnings
logger.error(message)   # For errors
```

## Phase 2: Implement State File Management

### 2.1 Create State Management Module

**New File**: `src/git_autosquash/state_manager.py`

```python
"""Persistent state management for git-autosquash operations.

This module provides reliable state tracking across process interruptions,
enabling recovery from conflicts, crashes, and user interruptions.
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any
import fcntl
import tempfile

logger = logging.getLogger(__name__)


class StateFileError(Exception):
    """Raised when state file operations fail."""
    pass


class AutoSquashState:
    """Manages persistent state for git-autosquash operations.

    State is stored in .git/git-autosquash-state.json with atomic writes
    and file locking to prevent corruption from concurrent access.
    """

    VERSION = "1.0"
    STATE_FILENAME = "git-autosquash-state.json"

    def __init__(self, repo_path: str):
        """Initialize state manager.

        Args:
            repo_path: Path to git repository root
        """
        self.repo_path = Path(repo_path)
        self.git_dir = self.repo_path / ".git"

        # Handle worktrees which have a .git file pointing to the real git dir
        if self.git_dir.is_file():
            with open(self.git_dir) as f:
                # Format: "gitdir: /path/to/.git/worktrees/name"
                gitdir_line = f.read().strip()
                if gitdir_line.startswith("gitdir: "):
                    self.git_dir = Path(gitdir_line[8:])

        self.state_file_path = self.git_dir / self.STATE_FILENAME

        # Lock file for concurrent access protection
        self.lock_file_path = self.git_dir / f".{self.STATE_FILENAME}.lock"

    def save_state(self,
                   stash_sha: str,
                   operation_type: str,
                   original_branch: str,
                   original_head: str,
                   target_commits: list = None,
                   command_args: list = None) -> None:
        """Save operation state for recovery.

        Uses atomic write with temporary file and rename to prevent
        corruption if process is killed during write.

        Args:
            stash_sha: SHA of stashed changes
            operation_type: Type of operation (staged_only/unstaged_only/mixed)
            original_branch: Branch name before operation
            original_head: HEAD commit SHA before operation
            target_commits: List of commits being modified
            command_args: Original command arguments

        Raises:
            StateFileError: If state cannot be saved
        """
        state = {
            "version": self.VERSION,
            "stash_sha": stash_sha,
            "operation_type": operation_type,
            "original_branch": original_branch,
            "original_head": original_head,
            "timestamp": time.time(),
            "timestamp_readable": datetime.now().isoformat(),
            "pid": os.getpid(),
            "rebase_in_progress": False,
            "target_commits": target_commits or [],
            "command_args": command_args or []
        }

        try:
            # Write to temporary file first
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.git_dir,
                prefix=".tmp-autosquash-state-"
            )

            try:
                with os.fdopen(temp_fd, 'w') as f:
                    json.dump(state, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())  # Force write to disk

                # Atomic rename (on POSIX systems)
                os.rename(temp_path, self.state_file_path)

                logger.info(f"State saved to {self.state_file_path}")
                logger.debug(f"State contents: {state}")

            except Exception:
                # Clean up temp file if something went wrong
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

        except Exception as e:
            raise StateFileError(f"Failed to save state: {e}") from e

    def load_state(self) -> Optional[Dict[str, Any]]:
        """Load saved state if it exists.

        Validates state file format and version compatibility.

        Returns:
            State dictionary if valid state exists, None otherwise

        Raises:
            StateFileError: If state file is corrupted
        """
        if not self.state_file_path.exists():
            return None

        try:
            with open(self.state_file_path, 'r') as f:
                # Use file locking to prevent reading while another process writes
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    state = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # Validate state structure
            if not self.validate_state(state):
                raise StateFileError("Invalid state file format")

            # Check version compatibility
            if state.get("version") != self.VERSION:
                logger.warning(
                    f"State file version mismatch. "
                    f"Expected {self.VERSION}, got {state.get('version')}"
                )
                # For now, we'll try to continue but may need migration logic later

            return state

        except json.JSONDecodeError as e:
            raise StateFileError(f"Corrupted state file: {e}") from e
        except Exception as e:
            raise StateFileError(f"Failed to load state: {e}") from e

    def update_state(self, **updates) -> None:
        """Update existing state with new values.

        Args:
            **updates: Key-value pairs to update in state

        Raises:
            StateFileError: If state doesn't exist or update fails
        """
        state = self.load_state()
        if not state:
            raise StateFileError("No state to update")

        state.update(updates)
        state["last_updated"] = time.time()

        # Re-save the entire state
        self.save_state(**{
            k: state[k]
            for k in ["stash_sha", "operation_type", "original_branch",
                     "original_head", "target_commits", "command_args"]
            if k in state
        })

    def clear_state(self) -> None:
        """Remove state file after successful completion.

        Also removes lock file if it exists.
        """
        if self.state_file_path.exists():
            try:
                self.state_file_path.unlink()
                logger.info("State file cleared")
            except Exception as e:
                logger.error(f"Failed to remove state file: {e}")

        if self.lock_file_path.exists():
            try:
                self.lock_file_path.unlink()
            except Exception:
                pass  # Lock file cleanup is best-effort

    def validate_state(self, state: Dict[str, Any]) -> bool:
        """Validate state file integrity and required fields.

        Args:
            state: State dictionary to validate

        Returns:
            True if state is valid, False otherwise
        """
        required_fields = [
            "version", "stash_sha", "operation_type",
            "original_branch", "timestamp"
        ]

        for field in required_fields:
            if field not in state:
                logger.error(f"State missing required field: {field}")
                return False

        # Validate types
        if not isinstance(state.get("stash_sha"), str):
            logger.error("Invalid stash_sha type")
            return False

        if state.get("operation_type") not in ["staged_only", "unstaged_only", "mixed"]:
            logger.error(f"Invalid operation_type: {state.get('operation_type')}")
            return False

        # Check timestamp is reasonable (within last 7 days)
        age = time.time() - state.get("timestamp", 0)
        if age > 7 * 24 * 3600:
            logger.warning(f"State file is {age / 3600:.1f} hours old")
            # Old but not invalid

        return True

    def has_saved_state(self) -> bool:
        """Check if a saved state exists.

        Returns:
            True if valid state file exists
        """
        if not self.state_file_path.exists():
            return False

        try:
            state = self.load_state()
            return state is not None
        except StateFileError:
            return False

    def get_state_age(self) -> Optional[float]:
        """Get age of saved state in seconds.

        Returns:
            Age in seconds, or None if no state exists
        """
        state = self.load_state()
        if not state:
            return None

        return time.time() - state.get("timestamp", 0)

    def format_state_summary(self) -> str:
        """Format a human-readable summary of the current state.

        Returns:
            Formatted state summary string
        """
        state = self.load_state()
        if not state:
            return "No saved state"

        age = self.get_state_age()
        age_str = self._format_duration(age) if age else "unknown"

        return f"""
╔══════════════════════════════════════════════════════════════╗
║               Git-AutoSquash Saved State                     ║
╚══════════════════════════════════════════════════════════════╝

Operation Type: {state.get('operation_type', 'unknown')}
Stash SHA: {state.get('stash_sha', 'unknown')[:12]}...
Original Branch: {state.get('original_branch', 'unknown')}
Original HEAD: {state.get('original_head', 'unknown')[:8]}
Created: {state.get('timestamp_readable', 'unknown')}
Age: {age_str}
Process ID: {state.get('pid', 'unknown')}
Rebase Active: {'Yes' if state.get('rebase_in_progress') else 'No'}

Target Commits: {len(state.get('target_commits', []))} commits
Command Args: {' '.join(state.get('command_args', []))}
"""

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable form.

        Args:
            seconds: Duration in seconds

        Returns:
            Human-readable duration string
        """
        if seconds < 60:
            return f"{seconds:.0f} seconds"
        elif seconds < 3600:
            return f"{seconds / 60:.0f} minutes"
        elif seconds < 86400:
            return f"{seconds / 3600:.1f} hours"
        else:
            return f"{seconds / 86400:.1f} days"
```

### 2.2 State File Location and Format

**Location**: `.git/git-autosquash-state.json`

**Why .git directory?**
- Automatically ignored by git
- Cleaned up if repository is deleted
- One state per repository (handles multiple repos)
- Follows git's own convention (`.git/rebase-merge`, `.git/MERGE_HEAD`, etc.)

**Example State File**:
```json
{
  "version": "1.0",
  "stash_sha": "3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a",
  "operation_type": "mixed",
  "original_branch": "feature/new-authentication",
  "original_head": "abc123def456789",
  "timestamp": 1703123456.789,
  "timestamp_readable": "2024-01-15T10:30:56.789000",
  "pid": 12345,
  "rebase_in_progress": true,
  "target_commits": [
    "def456abc123789",
    "789abc123def456"
  ],
  "command_args": ["--line-by-line"]
}
```

## Phase 3: Add --continue and --abort Commands

### 3.1 Update Argument Parser

**File**: `src/git_autosquash/main.py`

```python
def setup_argument_parser() -> argparse.ArgumentParser:
    """Set up and return the command line argument parser."""

    parser = argparse.ArgumentParser(
        prog="git-autosquash",
        description="Automatically squash changes back into historical commits",
    )

    # Existing arguments
    parser.add_argument(
        "--line-by-line",
        action="store_true",
        help="Use line-by-line hunk splitting instead of default git hunks",
    )
    parser.add_argument(
        "--auto-accept",
        action="store_true",
        help="Automatically accept all hunks with blame-identified targets, bypass TUI",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes (requires --auto-accept)",
    )

    # NEW: Recovery commands
    parser.add_argument(
        "--continue",
        dest="continue_operation",  # Avoid Python keyword
        action="store_true",
        help="Continue a previously interrupted git-autosquash operation"
    )
    parser.add_argument(
        "--abort",
        action="store_true",
        help="Abort an interrupted operation and restore original state"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show status of any interrupted operation"
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    return parser
```

### 3.2 Implement Command Handlers

**File**: `src/git_autosquash/recovery_handlers.py` (NEW)

```python
"""Handlers for --continue, --abort, and --status commands."""

import logging
import sys
from typing import Optional
from pathlib import Path

from .git_ops import GitOps
from .state_manager import AutoSquashState, StateFileError
from .exceptions import GitAutoSquashError, GitOperationError

logger = logging.getLogger(__name__)


def handle_continue(git_ops: GitOps) -> int:
    """Continue an interrupted git-autosquash operation.

    This function:
    1. Loads the saved state
    2. Verifies rebase is complete
    3. Restores stashed changes
    4. Cleans up state file

    Args:
        git_ops: Git operations handler

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    state_manager = AutoSquashState(git_ops.repo_path)

    # Load state
    state = state_manager.load_state()
    if not state:
        print("❌ No interrupted operation found to continue")
        print("ℹ️  Use 'git-autosquash --status' to check for saved state")
        return 1

    print("📋 Loading saved state...")
    print(f"   Stash SHA: {state['stash_sha'][:12]}...")
    print(f"   Operation type: {state['operation_type']}")
    print(f"   Original branch: {state['original_branch']}")

    # Check if rebase is still in progress
    if is_rebase_in_progress(git_ops):
        print("\n⚠️  Rebase is still in progress!")
        print("Please complete the rebase first:")
        print("  1. Resolve any remaining conflicts")
        print("  2. Stage resolved files: git add <files>")
        print("  3. Continue rebase: git rebase --continue")
        print("  4. Then run: git-autosquash --continue")
        return 1

    # Verify we're on the expected branch
    current_branch = git_ops.get_current_branch()
    if current_branch != state['original_branch']:
        print(f"\n⚠️  Expected to be on branch '{state['original_branch']}'")
        print(f"   but currently on '{current_branch}'")

        response = input("Continue anyway? [y/N]: ").lower().strip()
        if response != 'y':
            print("Aborted by user")
            return 1

    # Restore stashed changes
    print("\n📦 Restoring stashed changes...")
    success = restore_stashed_changes(git_ops, state)

    if success:
        print("✅ Successfully restored working tree changes")
        state_manager.clear_state()
        print("🧹 State file cleaned up")
        return 0
    else:
        print("\n❌ Failed to restore stashed changes")
        print(f"Your changes are still stashed at: {state['stash_sha']}")
        print("\nTo manually restore:")
        print(f"  git stash apply {state['stash_sha']}")
        print("\nTo clear state file:")
        print("  git-autosquash --abort")
        return 1


def handle_abort(git_ops: GitOps) -> int:
    """Abort an interrupted operation and restore original state.

    This function:
    1. Loads the saved state
    2. Aborts any active rebase
    3. Restores stashed changes
    4. Cleans up state file

    Args:
        git_ops: Git operations handler

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    state_manager = AutoSquashState(git_ops.repo_path)

    # Load state
    state = state_manager.load_state()
    if not state:
        print("❌ No interrupted operation found to abort")
        return 1

    print("🛑 Aborting git-autosquash operation...")
    print(f"   Stash SHA: {state['stash_sha'][:12]}...")
    print(f"   Original branch: {state['original_branch']}")

    # Abort rebase if in progress
    if is_rebase_in_progress(git_ops):
        print("\n🔄 Aborting active rebase...")
        result = git_ops.run_git_command(["rebase", "--abort"])
        if result.returncode == 0:
            print("✅ Rebase aborted")
        else:
            print(f"⚠️  Failed to abort rebase: {result.stderr}")
            print("You may need to manually run: git rebase --abort")

    # Check out original branch if needed
    current_branch = git_ops.get_current_branch()
    if current_branch != state['original_branch']:
        print(f"\n🔀 Switching back to branch '{state['original_branch']}'...")
        result = git_ops.run_git_command(["checkout", state['original_branch']])
        if result.returncode != 0:
            print(f"⚠️  Failed to checkout original branch: {result.stderr}")

    # Restore stashed changes
    print("\n📦 Restoring stashed changes...")
    success = restore_stashed_changes(git_ops, state)

    if success:
        print("✅ Successfully restored working tree changes")
    else:
        print(f"⚠️  Failed to restore stashed changes")
        print(f"Your changes are still stashed at: {state['stash_sha']}")
        print(f"Try manually: git stash apply {state['stash_sha']}")

    # Always clear state file on abort
    state_manager.clear_state()
    print("🧹 State file cleaned up")

    return 0 if success else 1


def handle_status(git_ops: GitOps) -> int:
    """Show status of any interrupted operation.

    Args:
        git_ops: Git operations handler

    Returns:
        Exit code (0 for success)
    """
    state_manager = AutoSquashState(git_ops.repo_path)

    if not state_manager.has_saved_state():
        print("✅ No interrupted operations")
        return 0

    # Display formatted state summary
    print(state_manager.format_state_summary())

    # Check current git status
    if is_rebase_in_progress(git_ops):
        print("\n⚠️  REBASE IN PROGRESS")
        print("Complete or abort the rebase before continuing:")
        print("  - To continue: resolve conflicts, git add, git rebase --continue")
        print("  - To abort: git rebase --abort")

    # Verify stash still exists
    state = state_manager.load_state()
    if state and not stash_exists(git_ops, state['stash_sha']):
        print("\n⚠️  WARNING: Stashed changes not found!")
        print("The stash may have been manually dropped or lost.")

    print("\nAvailable commands:")
    print("  git-autosquash --continue  # Resume after rebase completion")
    print("  git-autosquash --abort     # Abort and restore original state")

    return 0


def restore_stashed_changes(git_ops: GitOps, state: dict) -> bool:
    """Restore stashed changes from saved state.

    Args:
        git_ops: Git operations handler
        state: Saved state dictionary

    Returns:
        True if successful, False otherwise
    """
    stash_sha = state['stash_sha']
    operation_type = state['operation_type']

    # First verify the stash exists
    if not stash_exists(git_ops, stash_sha):
        logger.error(f"Stash {stash_sha} not found")
        return False

    # Different restoration strategies based on operation type
    if operation_type == "mixed":
        # Originally had --keep-index, so we stashed unstaged changes
        # These should be restored to working tree
        logger.info("Restoring unstaged changes from mixed operation")
        result = git_ops.run_git_command(["stash", "apply", stash_sha])

    elif operation_type == "staged_only":
        # Originally stashed staged changes with --staged
        # These should be restored to the index
        logger.info("Restoring staged changes")
        result = git_ops.run_git_command(["stash", "apply", "--index", stash_sha])

    elif operation_type == "unstaged_only":
        # Originally stashed all working tree changes
        # Restore to working tree
        logger.info("Restoring unstaged changes")
        result = git_ops.run_git_command(["stash", "apply", stash_sha])

    else:
        logger.error(f"Unknown operation type: {operation_type}")
        return False

    if result.returncode != 0:
        # Check if it's a conflict during stash application
        if "CONFLICT" in result.stderr or "conflict" in result.stderr.lower():
            print("\n⚠️  Conflicts occurred while restoring stashed changes")
            print("This can happen if the rebase modified the same files.")
            print("\nYour changes are partially applied with conflict markers.")
            print("Please resolve the conflicts manually, then:")
            print("  1. Stage resolved files: git add <files>")
            print("  2. Drop the stash: git stash drop " + stash_sha[:12])
            print("\nAlternatively, reset and try manual application:")
            print("  1. Reset working tree: git reset --hard")
            print(f"  2. Apply stash manually: git stash apply {stash_sha[:12]}")
        else:
            logger.error(f"Failed to apply stash: {result.stderr}")
        return False

    # Successfully applied, now drop the stash
    logger.info("Stash applied successfully, dropping from stash list")
    drop_result = git_ops.run_git_command(["stash", "drop", stash_sha])
    if drop_result.returncode != 0:
        logger.warning(f"Failed to drop stash (non-critical): {drop_result.stderr}")

    return True


def stash_exists(git_ops: GitOps, stash_sha: str) -> bool:
    """Check if a stash SHA exists in the repository.

    Args:
        git_ops: Git operations handler
        stash_sha: SHA of the stash to check

    Returns:
        True if stash exists, False otherwise
    """
    # Check if the object exists in git
    result = git_ops.run_git_command(["cat-file", "-t", stash_sha])
    if result.returncode != 0:
        return False

    # Verify it's a commit object (stashes are commits)
    return result.stdout.strip() == "commit"


def is_rebase_in_progress(git_ops: GitOps) -> bool:
    """Check if a rebase is currently in progress.

    Args:
        git_ops: Git operations handler

    Returns:
        True if rebase is active, False otherwise
    """
    # Check for rebase directories
    git_dir = Path(git_ops.repo_path) / ".git"

    # Handle worktrees
    if git_dir.is_file():
        with open(git_dir) as f:
            gitdir_line = f.read().strip()
            if gitdir_line.startswith("gitdir: "):
                git_dir = Path(gitdir_line[8:])

    rebase_merge = git_dir / "rebase-merge"
    rebase_apply = git_dir / "rebase-apply"

    return rebase_merge.exists() or rebase_apply.exists()
```

### 3.3 Update Main Entry Point

**File**: `src/git_autosquash/main.py`

```python
def main():
    """Main entry point for git-autosquash."""

    # Parse arguments
    parser = setup_argument_parser()
    args = parser.parse_args()

    # Initialize git operations
    try:
        git_ops = GitOps()
    except Exception as e:
        print(f"Failed to initialize git operations: {e}")
        return 1

    # Handle recovery commands first
    if args.continue_operation:
        from .recovery_handlers import handle_continue
        return handle_continue(git_ops)

    if args.abort:
        from .recovery_handlers import handle_abort
        return handle_abort(git_ops)

    if args.status:
        from .recovery_handlers import handle_status
        return handle_status(git_ops)

    # Check for interrupted operations before starting new one
    state_manager = AutoSquashState(git_ops.repo_path)
    if state_manager.has_saved_state():
        print("⚠️  Detected interrupted git-autosquash operation")

        # Show brief status
        state = state_manager.load_state()
        if state:
            age = state_manager.get_state_age()
            age_str = state_manager._format_duration(age) if age else "unknown"
            print(f"   Created: {age_str} ago")
            print(f"   Stash: {state['stash_sha'][:12]}...")
            print(f"   Branch: {state['original_branch']}")

        print("\nOptions:")
        print("  git-autosquash --continue  # Resume operation")
        print("  git-autosquash --abort     # Abort and restore")
        print("  git-autosquash --status    # Show details")
        print("\nCannot start new operation until previous one is resolved.")
        return 1

    # Continue with normal operation...
    # (existing code)
```

## Phase 4: Enhanced Conflict Handling

### 4.1 Update RebaseConflictError Handling

**File**: `src/git_autosquash/rebase_manager.py`

```python
def execute_squash(self, mappings: List[HunkTargetMapping]) -> bool:
    """Execute the squash operation for approved mappings.

    Enhanced with proper state management and conflict handling.
    """
    if not mappings:
        return True

    # Store original branch for cleanup
    self._original_branch = self.git_ops.get_current_branch()
    if not self._original_branch:
        raise ValueError("Cannot determine current branch")

    # Get original HEAD for state
    original_head_result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
    original_head = original_head_result.stdout.strip() if original_head_result.returncode == 0 else None

    try:
        # Group hunks by target commit
        commit_hunks = self._group_hunks_by_commit(mappings)

        # Check working tree state and handle stashing if needed
        self._handle_working_tree_state()

        # Save command arguments for state
        import sys
        command_args = sys.argv[1:]  # Skip program name

        # Update state to indicate rebase starting
        if self._stash_ref:
            self.state_manager.update_state(
                rebase_in_progress=True,
                target_commits=list(commit_hunks.keys()),
                command_args=command_args
            )

        # Execute rebase for each target commit
        target_commits = self._get_commit_order(set(commit_hunks.keys()))
        logger.info(f"Processing {len(target_commits)} target commits")

        for target_commit in target_commits:
            hunks = commit_hunks[target_commit]
            logger.info(f"Applying {len(hunks)} hunks to {target_commit[:8]}")

            success = self._apply_hunks_to_commit(target_commit, hunks)
            if not success:
                logger.error(f"Failed to apply hunks to commit {target_commit[:8]}")
                return False

        # Restore stash if we created one (success path)
        if self._stash_ref:
            self._restore_working_tree_changes()

        # Clear state file on success
        self.state_manager.clear_state()

        return True

    except RebaseConflictError as e:
        # Don't cleanup on rebase conflicts - preserve state for recovery
        self._handle_conflict_error(e)
        raise

    except Exception:
        # Cleanup on any other error
        self._cleanup_on_error()
        raise


def _handle_conflict_error(self, error: RebaseConflictError) -> None:
    """Handle rebase conflict with clear user guidance.

    Args:
        error: The conflict error with file information
    """
    # Load current state for display
    state = self.state_manager.load_state()
    if not state:
        # Shouldn't happen, but handle gracefully
        logger.error("No state found during conflict handling")
        print("\n❌ Rebase conflict detected but state was not saved properly.")
        print("Your changes may be in the git stash list. Check: git stash list")
        return

    # Format conflict message with recovery instructions
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                      REBASE CONFLICT DETECTED                        ║
╚══════════════════════════════════════════════════════════════════════╝

Your working tree changes are safely stashed and will be restored after
the rebase is completed.

📦 Stash Information:
   SHA: {stash_sha}
   Type: {operation_type}
   Created: {timestamp}

❌ Conflicted Files:
   {conflict_files}

📝 To Resolve and Continue:
   1. Fix conflicts in the files listed above
   2. Stage resolved files:
      git add <resolved-files>
   3. Continue the rebase:
      git rebase --continue
   4. Restore your changes:
      git-autosquash --continue

🛑 To Abort and Restore Original State:
   git-autosquash --abort

ℹ️  Your original changes are safe! They will be restored after you
   resolve the conflicts or abort the operation.

💡 Tips:
   - Use 'git status' to see conflict details
   - Use 'git diff' to see conflict markers
   - Use 'git-autosquash --status' to check saved state
""".format(
        stash_sha=state['stash_sha'][:12],
        operation_type=state['operation_type'],
        timestamp=state.get('timestamp_readable', 'unknown'),
        conflict_files='\n   '.join(f"- {f}" for f in error.conflicted_files)
    ))
```

### 4.2 Improve Error Recovery

**File**: `src/git_autosquash/rebase_manager.py`

```python
def _restore_working_tree_changes(self) -> None:
    """Restore stashed changes after successful rebase.

    Enhanced with better error handling and conflict detection.
    """
    if not self._stash_ref:
        return

    logger.info(f"Restoring stashed changes from {self._stash_ref[:12]}")

    # Determine restoration method based on operation type
    state = self.state_manager.load_state()
    operation_type = state.get('operation_type') if state else None

    if operation_type == "staged_only":
        # Restore to index
        result = self.git_ops.run_git_command(
            ["stash", "apply", "--index", self._stash_ref]
        )
    else:
        # Restore to working tree
        result = self.git_ops.run_git_command(
            ["stash", "apply", self._stash_ref]
        )

    if result.returncode != 0:
        self._handle_stash_restore_failure(result.stderr)
    else:
        # Success - drop the stash
        logger.info("Stash applied successfully, dropping from list")
        self.git_ops.run_git_command(["stash", "drop", self._stash_ref])
        self._stash_ref = None


def _handle_stash_restore_failure(self, error_msg: str) -> None:
    """Handle failure to restore stashed changes.

    Args:
        error_msg: Error message from git stash apply
    """
    if "CONFLICT" in error_msg or "conflict" in error_msg.lower():
        print("""
⚠️  Conflicts While Restoring Stashed Changes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The rebase was successful, but conflicts occurred while restoring
your working tree changes. This can happen when the rebase modified
the same parts of files that had uncommitted changes.

Your changes are partially applied with conflict markers (<<<< >>>>).

To resolve:
1. Review and fix the conflicts in your working tree
2. Stage the resolved files: git add <files>
3. Drop the stash: git stash drop {stash_ref}

Alternative - Reset and manual application:
1. Reset to clean state: git reset --hard
2. Manually apply stash: git stash apply {stash_ref}
3. Resolve any conflicts
""".format(stash_ref=self._stash_ref[:12]))
    else:
        print(f"""
❌ Failed to Restore Working Tree Changes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Error: {error_msg}

Your changes are still safely stashed at: {self._stash_ref[:12]}

To manually restore:
  git stash apply {self._stash_ref[:12]}

To see stash contents:
  git stash show -p {self._stash_ref[:12]}
""")
```

## Phase 5: Documentation Updates

### 5.1 Update CLI Options Reference

**File**: `docs/reference/cli-options.md`

Add after the existing options:

```markdown
### `--continue`

**Usage**: `git-autosquash --continue`

**Description**: Continue a previously interrupted git-autosquash operation after resolving conflicts.

**When to use**:
- After resolving rebase conflicts and running `git rebase --continue`
- After a git-autosquash operation was interrupted (Ctrl+C, system crash, etc.)
- When recovering from any error that left state preserved

**Example**:
```bash
# After resolving rebase conflicts
git add resolved_file.txt
git rebase --continue
git-autosquash --continue  # Restores your working tree changes
```

**What it does**:
1. Verifies the rebase is complete
2. Restores stashed working tree changes
3. Cleans up the state file

### `--abort`

**Usage**: `git-autosquash --abort`

**Description**: Abort an interrupted operation and restore the original state.

**When to use**:
- When you want to cancel an in-progress git-autosquash operation
- After encountering conflicts you don't want to resolve
- When something goes wrong and you want to start over

**Example**:
```bash
# Abort everything and restore original state
git-autosquash --abort
```

**What it does**:
1. Aborts any active rebase
2. Restores stashed working tree changes
3. Returns to original branch
4. Cleans up the state file

### `--status`

**Usage**: `git-autosquash --status`

**Description**: Show the status of any interrupted git-autosquash operation.

**When to use**:
- To check if there's an interrupted operation
- To see details about saved state
- To get recovery instructions

**Example**:
```bash
$ git-autosquash --status

╔══════════════════════════════════════════════════════════════╗
║               Git-AutoSquash Saved State                     ║
╚══════════════════════════════════════════════════════════════╝

Operation Type: mixed
Stash SHA: 3f4a5b6c7d8e...
Original Branch: feature/auth
Created: 2024-01-15T10:30:56
Age: 5 minutes

Available commands:
  git-autosquash --continue  # Resume after rebase completion
  git-autosquash --abort     # Abort and restore original state
```
```

### 5.2 Create Conflict Resolution Guide

**New File**: `docs/user-guide/conflict-resolution.md`

```markdown
# Conflict Resolution Guide

This guide explains how to handle conflicts that may occur during git-autosquash operations and how to use the recovery commands.

## Understanding git-autosquash Conflicts

Conflicts can occur in two situations:

1. **Rebase Conflicts**: When applying changes to historical commits
2. **Stash Restoration Conflicts**: When restoring your working tree after rebase

## State Management

git-autosquash automatically saves your working tree state before making any changes. This ensures your work is never lost, even if:
- Conflicts occur during rebase
- The process is interrupted (Ctrl+C)
- Your terminal closes unexpectedly
- System crashes or restarts

### The State File

Your operation state is saved in `.git/git-autosquash-state.json` containing:
- SHA reference to your stashed changes
- Original branch and commit
- Operation type and parameters
- Timestamp and process information

## Handling Rebase Conflicts

When rebase conflicts occur, you'll see:

```
╔══════════════════════════════════════════════════════════════════════╗
║                      REBASE CONFLICT DETECTED                        ║
╚══════════════════════════════════════════════════════════════════════╝

Your working tree changes are safely stashed and will be restored after
the rebase is completed.

📦 Stash Information:
   SHA: a3f4b2c89d1e
   Type: mixed
   Created: 2024-01-15T10:30:56

❌ Conflicted Files:
   - src/auth/login.py
   - src/auth/session.py
```

### Step-by-Step Resolution

1. **Review the conflicts**:
   ```bash
   git status                    # See conflicted files
   git diff                      # See conflict markers
   ```

2. **Fix conflicts in each file**:
   - Open conflicted files in your editor
   - Look for conflict markers: `<<<<<<<`, `=======`, `>>>>>>>`
   - Choose the correct version or merge both
   - Remove conflict markers

3. **Stage resolved files**:
   ```bash
   git add src/auth/login.py
   git add src/auth/session.py
   # Or stage all resolved files:
   git add -A
   ```

4. **Continue the rebase**:
   ```bash
   git rebase --continue
   ```

5. **Restore your working tree changes**:
   ```bash
   git-autosquash --continue
   ```

### Aborting Instead

If you don't want to resolve conflicts:

```bash
git-autosquash --abort
```

This will:
1. Abort the rebase
2. Restore your working tree changes
3. Return to the original state

## Handling Stash Restoration Conflicts

Sometimes conflicts occur when restoring your stashed changes after a successful rebase. This happens when the rebase modified the same lines you had uncommitted changes to.

### Resolution Steps

1. **Review conflicts in working tree**:
   ```bash
   git status
   git diff
   ```

2. **Resolve conflicts manually**:
   - Fix conflict markers in affected files
   - Stage resolved files

3. **Drop the stash** (it's already applied):
   ```bash
   git stash list                          # Find your stash
   git stash drop stash@{0}                # Drop it
   ```

### Alternative: Reset and Retry

If the conflicts are too complex:

```bash
# Reset to clean state
git reset --hard

# Manually apply stash
git stash apply <stash-sha>

# Resolve any conflicts
```

## Recovery Commands Reference

### Check Status

Always start by checking the current state:

```bash
git-autosquash --status
```

This shows:
- Whether an operation is interrupted
- Stash information
- Age of saved state
- Available recovery commands

### Continue Operation

After resolving conflicts and completing rebase:

```bash
git-autosquash --continue
```

Requirements:
- Rebase must be complete
- No unresolved conflicts

### Abort Operation

To cancel and restore original state:

```bash
git-autosquash --abort
```

This is always safe and will:
- Abort any active rebase
- Restore working tree changes
- Clean up state file

## Manual Recovery

If automated recovery fails, you can manually recover using the state file:

1. **Check the state file**:
   ```bash
   cat .git/git-autosquash-state.json
   ```

2. **Find your stash SHA**:
   ```json
   {
     "stash_sha": "a3f4b2c89d1e4f6a8b9c0d2e3f4a5b6c7d8e9f0a",
     ...
   }
   ```

3. **Manually apply the stash**:
   ```bash
   git stash apply a3f4b2c89d1e
   ```

4. **Clean up state file**:
   ```bash
   rm .git/git-autosquash-state.json
   ```

## Preventing Conflicts

### Best Practices

1. **Commit or stash before running git-autosquash**:
   ```bash
   git stash push -m "Save before autosquash"
   git-autosquash
   git stash pop
   ```

2. **Process changes in smaller batches**:
   - Work on one file or module at a time
   - Run git-autosquash more frequently

3. **Review target commits first**:
   - Understand what commits will be modified
   - Anticipate potential conflicts

## Troubleshooting

### "No interrupted operation found"

This means there's no state file. Check:
- Are you in the right repository?
- Did you already run --continue or --abort?
- Was the state file manually deleted?

### "Stash not found"

The stash SHA in the state file doesn't exist:
- It may have been manually dropped
- Check `git stash list` for your changes
- The state file may be corrupted

### "Rebase still in progress"

Complete or abort the rebase first:
```bash
# Option 1: Complete it
git rebase --continue

# Option 2: Abort it
git rebase --abort
```

### State File Corruption

If the state file is corrupted:

1. Back it up:
   ```bash
   cp .git/git-autosquash-state.json ~/backup-state.json
   ```

2. Try manual recovery using the stash SHA from the backup

3. Remove the corrupted file:
   ```bash
   rm .git/git-autosquash-state.json
   ```

## Getting Help

If you encounter issues not covered here:

1. Run `git-autosquash --status` and save the output
2. Check `git status` and `git stash list`
3. Report issues at: https://github.com/andrewleech/git-autosquash/issues

Include:
- The status output
- Git version: `git --version`
- git-autosquash version: `git-autosquash --version`
- Description of what you were doing when the issue occurred
```

### 5.3 Update Troubleshooting Guide

**File**: `docs/user-guide/troubleshooting.md`

Add new section after existing content:

```markdown
## Interrupted Operations

### Detecting Interrupted Operations

**Symptoms**:
```bash
$ git-autosquash
⚠️  Detected interrupted git-autosquash operation
   Created: 5 minutes ago
   Stash: a3f4b2c89d1e...
   Branch: feature/auth

Options:
  git-autosquash --continue  # Resume operation
  git-autosquash --abort     # Abort and restore
  git-autosquash --status    # Show details
```

**Diagnosis**:
```bash
# Check status
git-autosquash --status

# Check if rebase is active
git status

# Check state file
ls -la .git/git-autosquash-state.json
```

**Solutions**:

Continue after resolving conflicts:
```bash
git-autosquash --continue
```

Abort and restore:
```bash
git-autosquash --abort
```

### Stash Recovery Issues

**Problem**: "Failed to restore stashed changes"

**Diagnosis**:
```bash
# Check if stash exists
git stash list

# Check state file for SHA
cat .git/git-autosquash-state.json | grep stash_sha
```

**Solutions**:

Manual stash application:
```bash
# Get SHA from state file
git stash apply <sha-from-state-file>
```

Force recovery:
```bash
# Reset and retry
git reset --hard
git stash pop
```

### State File Issues

**Problem**: "State file corrupted or incompatible"

**Diagnosis**:
```bash
# Check file validity
python3 -m json.tool .git/git-autosquash-state.json
```

**Solutions**:

Manual cleanup:
```bash
# Backup state file
cp .git/git-autosquash-state.json ~/state-backup.json

# Remove corrupted file
rm .git/git-autosquash-state.json

# Manually recover using stash SHA from backup
git stash apply <sha-from-backup>
```

### Concurrent Operations

**Problem**: Multiple git-autosquash instances

**Prevention**:
- Always check `git-autosquash --status` before starting
- Complete or abort previous operations first

**Recovery**:
```bash
# Kill any running git-autosquash processes
pkill -f git-autosquash

# Check and clean up state
git-autosquash --status
git-autosquash --abort  # If needed
```
```

## Phase 6: Comprehensive Testing

### 6.1 Unit Tests for State Management

**New File**: `tests/test_state_manager.py`

```python
"""Tests for state management functionality."""

import json
import time
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from git_autosquash.state_manager import AutoSquashState, StateFileError


class TestAutoSquashState:
    """Test state management operations."""

    def test_save_and_load_state(self, tmp_git_repo):
        """Test saving and loading state."""
        state_manager = AutoSquashState(tmp_git_repo)

        # Save state
        state_manager.save_state(
            stash_sha="abc123def456",
            operation_type="mixed",
            original_branch="feature/test",
            original_head="789abc",
            target_commits=["commit1", "commit2"],
            command_args=["--line-by-line"]
        )

        # Load state
        loaded = state_manager.load_state()

        assert loaded is not None
        assert loaded["stash_sha"] == "abc123def456"
        assert loaded["operation_type"] == "mixed"
        assert loaded["original_branch"] == "feature/test"
        assert loaded["target_commits"] == ["commit1", "commit2"]
        assert loaded["command_args"] == ["--line-by-line"]
        assert "timestamp" in loaded
        assert "pid" in loaded

    def test_state_validation(self, tmp_git_repo):
        """Test state validation."""
        state_manager = AutoSquashState(tmp_git_repo)

        # Valid state
        valid_state = {
            "version": "1.0",
            "stash_sha": "abc123",
            "operation_type": "staged_only",
            "original_branch": "main",
            "timestamp": time.time()
        }
        assert state_manager.validate_state(valid_state) is True

        # Missing required field
        invalid_state = {
            "version": "1.0",
            "operation_type": "staged_only"
        }
        assert state_manager.validate_state(invalid_state) is False

        # Invalid operation type
        invalid_state = {
            "version": "1.0",
            "stash_sha": "abc123",
            "operation_type": "invalid",
            "original_branch": "main",
            "timestamp": time.time()
        }
        assert state_manager.validate_state(invalid_state) is False

    def test_state_file_corruption_handling(self, tmp_git_repo):
        """Test handling of corrupted state files."""
        state_manager = AutoSquashState(tmp_git_repo)

        # Create corrupted state file
        state_file = Path(tmp_git_repo) / ".git" / "git-autosquash-state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{ corrupted json")

        # Should raise StateFileError
        with pytest.raises(StateFileError) as exc:
            state_manager.load_state()
        assert "Corrupted state file" in str(exc.value)

    def test_atomic_write(self, tmp_git_repo):
        """Test atomic write prevents partial writes."""
        state_manager = AutoSquashState(tmp_git_repo)

        # Simulate interrupted write by patching os.rename to fail
        with patch('os.rename', side_effect=OSError("Simulated failure")):
            with pytest.raises(StateFileError):
                state_manager.save_state(
                    stash_sha="abc123",
                    operation_type="mixed",
                    original_branch="main",
                    original_head="def456"
                )

        # State file should not exist due to atomic write failure
        assert not state_manager.state_file_path.exists()

    def test_clear_state(self, tmp_git_repo):
        """Test state cleanup."""
        state_manager = AutoSquashState(tmp_git_repo)

        # Save state
        state_manager.save_state(
            stash_sha="abc123",
            operation_type="mixed",
            original_branch="main",
            original_head="def456"
        )

        assert state_manager.has_saved_state()

        # Clear state
        state_manager.clear_state()

        assert not state_manager.has_saved_state()
        assert state_manager.load_state() is None

    def test_update_state(self, tmp_git_repo):
        """Test updating existing state."""
        state_manager = AutoSquashState(tmp_git_repo)

        # Save initial state
        state_manager.save_state(
            stash_sha="abc123",
            operation_type="mixed",
            original_branch="main",
            original_head="def456"
        )

        # Update state
        state_manager.update_state(
            rebase_in_progress=True,
            target_commits=["commit1", "commit2"]
        )

        # Verify updates
        loaded = state_manager.load_state()
        assert loaded["rebase_in_progress"] is True
        assert loaded["target_commits"] == ["commit1", "commit2"]
        assert loaded["stash_sha"] == "abc123"  # Original values preserved

    def test_worktree_support(self, tmp_git_repo):
        """Test state management in git worktrees."""
        # Create a worktree
        worktree_path = Path(tmp_git_repo).parent / "worktree"
        # Simulate worktree .git file
        worktree_git = worktree_path / ".git"
        worktree_path.mkdir(parents=True)
        worktree_git.write_text(f"gitdir: {tmp_git_repo}/.git/worktrees/test")

        state_manager = AutoSquashState(str(worktree_path))

        # Should resolve to main git dir
        assert "worktrees" in str(state_manager.git_dir)
```

### 6.2 Integration Tests for Recovery

**New File**: `tests/test_recovery_integration.py`

```python
"""Integration tests for --continue and --abort functionality."""

import subprocess
import json
from pathlib import Path
import pytest

from git_autosquash.recovery_handlers import (
    handle_continue, handle_abort, handle_status
)


class TestRecoveryIntegration:
    """Test recovery command integration."""

    def test_continue_after_successful_rebase(self, conflict_repo):
        """Test --continue after rebase completes successfully."""
        repo_path, commits = conflict_repo.create_simple_repo()

        # Create initial state file simulating interrupted operation
        state = {
            "version": "1.0",
            "stash_sha": self._create_test_stash(repo_path),
            "operation_type": "mixed",
            "original_branch": "main",
            "original_head": commits["head"],
            "timestamp": time.time(),
            "rebase_in_progress": False
        }

        state_file = Path(repo_path) / ".git" / "git-autosquash-state.json"
        state_file.write_text(json.dumps(state))

        # Run --continue
        git_ops = GitOps(repo_path)
        result = handle_continue(git_ops)

        assert result == 0
        assert not state_file.exists()

        # Verify stash was applied
        status = git_ops.run_git_command(["status", "--porcelain"])
        assert status.stdout.strip() != ""  # Should have changes

    def test_abort_during_rebase(self, conflict_repo):
        """Test --abort while rebase is in progress."""
        repo_path, commits = conflict_repo.create_conflict_scenario()

        # Start a rebase that will conflict
        git_ops = GitOps(repo_path)
        git_ops.run_git_command([
            "rebase", "-i", commits["target_commit"]
        ])

        # Create state file
        state = {
            "version": "1.0",
            "stash_sha": self._create_test_stash(repo_path),
            "operation_type": "staged_only",
            "original_branch": "feature",
            "original_head": commits["head"],
            "timestamp": time.time(),
            "rebase_in_progress": True
        }

        state_file = Path(repo_path) / ".git" / "git-autosquash-state.json"
        state_file.write_text(json.dumps(state))

        # Run --abort
        result = handle_abort(git_ops)

        assert result == 0
        assert not state_file.exists()

        # Verify rebase was aborted
        assert not self._is_rebase_in_progress(repo_path)

        # Verify we're back on original branch
        current_branch = git_ops.get_current_branch()
        assert current_branch == "feature"

    def test_continue_with_stash_conflicts(self, conflict_repo):
        """Test --continue when stash restoration has conflicts."""
        repo_path, commits = conflict_repo.create_simple_repo()

        # Modify a file
        test_file = Path(repo_path) / "test.txt"
        test_file.write_text("modified content")

        # Create stash
        git_ops = GitOps(repo_path)
        stash_result = git_ops.run_git_command(["stash", "create", "test"])
        stash_sha = stash_result.stdout.strip()

        # Modify same file differently (will conflict with stash)
        test_file.write_text("different content")
        git_ops.run_git_command(["add", "."])
        git_ops.run_git_command(["commit", "-m", "Conflicting change"])

        # Create state file
        state = {
            "version": "1.0",
            "stash_sha": stash_sha,
            "operation_type": "unstaged_only",
            "original_branch": "main",
            "original_head": commits["head"],
            "timestamp": time.time()
        }

        state_file = Path(repo_path) / ".git" / "git-autosquash-state.json"
        state_file.write_text(json.dumps(state))

        # Run --continue (should handle conflict gracefully)
        result = handle_continue(git_ops)

        # Should indicate failure but provide recovery instructions
        assert result != 0

        # State file should still exist for manual recovery
        assert state_file.exists()

    def test_status_command(self, tmp_git_repo):
        """Test --status command output."""
        # Create state file
        state = {
            "version": "1.0",
            "stash_sha": "abc123def456789",
            "operation_type": "mixed",
            "original_branch": "feature/test",
            "original_head": "789abc",
            "timestamp": time.time() - 300,  # 5 minutes ago
            "timestamp_readable": "2024-01-15T10:30:00",
            "pid": 12345,
            "rebase_in_progress": False,
            "target_commits": ["commit1"],
            "command_args": ["--line-by-line"]
        }

        state_file = Path(tmp_git_repo) / ".git" / "git-autosquash-state.json"
        state_file.parent.mkdir(exist_ok=True)
        state_file.write_text(json.dumps(state))

        git_ops = GitOps(tmp_git_repo)

        # Capture output
        import io
        import sys
        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            result = handle_status(git_ops)
            output = captured_output.getvalue()
        finally:
            sys.stdout = sys.__stdout__

        assert result == 0
        assert "Git-AutoSquash Saved State" in output
        assert "abc123def456" in output
        assert "feature/test" in output
        assert "5 minutes" in output

    def test_concurrent_operation_detection(self, tmp_git_repo):
        """Test detection of concurrent operations."""
        # Create state file from "another process"
        state = {
            "version": "1.0",
            "stash_sha": "abc123",
            "operation_type": "mixed",
            "original_branch": "main",
            "original_head": "def456",
            "timestamp": time.time(),
            "pid": 99999  # Different PID
        }

        state_file = Path(tmp_git_repo) / ".git" / "git-autosquash-state.json"
        state_file.parent.mkdir(exist_ok=True)
        state_file.write_text(json.dumps(state))

        # Try to start new operation
        from git_autosquash.main import check_interrupted_operation
        git_ops = GitOps(tmp_git_repo)

        has_interrupted = check_interrupted_operation(git_ops)
        assert has_interrupted is True

    def _create_test_stash(self, repo_path: str) -> str:
        """Helper to create a test stash."""
        test_file = Path(repo_path) / "stash_test.txt"
        test_file.write_text("stashed content")

        result = subprocess.run(
            ["git", "stash", "create", "test stash"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()

    def _is_rebase_in_progress(self, repo_path: str) -> bool:
        """Helper to check rebase status."""
        git_dir = Path(repo_path) / ".git"
        return (
            (git_dir / "rebase-merge").exists() or
            (git_dir / "rebase-apply").exists()
        )
```

## Phase 7: Performance and Edge Cases

### 7.1 Handle Edge Cases

**Additional checks to add**:

1. **Disk space checks before stashing**:
```python
import shutil

def check_disk_space(path: Path, required_mb: int = 100) -> bool:
    """Check if sufficient disk space is available."""
    stat = shutil.disk_usage(path)
    available_mb = stat.free / (1024 * 1024)
    return available_mb > required_mb
```

2. **Stale PID detection**:
```python
def is_process_running(pid: int) -> bool:
    """Check if a process with given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

# In state validation
if not is_process_running(state["pid"]):
    logger.warning("Original process no longer running")
```

3. **Submodule handling**:
```python
def has_submodule_changes(git_ops: GitOps) -> bool:
    """Check for uncommitted submodule changes."""
    result = git_ops.run_git_command(["submodule", "status"])
    if result.returncode == 0:
        # Leading + indicates uncommitted changes in submodule
        for line in result.stdout.splitlines():
            if line.startswith("+"):
                return True
    return False
```

## Implementation Timeline

### Week 1: Critical Fixes
- Day 1-2: Implement stash reference fix (Phase 1)
- Day 3-4: Add state management (Phase 2)
- Day 5: Testing and validation

### Week 2: Recovery Commands
- Day 1-2: Implement --continue/--abort/--status (Phase 3)
- Day 3: Enhanced conflict handling (Phase 4)
- Day 4-5: Integration testing

### Week 3: Polish and Documentation
- Day 1-2: Extract WorkingTreeStateManager (Phase 5)
- Day 3: Documentation updates (Phase 6)
- Day 4-5: Comprehensive testing and bug fixes

## Success Criteria

1. **No data loss**: Stash references are always correct
2. **Clear recovery path**: Users can always recover from interruptions
3. **Consistent with git**: --continue/--abort match git's patterns
4. **Well documented**: Clear guides for all scenarios
5. **Thoroughly tested**: >90% coverage of new code
6. **Backward compatible**: Existing workflows continue to work

## Risk Mitigation

### Risk: Breaking existing workflows
**Mitigation**:
- All changes on feature branch
- Extensive testing before merge
- Gradual rollout with testing on real repositories

### Risk: State file corruption
**Mitigation**:
- Atomic writes with temporary files
- JSON validation on load
- Clear corruption recovery procedures

### Risk: Platform compatibility
**Mitigation**:
- Test on Linux, macOS, Windows
- Handle file locking differences
- Fallback to simple stash@{n} if advanced features fail

This comprehensive plan addresses all critical issues identified in the code review while maintaining a clear path for implementation and rollback if needed.

---

## Implementation Progress

### Phase 1.1: Stash SHA Capture Tests & Implementation (COMPLETED ✅ 2024-09-21 17:00)

**Status**: ✅ COMPLETE - Critical data loss bug FIXED

**What was completed**:
1. ✅ Created comprehensive test suite in `tests/test_stash_management.py`
   - 11 tests covering SHA capture, restoration, and integration scenarios
   - All tests following TDD methodology (written first, then implementation)
   - Tests verify SHA-based tracking vs hardcoded `stash@{0}` approach

2. ✅ Implemented stash SHA tracking methods in `rebase_manager.py`:
   - `_create_and_store_stash()` - Uses `git stash create` + `git stash store` for reliable SHA
   - `_create_stash_with_options()` - Handles options like `--staged`, `--keep-index`
   - `_restore_stash_by_sha()` - Restores and drops stash using SHA reference

3. ✅ **CRITICAL FIX**: Replaced all hardcoded `stash@{0}` references with SHA tracking
   - Lines 180, 197, 208 in `_handle_working_tree_state()` method
   - Now uses proper SHA capture instead of assuming stash index positions
   - **Data loss risk eliminated** - stash references are now immune to concurrent stash operations

4. ✅ Added proper logging with `logging.getLogger(__name__)`
   - Replaced debug prints with structured logging
   - Error handling with informative messages

**Test Results**: 11/11 tests passing, 1 skipped (integration test for later)

**Key Technical Achievement**:
The critical race condition has been eliminated. Previously:
```python
# BROKEN - race condition risk
result = git_ops.run_git_command(["stash", "push", "--staged", "-m", "message"])
if result.returncode == 0:
    self._stash_ref = "stash@{0}"  # WRONG! Assumes stash position
```

Now:
```python
# FIXED - reliable SHA tracking
stash_sha = self._create_stash_with_options(message, ["--staged"])
if stash_sha:
    self._stash_ref = stash_sha  # Correct! Uses immutable SHA reference
```

**Verification**: All working tree scenarios (staged-only, unstaged-only, mixed) now use SHA-based stash tracking.

**Next Steps**: Ready for Phase 2 - State Management Infrastructure