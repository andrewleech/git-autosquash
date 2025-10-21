"""Squash context abstraction for git-autosquash operations.

This module provides an immutable context object that replaces the semantic
overloading of blame_ref and the instance variable management of _source_commit.

The SquashContext centralizes all the logic for determining:
- Whether HEAD should be excluded from blame/fallback
- Whether we're processing a historical commit vs working tree changes
- What blame reference to use for git operations
"""

import re
from dataclasses import dataclass
from typing import Optional

from git_autosquash.git_ops import GitOps


@dataclass(frozen=True)
class SquashContext:
    """Immutable context for squash operations.

    Attributes:
        blame_ref: Git reference to use for blame operations (e.g., "HEAD", "abc123~1")
        source_commit: Optional commit SHA when using --source <commit>
        is_historical_commit: True if processing a historical commit (not working tree)
        working_tree_clean: True if working tree has no changes
    """

    blame_ref: str
    source_commit: Optional[str]
    is_historical_commit: bool
    working_tree_clean: bool

    @classmethod
    def from_source(cls, source: str, git_ops: GitOps) -> "SquashContext":
        """Create SquashContext from --source CLI argument.

        This factory method replaces the logic in main.py lines 696-709.

        Args:
            source: The value of --source argument (e.g., "HEAD", "auto", "abc123")
            git_ops: GitOps instance for checking working tree status

        Returns:
            Configured SquashContext instance

        Examples:
            - source="HEAD" → blame_ref="HEAD~1", source_commit=None
            - source="abc123" → blame_ref="abc123~1", source_commit="abc123"
            - source="auto" → blame_ref="HEAD", source_commit=None
        """
        # Normalize source to lowercase for comparison
        source_lower = source.lower()

        # Get working tree status first - needed to determine what we're processing
        status = git_ops.get_working_tree_status()
        working_tree_clean = status["is_clean"]

        # Determine blame_ref and source_commit based on source
        if source_lower in ["head"]:
            # Processing HEAD commit, not a specific commit SHA
            blame_ref = "HEAD~1"
            source_commit_value = None
            is_historical = False
        elif source_lower in ["auto", "working-tree", "index"]:
            # For "auto": if working tree is clean, process HEAD commit (use HEAD~1)
            # Otherwise process working tree changes (use HEAD)
            if source_lower == "auto" and working_tree_clean:
                # Working tree clean - process HEAD commit
                blame_ref = "HEAD~1"
            else:
                # Process working tree or index changes
                blame_ref = "HEAD"
            source_commit_value = None
            is_historical = False
        else:
            # Assume it's a commit SHA - processing historical commit
            blame_ref = f"{source}~1"
            source_commit_value = source
            is_historical = True

        return cls(
            blame_ref=blame_ref,
            source_commit=source_commit_value,
            is_historical_commit=is_historical,
            working_tree_clean=working_tree_clean,
        )

    @property
    def normalized_blame_ref(self) -> str:
        """Normalize blame_ref for case-insensitive comparison.

        Returns:
            Uppercase version of blame_ref for consistent comparison
        """
        return self.blame_ref.upper()

    @property
    def is_processing_head_commit(self) -> bool:
        """Check if we're processing the HEAD commit itself (not working tree).

        This is a semantic check that replaces the brittle string comparison
        `blame_ref == "HEAD"` and properly considers working tree state.

        Returns:
            True if processing HEAD commit with clean working tree
        """
        return self.normalized_blame_ref == "HEAD" and self.working_tree_clean

    def should_exclude_head_from_blame(self) -> bool:
        """Determine if HEAD should be excluded from blame analysis.

        This centralizes the HEAD exclusion logic that was previously split
        across HunkTargetResolver._should_exclude_head_from_blame_analysis().

        HEAD should be excluded from blame analysis when:
        - Processing the HEAD commit itself (blame_ref="HEAD")
        - AND working tree is clean (not processing working tree changes)

        When processing historical commits (blame_ref != "HEAD"), HEAD is a
        valid target and should NOT be excluded.

        Returns:
            True if HEAD should be excluded from blame candidates
        """
        # Only exclude HEAD when processing HEAD itself, not historical commits
        if self.blame_ref != "HEAD":
            return False

        # Exclude HEAD only when working tree is clean
        return self.working_tree_clean

    def should_exclude_head_from_fallback(self) -> bool:
        """Determine if HEAD should be excluded from fallback candidates.

        This centralizes the HEAD exclusion logic that was previously in
        FallbackTargetProvider._should_exclude_head_as_target().

        Uses the same logic as blame exclusion for consistency.

        Returns:
            True if HEAD should be excluded from fallback candidates
        """
        # Use same logic as blame exclusion for consistency
        return self.should_exclude_head_from_blame()

    def validate_source_commit(self, git_ops: GitOps) -> list[str]:
        """Validate source_commit if present.

        Performs validation checks on the source commit:
        - Valid SHA format (basic check)
        - Commit exists in repository
        - Commit is in current branch

        Args:
            git_ops: GitOps instance for git operations

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        if not self.source_commit:
            return errors

        # Basic SHA format check (partial or full SHA-1/SHA-256)
        # Git accepts abbreviated SHAs (minimum 4 chars for most repos)
        if not re.match(r"^[a-f0-9]{4,64}$", self.source_commit.lower()):
            errors.append(
                f"Invalid commit format '{self.source_commit}'. "
                "Expected hexadecimal SHA (4-64 characters)"
            )
            return errors  # Early return if format is invalid

        # Check if commit exists
        result = git_ops.run_git_command(["cat-file", "-t", self.source_commit])
        if result.returncode != 0:
            errors.append(f"Commit '{self.source_commit}' does not exist in repository")
            return errors

        # Verify it's a commit object (not a tree or blob)
        if result.stdout.strip() != "commit":
            errors.append(
                f"'{self.source_commit}' is not a commit (type: {result.stdout.strip()})"
            )
            return errors

        # Check if commit is an ancestor of HEAD (i.e., in current branch history)
        ancestor_result = git_ops.run_git_command(
            ["merge-base", "--is-ancestor", self.source_commit, "HEAD"]
        )
        if ancestor_result.returncode != 0:
            errors.append(
                f"Commit '{self.source_commit}' is not in current branch history. "
                "Only commits reachable from HEAD can be used as source."
            )

        # Check if source commit is HEAD itself (usually not what user wants)
        head_result = git_ops.run_git_command(["rev-parse", "HEAD"])
        if head_result.returncode == 0:
            head_sha = head_result.stdout.strip()
            # Resolve source_commit to full SHA for comparison
            source_sha_result = git_ops.run_git_command(
                ["rev-parse", self.source_commit]
            )
            if source_sha_result.returncode == 0:
                source_full_sha = source_sha_result.stdout.strip()
                if source_full_sha == head_sha:
                    errors.append(
                        "Source commit is HEAD. Use '--source HEAD' explicitly if intended, "
                        "or omit --source to process working tree changes."
                    )

        return errors

    def validate_blame_ref(self, git_ops: GitOps) -> list[str]:
        """Validate blame_ref is a valid git reference.

        Args:
            git_ops: GitOps instance for git operations

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        if not self.blame_ref:
            errors.append("blame_ref cannot be empty")
            return errors

        # Check if blame_ref is a valid git reference
        result = git_ops.run_git_command(["rev-parse", "--verify", self.blame_ref])
        if result.returncode != 0:
            errors.append(
                f"Invalid blame reference '{self.blame_ref}'. "
                f"Must be a valid git reference (commit SHA, branch, tag, or HEAD~N)"
            )

        return errors

    def validate(self, git_ops: GitOps) -> list[str]:
        """Validate all context fields.

        Args:
            git_ops: GitOps instance for git operations

        Returns:
            List of all validation error messages (empty if valid)
        """
        errors: list[str] = []
        errors.extend(self.validate_blame_ref(git_ops))
        errors.extend(self.validate_source_commit(git_ops))
        return errors
