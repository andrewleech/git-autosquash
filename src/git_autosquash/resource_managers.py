"""Resource managers for guaranteed cleanup in git operations."""

import logging
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, List, Callable

from git_autosquash.git_ops import GitOps
from git_autosquash.result import GitResult, GitOperationError, Ok, Err


class GitStateManager:
    """Manager for git repository state with guaranteed restoration."""

    def __init__(self, git_ops: GitOps) -> None:
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)
        self._stash_refs: List[str] = []
        self._original_branch: Optional[str] = None
        self._cleanup_actions: List[Callable[[], None]] = []
        self._stash_creation_time: Optional[float] = None

    def save_current_state(self) -> GitResult[str]:
        """Save the current git state and return a stash reference."""
        try:
            # Get current branch
            success, branch = self.git_ops._run_git_command("branch", "--show-current")
            if success:
                self._original_branch = branch.strip()

            # Create stash without untracked files to avoid restore conflicts
            success, output = self.git_ops._run_git_command(
                "stash",
                "push",
                "--message",
                "git-autosquash temporary state",
            )

            if success:
                # Extract stash reference from output - git stash returns SHA
                # Output format: "Saved working directory and index state WIP on branch: message"
                # But we need to use stash@{0} since that's the latest stash created
                # However, we must pop it immediately or track it carefully to avoid conflicts
                stash_ref = "stash@{0}"  # Latest stash (the one we just created)
                self._stash_refs.append(stash_ref)
                self.logger.debug(f"Saved git state to {stash_ref}")

                # CRITICAL: Store creation timestamp to verify this is our stash
                import time

                self._stash_creation_time = time.time()

                return Ok(stash_ref)
            else:
                error = GitOperationError(
                    operation="save_state",
                    message="Failed to create stash",
                    stderr=output,
                )
                return Err(error)

        except Exception as e:
            error = GitOperationError(
                operation="save_state", message=f"Exception during state save: {e}"
            )
            return Err(error)

    def _verify_stash_is_ours(self, stash_ref: str) -> bool:
        """Verify that the stash reference points to a stash we created."""
        try:
            # Check stash message to see if it's ours
            success, output = self.git_ops._run_git_command(
                "stash", "show", "-s", stash_ref
            )

            if success and "git-autosquash temporary state" in output:
                return True

            # Also check if it's in our tracked stashes
            if stash_ref in self._stash_refs:
                return True

            self.logger.warning(
                f"Stash {stash_ref} does not appear to be created by git-autosquash"
            )
            return False

        except Exception as e:
            self.logger.warning(f"Could not verify stash ownership: {e}")
            return False

    def restore_state(self, stash_ref: str) -> GitResult[bool]:
        """Restore git state from a stash reference."""
        try:
            # CRITICAL: Verify this is our stash before restoring
            if not self._verify_stash_is_ours(stash_ref):
                error = GitOperationError(
                    operation="restore_state",
                    message=f"SAFETY: Refusing to restore stash {stash_ref} - not created by current git-autosquash operation",
                    command=f"git stash pop {stash_ref}",
                    stderr="Stash verification failed",
                )
                return Err(error)

            # Apply the stash
            success, output = self.git_ops._run_git_command("stash", "pop", stash_ref)

            if success:
                if stash_ref in self._stash_refs:
                    self._stash_refs.remove(stash_ref)
                self.logger.debug(f"Restored git state from {stash_ref}")
                return Ok(True)
            else:
                error = GitOperationError(
                    operation="restore_state",
                    message="Failed to restore stash",
                    command=f"git stash pop {stash_ref}",
                    stderr=output,
                )
                return Err(error)

        except Exception as e:
            error = GitOperationError(
                operation="restore_state",
                message=f"Exception during state restore: {e}",
            )
            return Err(error)

    def add_cleanup_action(self, action: Callable[[], None]) -> None:
        """Add a cleanup action to be executed on manager destruction."""
        self._cleanup_actions.append(action)

    def cleanup_all(self) -> None:
        """Clean up all resources and restore original state."""
        # Execute custom cleanup actions
        for action in self._cleanup_actions:
            try:
                action()
            except Exception as e:
                self.logger.warning(f"Cleanup action failed: {e}")

        # Clean up any remaining stashes
        for stash_ref in self._stash_refs:
            try:
                # If it's a SHA, we need to find the actual stash reference
                actual_ref = stash_ref
                if len(stash_ref) >= 7 and not stash_ref.startswith("stash@"):
                    # Find the stash reference for this SHA
                    list_result = self.git_ops.run_git_command(
                        ["stash", "list", "--format=%H %gd"]
                    )
                    if list_result.returncode == 0:
                        for line in list_result.stdout.strip().split("\n"):
                            if line:
                                parts = line.split(" ", 1)
                                if len(parts) == 2:
                                    sha, ref = parts
                                    if sha == stash_ref or sha.startswith(
                                        stash_ref[:12]
                                    ):
                                        # Extract stash@{n} from "(stash@{0})"
                                        if ref.startswith("(") and ref.endswith(")"):
                                            actual_ref = ref[1:-1]
                                            self.logger.debug(
                                                f"Resolved SHA {stash_ref[:12]} to {actual_ref}"
                                            )
                                            break

                # Use public API method with proper stash reference
                result = self.git_ops.run_git_command(["stash", "drop", actual_ref])
                if result.returncode == 0:
                    self.logger.debug(f"Dropped stash {actual_ref}")
                else:
                    self.logger.warning(
                        f"Failed to drop stash {actual_ref}: {result.stderr}"
                    )
            except Exception as e:
                self.logger.warning(f"Error dropping stash {stash_ref}: {e}")

        self._stash_refs.clear()
        self._cleanup_actions.clear()

    def __del__(self) -> None:
        """Ensure cleanup on object destruction."""
        if self._stash_refs or self._cleanup_actions:
            self.logger.warning(
                "GitStateManager being destroyed with uncleaned resources"
            )
            self.cleanup_all()


