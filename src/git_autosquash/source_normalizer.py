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
        self.parent_commit: Optional[str] = None  # Store parent for safe cleanup

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
                # temp_commit_created set by method

            elif source_lower == "index":
                commit_hash = self._commit_index()
                # temp_commit_created set by method

            elif source_lower == "head":
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
            raise SourceNormalizationError(f"Failed to stage changes: {result.stderr}")

        # Check if there are actually changes to commit
        result = self.git_ops.run_git_command(["diff", "--cached", "--quiet"])
        if result.returncode == 0:
            # No changes staged - unstage and use HEAD instead
            self.logger.debug("No changes to commit, restoring index and using HEAD")
            # Reset index to HEAD to unstage the files
            self.git_ops.run_git_command(["reset", "HEAD"])
            self.temp_commit_created = False
            return self._get_head_hash()

        # Store parent commit before creating temp commit
        self.parent_commit = self._get_head_hash()

        # Create temporary commit (skip hooks with --no-verify)
        result = self.git_ops.run_git_command(
            [
                "commit",
                "--no-verify",
                "-m",
                "TEMP: git-autosquash working tree snapshot",
            ]
        )

        if result.returncode != 0:
            # Reset index on failure
            self.git_ops.run_git_command(["reset", "HEAD"])
            raise SourceNormalizationError(
                f"Failed to create temp commit: {result.stderr}"
            )

        self.temp_commit_created = True
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
            self.temp_commit_created = False
            return self._get_head_hash()

        # Store parent commit before creating temp commit
        self.parent_commit = self._get_head_hash()

        # Create temporary commit (skip hooks with --no-verify)
        result = self.git_ops.run_git_command(
            ["commit", "--no-verify", "-m", "TEMP: git-autosquash index snapshot"]
        )

        if result.returncode != 0:
            raise SourceNormalizationError(
                f"Failed to create temp commit: {result.stderr}"
            )

        self.temp_commit_created = True
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
            raise SourceNormalizationError(f"Invalid commit reference: {commit_ref}")

        commit_sha = result.stdout.strip()

        # Verify commit exists
        result = self.git_ops.run_git_command(["cat-file", "-t", commit_sha])
        if result.returncode != 0 or result.stdout.strip() != "commit":
            raise SourceNormalizationError(f"Not a valid commit: {commit_ref}")

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
            raise SourceNormalizationError(f"Failed to get HEAD hash: {result.stderr}")

        return result.stdout.strip()

    def cleanup_temp_commit(self) -> None:
        """Remove temporary commit if we created one.

        Uses soft reset to remove the commit while preserving changes
        in the index/working tree.
        """
        if not self.temp_commit_created:
            return

        # Use stored parent commit if available, otherwise fall back to ~1
        if self.parent_commit:
            target_commit = self.parent_commit
            self.logger.info(f"Cleaning up temporary commit to {target_commit[:8]}")
        elif self.starting_commit:
            target_commit = f"{self.starting_commit}~1"
            self.logger.warning(
                "No parent commit stored, using ~1 notation (less safe)"
            )
        else:
            self.logger.warning("No commit information available for cleanup")
            return

        # Soft reset to parent (preserves changes)
        result = self.git_ops.run_git_command(["reset", "--soft", target_commit])

        if result.returncode == 0:
            self.logger.debug("✓ Temporary commit removed")
            self.temp_commit_created = False
            self.parent_commit = None
        else:
            self.logger.warning(f"Failed to cleanup temp commit: {result.stderr}")
