"""Interactive rebase manager for applying hunk mappings to historical commits."""

import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Set

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk


class RebaseConflictError(Exception):
    """Raised when rebase encounters conflicts that need user resolution."""

    def __init__(self, message: str, conflicted_files: List[str]) -> None:
        """Initialize conflict error.

        Args:
            message: Error message
            conflicted_files: List of files with conflicts
        """
        super().__init__(message)
        self.conflicted_files = conflicted_files


class RebaseManager:
    """Manages interactive rebase operations for squashing hunks to commits."""

    def __init__(self, git_ops: GitOps, merge_base: str) -> None:
        """Initialize rebase manager.

        Args:
            git_ops: Git operations handler
            merge_base: Merge base commit hash
        """
        self.git_ops = git_ops
        self.merge_base = merge_base
        self._stash_ref: Optional[str] = None
        self._original_branch: Optional[str] = None

    def execute_squash(self, mappings: List[HunkTargetMapping]) -> bool:
        """Execute the squash operation for approved mappings.

        Args:
            mappings: List of approved hunk to commit mappings

        Returns:
            True if successful, False if user aborted

        Raises:
            RebaseConflictError: If conflicts occur during rebase
            subprocess.SubprocessError: If git operations fail
        """
        if not mappings:
            return True

        # Store original branch for cleanup
        self._original_branch = self.git_ops.get_current_branch()
        if not self._original_branch:
            raise ValueError("Cannot determine current branch")

        try:
            # Group hunks by target commit
            commit_hunks = self._group_hunks_by_commit(mappings)

            # Check working tree state and handle stashing if needed
            self._handle_working_tree_state()

            # Execute rebase for each target commit
            for target_commit in self._get_commit_order(set(commit_hunks.keys())):
                hunks = commit_hunks[target_commit]
                success = self._apply_hunks_to_commit(target_commit, hunks)
                if not success:
                    return False

            return True

        except Exception:
            # Cleanup on any error
            self._cleanup_on_error()
            raise

    def _group_hunks_by_commit(
        self, mappings: List[HunkTargetMapping]
    ) -> Dict[str, List[DiffHunk]]:
        """Group hunks by their target commit.

        Args:
            mappings: List of hunk to commit mappings

        Returns:
            Dictionary mapping commit hash to list of hunks
        """
        commit_hunks: Dict[str, List[DiffHunk]] = {}

        for mapping in mappings:
            if mapping.target_commit:
                commit_hash = mapping.target_commit
                if commit_hash not in commit_hunks:
                    commit_hunks[commit_hash] = []
                commit_hunks[commit_hash].append(mapping.hunk)

        return commit_hunks

    def _get_commit_order(self, commit_hashes: Set[str]) -> List[str]:
        """Get commits in chronological order (oldest first).

        Args:
            commit_hashes: Set of commit hashes to order

        Returns:
            List of commit hashes in chronological order
        """
        # Get commit timestamps for ordering
        commits_with_timestamps = []
        for commit_hash in commit_hashes:
            try:
                result = self.git_ops.run_git_command(
                    ["show", "-s", "--format=%ct", commit_hash]
                )
                if result.returncode == 0:
                    timestamp = int(result.stdout.strip())
                    commits_with_timestamps.append((float(timestamp), commit_hash))
            except (ValueError, subprocess.SubprocessError):
                # If we can't get timestamp, put it at the end
                commits_with_timestamps.append((float("inf"), commit_hash))

        # Sort by timestamp (oldest first)
        commits_with_timestamps.sort(key=lambda x: x[0])
        return [commit_hash for _, commit_hash in commits_with_timestamps]

    def _handle_working_tree_state(self) -> None:
        """Handle working tree state before rebase."""
        status = self.git_ops.get_working_tree_status()

        if not status["is_clean"]:
            # Stash any uncommitted changes
            result = self.git_ops.run_git_command(
                ["stash", "push", "-m", "git-autosquash temp stash"]
            )
            if result.returncode == 0:
                self._stash_ref = "stash@{0}"
            else:
                raise subprocess.SubprocessError(
                    f"Failed to stash changes: {result.stderr}"
                )

    def _apply_hunks_to_commit(self, target_commit: str, hunks: List[DiffHunk]) -> bool:
        """Apply hunks to a specific commit via interactive rebase.

        Args:
            target_commit: Target commit hash
            hunks: List of hunks to apply to this commit

        Returns:
            True if successful, False if user aborted
        """
        # Create patch for the hunks
        patch_content = self._create_patch_for_hunks(hunks)

        # Start interactive rebase to edit the target commit
        if not self._start_rebase_edit(target_commit):
            return False

        try:
            # Apply the patch
            self._apply_patch(patch_content)

            # Amend the commit
            self._amend_commit()

            # Continue the rebase
            self._continue_rebase()

            return True

        except RebaseConflictError:
            # Let the exception propagate for user handling
            raise
        except Exception as e:
            # Abort rebase on unexpected errors
            self._abort_rebase()
            raise subprocess.SubprocessError(f"Failed to apply patch: {e}")

    def _create_patch_for_hunks(self, hunks: List[DiffHunk]) -> str:
        """Create a patch string from a list of hunks.

        Args:
            hunks: List of hunks to include in patch

        Returns:
            Patch content as string
        """
        patch_lines = []
        current_file = None

        for hunk in hunks:
            # Add file header if this is a new file
            if hunk.file_path != current_file:
                current_file = hunk.file_path
                patch_lines.extend(
                    [f"--- a/{hunk.file_path}", f"+++ b/{hunk.file_path}"]
                )

            # Add hunk content
            patch_lines.extend(hunk.lines)

        return "\n".join(patch_lines) + "\n"

    def _start_rebase_edit(self, target_commit: str) -> bool:
        """Start interactive rebase to edit target commit.

        Args:
            target_commit: Commit to edit

        Returns:
            True if rebase started successfully
        """
        # Create rebase todo that marks target commit for editing
        todo_content = f"edit {target_commit}\n"

        # Write todo to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(todo_content)
            todo_file = f.name

        try:
            # Set git editor to use our todo file
            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = f"cp {todo_file}"

            # Start interactive rebase
            result = self.git_ops.run_git_command(
                ["rebase", "-i", f"{target_commit}^"], env=env
            )

            if result.returncode != 0:
                # Rebase failed to start
                return False

            return True

        finally:
            # Clean up temp file
            try:
                os.unlink(todo_file)
            except OSError:
                pass

    def _apply_patch(self, patch_content: str) -> None:
        """Apply patch content to working directory.

        Args:
            patch_content: Patch content to apply
        """
        # Write patch to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(patch_content)
            patch_file = f.name

        try:
            # Apply patch using git apply
            result = self.git_ops.run_git_command(
                ["apply", "--whitespace=nowarn", patch_file]
            )

            if result.returncode != 0:
                # Check if there are conflicts
                conflicted_files = self._get_conflicted_files()
                if conflicted_files:
                    raise RebaseConflictError(
                        f"Patch application failed with conflicts: {result.stderr}",
                        conflicted_files,
                    )
                else:
                    raise subprocess.SubprocessError(
                        f"Patch application failed: {result.stderr}"
                    )

        finally:
            # Clean up temp file
            try:
                os.unlink(patch_file)
            except OSError:
                pass

    def _amend_commit(self) -> None:
        """Amend the current commit with changes."""
        # Stage all changes
        result = self.git_ops.run_git_command(["add", "."])
        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Failed to stage changes: {result.stderr}"
            )

        # Amend commit (keep original message)
        result = self.git_ops.run_git_command(["commit", "--amend", "--no-edit"])
        if result.returncode != 0:
            raise subprocess.SubprocessError(f"Failed to amend commit: {result.stderr}")

    def _continue_rebase(self) -> None:
        """Continue the interactive rebase."""
        result = self.git_ops.run_git_command(["rebase", "--continue"])
        if result.returncode != 0:
            # Check for conflicts
            conflicted_files = self._get_conflicted_files()
            if conflicted_files:
                raise RebaseConflictError(
                    f"Rebase conflicts detected: {result.stderr}", conflicted_files
                )
            else:
                raise subprocess.SubprocessError(
                    f"Failed to continue rebase: {result.stderr}"
                )

    def _abort_rebase(self) -> None:
        """Abort the current rebase."""
        try:
            self.git_ops.run_git_command(["rebase", "--abort"])
        except subprocess.SubprocessError:
            # Ignore errors during abort
            pass

    def _get_conflicted_files(self) -> List[str]:
        """Get list of files with merge conflicts.

        Returns:
            List of file paths with conflicts
        """
        try:
            result = self.git_ops.run_git_command(
                ["diff", "--name-only", "--diff-filter=U"]
            )
            if result.returncode == 0:
                return [
                    line.strip() for line in result.stdout.split("\n") if line.strip()
                ]
        except subprocess.SubprocessError:
            pass

        return []

    def _cleanup_on_error(self) -> None:
        """Cleanup state after error."""
        # Abort any active rebase
        self._abort_rebase()

        # Restore stash if we created one
        if self._stash_ref:
            try:
                self.git_ops.run_git_command(["stash", "pop", self._stash_ref])
            except subprocess.SubprocessError:
                # Stash pop failed, but don't raise - user can manually recover
                pass
            finally:
                self._stash_ref = None

    def abort_operation(self) -> None:
        """Abort the current squash operation and restore original state."""
        self._cleanup_on_error()

    def is_rebase_in_progress(self) -> bool:
        """Check if a rebase is currently in progress.

        Returns:
            True if rebase is active
        """
        try:
            result = self.git_ops.run_git_command(["status", "--porcelain=v2"])
            if result.returncode == 0:
                # Look for rebase status indicators
                lines = result.stdout.split("\n")
                for line in lines:
                    if line.startswith("# rebase"):
                        return True
        except subprocess.SubprocessError:
            pass

        return False

    def get_rebase_status(self) -> Dict[str, Any]:
        """Get current rebase status information.

        Returns:
            Dictionary with rebase status details
        """
        status: Dict[str, Any] = {
            "in_progress": False,
            "current_commit": None,
            "conflicted_files": [],
            "step": None,
            "total_steps": None,
        }

        if not self.is_rebase_in_progress():
            return status

        status["in_progress"] = True
        status["conflicted_files"] = self._get_conflicted_files()

        # Try to get rebase step info
        try:
            rebase_dir = os.path.join(self.git_ops.repo_path, ".git", "rebase-merge")
            if os.path.exists(rebase_dir):
                # Read step info
                msgnum_file = os.path.join(rebase_dir, "msgnum")
                end_file = os.path.join(rebase_dir, "end")

                if os.path.exists(msgnum_file) and os.path.exists(end_file):
                    with open(msgnum_file, "r") as f:
                        status["step"] = int(f.read().strip())
                    with open(end_file, "r") as f:
                        status["total_steps"] = int(f.read().strip())
        except (OSError, ValueError):
            pass

        return status
