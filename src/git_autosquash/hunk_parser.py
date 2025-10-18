"""Diff parsing and hunk splitting module."""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from git_autosquash.git_ops import GitOps

logger = logging.getLogger(__name__)


@dataclass
class DiffHunk:
    """Represents a single diff hunk with metadata."""

    file_path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[str]
    context_before: List[str]
    context_after: List[str]

    @property
    def affected_lines(self) -> range:
        """Get the range of lines affected in the new file."""
        return range(self.new_start, self.new_start + self.new_count)

    @property
    def has_additions(self) -> bool:
        """Check if hunk contains added lines."""
        return any(
            line.startswith("+") and not line.startswith("+++") for line in self.lines
        )

    @property
    def has_deletions(self) -> bool:
        """Check if hunk contains deleted lines."""
        return any(
            line.startswith("-") and not line.startswith("---") for line in self.lines
        )


class HunkParser:
    """Parses git diff output into structured hunks."""

    def __init__(self, git_ops: GitOps) -> None:
        """Initialize HunkParser with GitOps instance.

        Args:
            git_ops: GitOps instance for running git commands
        """
        self.git_ops = git_ops

    def get_diff_hunks(
        self,
        line_by_line: bool = False,
        from_commit: Optional[str] = None,
        source: str = "auto",
    ) -> List[DiffHunk]:
        """Extract hunks from a commit or working tree.

        Recommended usage: Use from_commit with SourceNormalizer for consistent
        parsing from normalized commits. The source parameter is maintained for
        backward compatibility.

        Args:
            line_by_line: If True, split hunks line-by-line for finer granularity
            from_commit: Commit hash to parse (recommended path, use with SourceNormalizer)
            source: DEPRECATED - What to process. Use from_commit instead.
                   Values: 'auto' (detect based on tree status), 'working-tree',
                   'index', 'head', or a commit SHA

        Returns:
            List of DiffHunk objects representing changes
        """
        if from_commit:
            # New path: parse from normalized commit
            if source != "auto":
                logger.debug(
                    f"Ignoring 'source={source}' parameter because from_commit is provided"
                )

            success, diff_output = self.git_ops._run_git_command(
                "show", "--format=", from_commit
            )
            if not success:
                logger.warning(
                    f"Failed to get diff from commit {from_commit}: git command failed"
                )
                return []
            hunks = self._parse_diff_output(diff_output)
        else:
            # Legacy path: maintain backward compatibility
            # Note: Always emit warning since source parameter is deprecated
            logger.debug(
                "Using deprecated source-based parsing. "
                "Consider using SourceNormalizer with from_commit parameter."
            )
            hunks = self._get_hunks_from_source(source)

        if line_by_line:
            hunks = self._split_hunks_line_by_line(hunks)

        return hunks

    def _get_hunks_from_source(self, source: str) -> List[DiffHunk]:
        """Get hunks from legacy source specification (backward compatibility).

        Args:
            source: Source specification ('auto', 'working-tree', 'index', 'head', or commit SHA)

        Returns:
            List of DiffHunk objects
        """
        if source == "auto":
            # Auto-detect based on working tree status
            status = self.git_ops.get_working_tree_status()

            if status["is_clean"]:
                # Working tree is clean, diff HEAD~1 to get previous commit changes
                success, diff_output = self.git_ops._run_git_command(
                    "show", "--format=", "HEAD"
                )
            elif status["has_staged"] and not status["has_unstaged"]:
                # Only staged changes, diff them
                success, diff_output = self.git_ops._run_git_command("diff", "--cached")
            elif not status["has_staged"] and status["has_unstaged"]:
                # Only unstaged changes, diff them
                success, diff_output = self.git_ops._run_git_command("diff")
            else:
                # Both staged and unstaged changes - process only staged changes
                # Unstaged changes will be temporarily stashed by the rebase manager
                success, diff_output = self.git_ops._run_git_command("diff", "--cached")
        elif source == "working-tree":
            # Explicitly diff working tree (unstaged changes)
            success, diff_output = self.git_ops._run_git_command("diff")
        elif source == "index":
            # Explicitly diff staged changes
            success, diff_output = self.git_ops._run_git_command("diff", "--cached")
        elif source == "head" or source == "HEAD":
            # Diff HEAD commit
            success, diff_output = self.git_ops._run_git_command(
                "show", "--format=", "HEAD"
            )
        else:
            # Assume it's a commit SHA
            success, diff_output = self.git_ops._run_git_command(
                "show", "--format=", source
            )

        if not success:
            return []

        return self._parse_diff_output(diff_output)

    def _parse_diff_output(self, diff_output: str) -> List[DiffHunk]:
        """Parse git diff output into DiffHunk objects.

        Args:
            diff_output: Raw git diff output

        Returns:
            List of parsed DiffHunk objects
        """
        if not diff_output.strip():
            return []

        hunks = []
        lines = diff_output.split("\n")
        current_file = None
        i = 0

        while i < len(lines):
            line = lines[i]

            # Track current file being processed
            if line.startswith("diff --git"):
                # Extract file path from "diff --git a/path b/path"
                match = re.match(r"diff --git a/(.*) b/(.*)", line)
                if match:
                    current_file = match.group(2)  # Use the new file path

            elif line.startswith("@@") and current_file:
                # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
                hunk_match = re.match(
                    r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line
                )
                if hunk_match:
                    old_start = int(hunk_match.group(1))
                    old_count = int(hunk_match.group(2) or 1)
                    new_start = int(hunk_match.group(3))
                    new_count = int(hunk_match.group(4) or 1)

                    # Collect hunk lines
                    hunk_lines = [line]  # Include the @@ line
                    i += 1

                    while (
                        i < len(lines)
                        and not lines[i].startswith("@@")
                        and not lines[i].startswith("diff --git")
                    ):
                        hunk_lines.append(
                            lines[i]
                        )  # Preserve all lines including empty ones
                        i += 1

                    # Create DiffHunk object
                    hunk = DiffHunk(
                        file_path=current_file,
                        old_start=old_start,
                        old_count=old_count,
                        new_start=new_start,
                        new_count=new_count,
                        lines=hunk_lines,
                        context_before=[],
                        context_after=[],
                    )

                    hunks.append(hunk)
                    continue  # Don't increment i, it was already incremented in the loop

            i += 1

        return hunks

    def _split_hunks_line_by_line(self, hunks: List[DiffHunk]) -> List[DiffHunk]:
        """Split hunks into line-by-line changes for finer granularity.

        Args:
            hunks: List of original hunks to split

        Returns:
            List of line-by-line split hunks
        """
        split_hunks = []

        for hunk in hunks:
            # If hunk is already small (single line change), keep as-is
            change_lines = [
                line for line in hunk.lines[1:] if line.startswith(("+", "-"))
            ]
            if len(change_lines) <= 1:
                split_hunks.append(hunk)
                continue

            # Split into individual line changes
            current_old_line = hunk.old_start
            current_new_line = hunk.new_start

            i = 1  # Skip the @@ header line
            while i < len(hunk.lines):
                line = hunk.lines[i]

                if line.startswith("+"):
                    # Addition: create a single-line hunk with proper line counts
                    header = f"@@ -{current_old_line},0 +{current_new_line},1 @@"
                    new_hunk = DiffHunk(
                        file_path=hunk.file_path,
                        old_start=current_old_line,
                        old_count=0,
                        new_start=current_new_line,
                        new_count=1,
                        lines=[header, line],
                        context_before=[],
                        context_after=[],
                    )
                    split_hunks.append(new_hunk)
                    current_new_line += 1

                elif line.startswith("-"):
                    # Deletion: create a single-line hunk with proper line counts
                    header = f"@@ -{current_old_line},1 +{current_new_line},0 @@"
                    new_hunk = DiffHunk(
                        file_path=hunk.file_path,
                        old_start=current_old_line,
                        old_count=1,
                        new_start=current_new_line,
                        new_count=0,
                        lines=[header, line],
                        context_before=[],
                        context_after=[],
                    )
                    split_hunks.append(new_hunk)
                    current_old_line += 1

                else:
                    # Context line: advance both pointers
                    current_old_line += 1
                    current_new_line += 1

                i += 1

        return split_hunks

    def get_file_content_at_lines(
        self, file_path: str, start_line: int, end_line: int, ref: str = "HEAD"
    ) -> List[str]:
        """Get file content at specific line range for context.

        Args:
            file_path: Path to the file
            start_line: Starting line number (1-based)
            end_line: Ending line number (1-based, inclusive)
            ref: Git ref to use for file content (default: HEAD)

        Returns:
            List of lines from the file, empty list on error
        """
        # Use git show with line range for efficiency on large files
        success, output = self.git_ops._run_git_command("show", f"{ref}:{file_path}")

        if not success:
            return []

        try:
            lines = output.split("\n")
            # Convert to 0-based indexing and ensure bounds
            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)

            return lines[start_idx:end_idx]
        except Exception:
            # Handle any parsing errors gracefully
            return []
