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

    def save_current_state(self) -> GitResult[str]:
        """Save the current git state and return a stash reference."""
        try:
            # Get current branch
            success, branch = self.git_ops._run_git_command("branch", "--show-current")
            if success:
                self._original_branch = branch.strip()

            # Create stash with untracked files
            success, output = self.git_ops._run_git_command(
                "stash",
                "push",
                "--include-untracked",
                "--message",
                "git-autosquash temporary state",
            )

            if success:
                # Extract stash reference from output
                stash_ref = "stash@{0}"  # Latest stash
                self._stash_refs.append(stash_ref)
                self.logger.debug(f"Saved git state to {stash_ref}")
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

    def restore_state(self, stash_ref: str) -> GitResult[bool]:
        """Restore git state from a stash reference."""
        try:
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
                success, _ = self.git_ops._run_git_command("stash", "drop", stash_ref)
                if success:
                    self.logger.debug(f"Dropped stash {stash_ref}")
                else:
                    self.logger.warning(f"Failed to drop stash {stash_ref}")
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


class WorktreeManager:
    """Manager for git worktree lifecycle with guaranteed cleanup."""

    def __init__(self, git_ops: GitOps, base_path: Optional[Path] = None) -> None:
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)
        self.base_path = base_path or Path(tempfile.gettempdir())
        self._worktrees: List[Path] = []

    def create_worktree(self, branch: str = "HEAD") -> GitResult[Path]:
        """Create a temporary worktree."""
        try:
            # Create temporary directory
            temp_dir = Path(
                tempfile.mkdtemp(prefix="git-autosquash-worktree-", dir=self.base_path)
            )

            # Create worktree
            success, output = self.git_ops._run_git_command(
                "worktree", "add", str(temp_dir), branch
            )

            if success:
                self._worktrees.append(temp_dir)
                self.logger.debug(f"Created worktree at {temp_dir}")
                return Ok(temp_dir)
            else:
                # Clean up temp directory if worktree creation failed
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

                error = GitOperationError(
                    operation="create_worktree",
                    message="Failed to create worktree",
                    command=f"git worktree add {temp_dir} {branch}",
                    stderr=output,
                )
                return Err(error)

        except Exception as e:
            error = GitOperationError(
                operation="create_worktree",
                message=f"Exception during worktree creation: {e}",
            )
            return Err(error)

    def remove_worktree(self, worktree_path: Path) -> GitResult[bool]:
        """Remove a worktree and clean up its directory."""
        try:
            # Remove from git
            success, output = self.git_ops._run_git_command(
                "worktree", "remove", str(worktree_path), "--force"
            )

            if success:
                # Remove from tracking
                if worktree_path in self._worktrees:
                    self._worktrees.remove(worktree_path)

                # Ensure directory is gone
                if worktree_path.exists():
                    shutil.rmtree(worktree_path)

                self.logger.debug(f"Removed worktree {worktree_path}")
                return Ok(True)
            else:
                # Try manual cleanup even if git command failed
                if worktree_path.exists():
                    try:
                        shutil.rmtree(worktree_path)
                    except Exception as cleanup_error:
                        self.logger.warning(
                            f"Manual cleanup failed for {worktree_path}: {cleanup_error}"
                        )

                error = GitOperationError(
                    operation="remove_worktree",
                    message="Failed to remove worktree",
                    command=f"git worktree remove {worktree_path} --force",
                    stderr=output,
                )
                return Err(error)

        except Exception as e:
            error = GitOperationError(
                operation="remove_worktree",
                message=f"Exception during worktree removal: {e}",
            )
            return Err(error)

    def cleanup_all(self) -> None:
        """Clean up all managed worktrees."""
        for worktree_path in list(self._worktrees):
            result = self.remove_worktree(worktree_path)
            if result.is_err():
                self.logger.warning(
                    f"Failed to clean up worktree: {result.unwrap_err()}"
                )

        self._worktrees.clear()

    def __del__(self) -> None:
        """Ensure cleanup on object destruction."""
        if self._worktrees:
            self.logger.warning(
                "WorktreeManager being destroyed with uncleaned worktrees"
            )
            self.cleanup_all()


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


@contextmanager
def worktree_context(
    git_ops: GitOps, branch: str = "HEAD"
) -> Generator[Path, None, None]:
    """Context manager for temporary worktree with automatic cleanup.

    Usage:
        with worktree_context(git_ops) as worktree_path:
            # Work with the temporary worktree
            pass
        # Worktree is automatically cleaned up
    """
    manager = WorktreeManager(git_ops)
    try:
        result = manager.create_worktree(branch)
        if result.is_err():
            raise RuntimeError(f"Failed to create worktree: {result.unwrap_err()}")

        worktree_path = result.unwrap()
        yield worktree_path
    finally:
        manager.cleanup_all()


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
