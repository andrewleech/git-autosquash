"""Split source commits into per-hunk commits for reliable 3-way merge.

This module provides functionality to split a source commit into multiple
temporary commits, one per hunk. This enables git's 3-way merge machinery
to work reliably when cherry-picking hunks to target commits.

Instead of extracting hunks as text patches (which breaks 3-way merge),
we create real git commits that git can use for proper conflict resolution.
"""

import logging
import subprocess
from typing import List, Optional

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser, DiffHunk


logger = logging.getLogger(__name__)


class HunkCommitSplitter:
    """Split source commits into per-hunk commits for reliable cherry-picking.

    This creates temporary commits on a separate branch, one commit per hunk,
    enabling git's 3-way merge to work properly during cherry-pick operations.
    """

    def __init__(self, git_ops: GitOps):
        """Initialize the hunk commit splitter.

        Args:
            git_ops: GitOps instance for git command execution
        """
        self.git_ops = git_ops
        self.temp_branch: Optional[str] = None
        self.split_commits: List[str] = []
        self.original_branch: Optional[str] = None

    def split_commit_into_hunks(
        self, source_commit: str
    ) -> tuple[List[str], List[DiffHunk]]:
        """Split a source commit into separate commits, one per hunk.

        Creates a temporary branch and commits each hunk individually,
        preserving the original commit message with a marker indicating
        which hunk this is.

        Args:
            source_commit: The commit SHA to split

        Returns:
            Tuple of (list of split commit SHAs, list of corresponding hunks)

        Raises:
            subprocess.SubprocessError: If git operations fail
        """
        logger.info(f"Splitting commit {source_commit[:8]} into per-hunk commits")

        # Store original branch for restoration
        self.original_branch = self.git_ops.get_current_branch()

        # Get hunks from source commit
        parser = HunkParser(self.git_ops)
        hunks = parser.get_diff_hunks(line_by_line=False, from_commit=source_commit)

        if not hunks:
            logger.warning("No hunks found in source commit")
            return [], []

        logger.info(f"Found {len(hunks)} hunks to split")

        # Create temporary branch at source~1 (parent of source commit)
        self.temp_branch = f"git-autosquash-split-{source_commit[:8]}"

        # Clean up stale branch if it exists
        self.git_ops.run_git_command(["branch", "-D", self.temp_branch])

        parent_result = self.git_ops.run_git_command(
            ["rev-parse", f"{source_commit}~1"]
        )
        if parent_result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Failed to get parent of {source_commit}: {parent_result.stderr}"
            )
        parent_sha = parent_result.stdout.strip()

        # Create and switch to temp branch
        result = self.git_ops.run_git_command(
            ["checkout", "-b", self.temp_branch, parent_sha]
        )
        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Failed to create temp branch: {result.stderr}"
            )

        try:
            # Get original commit message
            msg_result = self.git_ops.run_git_command(
                ["log", "-1", "--format=%B", source_commit]
            )
            original_message = (
                msg_result.stdout.strip()
                if msg_result.returncode == 0
                else "Split commit"
            )

            # Create one commit per hunk
            split_commits = []
            for i, hunk in enumerate(hunks, 1):
                logger.debug(f"Creating commit {i}/{len(hunks)} for {hunk.file_path}")

                # Apply this hunk only
                patch_content = self._create_patch_for_hunk(hunk)
                commit_sha = self._apply_and_commit_hunk(
                    patch_content, original_message, i, len(hunks)
                )
                split_commits.append(commit_sha)

            self.split_commits = split_commits
            logger.info(
                f"Created {len(split_commits)} split commits on {self.temp_branch}"
            )

            return split_commits, hunks

        finally:
            # Switch back to original branch
            if self.original_branch:
                result = self.git_ops.run_git_command(
                    ["checkout", self.original_branch]
                )
                if result.returncode != 0:
                    logger.error(
                        f"Failed to return to original branch: {result.stderr}"
                    )

    def _create_patch_for_hunk(self, hunk: DiffHunk) -> str:
        """Create a patch file content for a single hunk.

        Args:
            hunk: The hunk to create a patch for

        Returns:
            Patch content string in proper git diff format
        """
        lines = [
            f"diff --git a/{hunk.file_path} b/{hunk.file_path}",
            f"--- a/{hunk.file_path}",
            f"+++ b/{hunk.file_path}",
        ]
        lines.extend(hunk.lines)
        return "\n".join(lines) + "\n"

    def _apply_and_commit_hunk(
        self, patch_content: str, original_message: str, hunk_num: int, total_hunks: int
    ) -> str:
        """Apply a hunk patch and commit it.

        Args:
            patch_content: The patch to apply
            original_message: Original commit message
            hunk_num: Current hunk number (1-indexed)
            total_hunks: Total number of hunks

        Returns:
            SHA of created commit

        Raises:
            subprocess.SubprocessError: If patch application or commit fails
        """
        import tempfile
        import os

        # Write patch to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".patch") as f:
            f.write(patch_content)
            patch_file = f.name

        try:
            # Apply patch
            result = self.git_ops.run_git_command(["apply", "--index", patch_file])
            if result.returncode != 0:
                raise subprocess.SubprocessError(
                    f"Failed to apply hunk {hunk_num}: {result.stderr}"
                )

            # Create commit message
            commit_message = (
                f"{original_message}\n\n"
                f"[git-autosquash: split {hunk_num}/{total_hunks}]"
            )

            # Write message to temp file
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".txt"
            ) as f:
                f.write(commit_message)
                msg_file = f.name

            try:
                # Commit
                result = self.git_ops.run_git_command(["commit", "-F", msg_file])
                if result.returncode != 0:
                    raise subprocess.SubprocessError(
                        f"Failed to commit hunk {hunk_num}: {result.stderr}"
                    )

                # Get commit SHA
                sha_result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
                if sha_result.returncode != 0:
                    raise subprocess.SubprocessError(
                        f"Failed to get commit SHA: {sha_result.stderr}"
                    )

                return sha_result.stdout.strip()

            finally:
                try:
                    os.unlink(msg_file)
                except OSError:
                    pass

        finally:
            try:
                os.unlink(patch_file)
            except OSError:
                pass

    def cleanup(self) -> None:
        """Clean up temporary branch and split commits.

        This should be called after successful processing to remove
        the temporary commits and branch.
        """
        if not self.temp_branch:
            return

        logger.info(f"Cleaning up split commits on {self.temp_branch}")

        # First, ensure we're not on the temp branch (can't delete current branch)
        if self.original_branch:
            current_branch = self.git_ops.get_current_branch()
            if current_branch == self.temp_branch:
                logger.debug(f"Switching from temp branch to {self.original_branch}")
                result = self.git_ops.run_git_command(
                    ["checkout", self.original_branch]
                )
                if result.returncode != 0:
                    logger.warning(
                        f"Failed to switch back to {self.original_branch}: {result.stderr}"
                    )
                    # Continue anyway, might still be able to delete

        # Delete the temporary branch
        result = self.git_ops.run_git_command(["branch", "-D", self.temp_branch])
        if result.returncode != 0:
            logger.warning(
                f"Failed to delete temp branch {self.temp_branch}: {result.stderr}"
            )
            logger.info(
                f"You can manually delete it with: git branch -D {self.temp_branch}"
            )
        else:
            logger.info(f"Deleted temporary branch {self.temp_branch}")

        self.temp_branch = None
        self.split_commits = []