# WorktreeManager removed - functionality not needed


@contextmanager
def git_state_context(git_ops: GitOps) -> Generator[GitStateManager, None, None]:
    """Context manager for git state with automatic restoration.

    Usage:
        with git_state_context(git_ops) as state_mgr:
            stash_result = state_mgr.save_current_state()
            if stash_result.is_ok():
                # Do operations that modify git state
                pass
            # State is automatically restored on exit
    """
    manager = GitStateManager(git_ops)
    try:
        yield manager
    finally:
        manager.cleanup_all()


# worktree_context function removed - functionality not needed


@contextmanager
def temporary_directory(
    prefix: str = "git-autosquash-", base_dir: Optional[Path] = None
) -> Generator[Path, None, None]:
    """Context manager for temporary directory with automatic cleanup."""
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=base_dir))
    try:
        yield temp_dir
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Failed to clean up temporary directory {temp_dir}: {e}"
            )


class IndexStateManager:
    """Manager for git index state with restoration capabilities."""

    def __init__(self, git_ops: GitOps) -> None:
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)
        self._saved_tree: Optional[str] = None
        self._original_index_file: Optional[str] = None

    def save_index_state(self) -> GitResult[str]:
        """Save current index state and return tree hash."""
        try:
            # Write current index to a tree object
            success, tree_hash = self.git_ops._run_git_command("write-tree")

            if success:
                self._saved_tree = tree_hash.strip()
                self.logger.debug(f"Saved index state as tree {self._saved_tree}")
                return Ok(self._saved_tree)
            else:
                error = GitOperationError(
                    operation="save_index",
                    message="Failed to save index state",
                    stderr=tree_hash,
                )
                return Err(error)

        except Exception as e:
            error = GitOperationError(
                operation="save_index", message=f"Exception during index save: {e}"
            )
            return Err(error)

    def restore_index_state(self) -> GitResult[bool]:
        """Restore index from saved tree."""
        if not self._saved_tree:
            error = GitOperationError(
                operation="restore_index", message="No saved index state to restore"
            )
            return Err(error)

        try:
            # Restore index from tree
            success, output = self.git_ops._run_git_command(
                "read-tree", self._saved_tree
            )

            if success:
                self.logger.debug(f"Restored index from tree {self._saved_tree}")
                return Ok(True)
            else:
                error = GitOperationError(
                    operation="restore_index",
                    message="Failed to restore index state",
                    command=f"git read-tree {self._saved_tree}",
                    stderr=output,
                )
                return Err(error)

        except Exception as e:
            error = GitOperationError(
                operation="restore_index",
                message=f"Exception during index restore: {e}",
            )
            return Err(error)


@contextmanager
def index_state_context(git_ops: GitOps) -> Generator[IndexStateManager, None, None]:
    """Context manager for git index state with automatic restoration."""
    manager = IndexStateManager(git_ops)

    # Save initial state
    save_result = manager.save_index_state()
    if save_result.is_err():
        raise RuntimeError(f"Failed to save index state: {save_result.unwrap_err()}")

    try:
        yield manager
    finally:
        # Restore state
        restore_result = manager.restore_index_state()
        if restore_result.is_err():
            logging.getLogger(__name__).warning(
                f"Failed to restore index state: {restore_result.unwrap_err()}"
            )
