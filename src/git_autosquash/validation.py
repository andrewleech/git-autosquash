"""Validation framework for ensuring processing integrity."""

from typing import TYPE_CHECKING, List
import logging
from git_autosquash.git_ops import GitOps

if TYPE_CHECKING:
    from git_autosquash.hunk_parser import DiffHunk

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when processing validation fails.

    This indicates potential data corruption or loss during processing.
    The exception message includes detailed information about what
    went wrong and how to inspect the differences.
    """

    pass


class ProcessingValidator:
    """Validate that processing completed without data corruption.

    This class provides end-to-end validation by comparing the starting
    commit with the final result. If `git diff <start> HEAD` shows any
    differences, data corruption occurred during processing.

    The validator provides two types of validation:
    1. Pre-flight: validate_hunk_count() checks hunk counts match
    2. Post-flight: validate_processing() checks no corruption occurred

    Note: This validator works correctly in detached HEAD state, which is
    common during rebase operations.

    Attributes:
        git_ops: GitOps instance for git command execution
        logger: Logger instance for validation messages
    """

    def __init__(self, git_ops: GitOps):
        """Initialize the processing validator.

        Args:
            git_ops: GitOps instance for git command execution
        """
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)

    def validate_processing(
        self, starting_commit: str, description: str = "processing"
    ) -> bool:
        """Validate that current HEAD has same changes as starting commit.

        This is the primary validation method. It compares the starting
        commit (before processing) with current HEAD (after processing).
        If any differences exist, data corruption occurred.

        The validation works by running:
            git diff --exit-code <starting_commit> HEAD

        Exit code 0 means no differences (success).
        Exit code 1 means differences found (corruption).
        Other exit codes indicate git command failure.

        Note: Binary files will show "Binary files differ" in output but
        validation will still detect the difference correctly.

        Args:
            starting_commit: The commit hash we started with
            description: Description for error messages (e.g., "squash operation")

        Returns:
            True if validation passes (no differences)

        Raises:
            ValidationError: If differences detected (data corruption) or
                           if git command fails
        """
        self.logger.info(f"Validating {description}...")

        # Get current HEAD
        current_head = self._get_head_hash()

        self.logger.debug(f"Comparing {starting_commit[:8]} -> {current_head[:8]}")

        # Compare starting commit with current HEAD
        result = self.git_ops.run_git_command(
            [
                "diff",
                "--exit-code",  # Exit with 1 if differences found
                starting_commit,
                current_head,
            ]
        )

        if result.returncode == 0:
            # No differences - validation passed
            self.logger.info(f"[+] Validation passed: {description}")
            return True

        elif result.returncode == 1:
            # Differences found - this is data corruption
            # Truncate at line boundaries for cleaner output
            diff_lines = result.stdout.split("\n")
            if len(diff_lines) > 30:
                diff_output = "\n".join(diff_lines[:30]) + "\n... (truncated)"
            else:
                diff_output = result.stdout

            raise ValidationError(
                f"Data corruption detected during {description}!\n"
                f"Starting commit: {starting_commit}\n"
                f"Current HEAD:    {current_head}\n"
                f"\nDifferences found:\n{diff_output}\n\n"
                f"This indicates that processing did not preserve all changes.\n"
                f"\nRecovery options:\n"
                f"  1. Inspect differences: git diff {starting_commit[:8]} {current_head[:8]}\n"
                f"  2. Abort changes: git reset --hard {starting_commit[:8]}\n"
                f"  3. Keep current state if changes appear correct\n"
            )

        else:
            # Git command failed
            raise ValidationError(
                f"Validation failed to run (exit code {result.returncode}): {result.stderr}\n"
                f"Git command: git diff --exit-code {starting_commit[:8]} {current_head[:8]}"
            )

    def validate_hunk_count(
        self, starting_commit: str, processed_hunks: List["DiffHunk"]
    ) -> bool:
        """Validate that hunk counts match between commit and processed list.

        This is a pre-flight validation to ensure we're not missing any hunks
        before we start processing. It compares the number of hunks in the
        starting commit with the number of hunks we plan to process.

        Note: This only validates counts, not hunk content. Hunks could be
        reordered or different hunks could be present, and this check would
        still pass. For full validation, use validate_processing() after
        processing completes.

        Args:
            starting_commit: The commit to validate against
            processed_hunks: The hunks we plan to process

        Returns:
            True if validation passes (counts match)

        Raises:
            ValidationError: If hunk counts don't match or if unable to
                           get hunks from starting commit
        """
        self.logger.debug("Validating hunk count...")

        # Get diff from starting commit
        result = self.git_ops.run_git_command(["show", "--format=", starting_commit])

        if result.returncode != 0:
            raise ValidationError(
                f"Failed to get diff from {starting_commit}: {result.stderr}"
            )

        # Count hunks in original commit by counting hunk header lines
        # Hunk headers start with @@ (not just contain @@ )
        # This avoids coupling to HunkParser's internal implementation
        original_count = sum(
            1 for line in result.stdout.split("\n") if line.startswith("@@")
        )

        # Get count of hunks to be processed
        processed_count = len(processed_hunks)

        if original_count != processed_count:
            raise ValidationError(
                f"Hunk count mismatch: {original_count} hunks in commit, "
                f"{processed_count} hunks to process. "
                f"This indicates hunks were lost during parsing."
            )

        self.logger.debug(f"[+] Hunk count validated: {processed_count} hunks")
        return True

    def _get_head_hash(self) -> str:
        """Get current HEAD commit hash.

        Returns:
            Full SHA of HEAD

        Raises:
            ValidationError: If HEAD cannot be resolved
        """
        result = self.git_ops.run_git_command(["rev-parse", "HEAD"])

        if result.returncode != 0:
            raise ValidationError(f"Failed to get HEAD hash: {result.stderr}")

        return result.stdout.strip()
