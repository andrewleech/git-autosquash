"""Git blame analysis and target commit resolution."""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from enum import Enum

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.batch_git_ops import BatchGitOperations, BlameInfo as BatchBlameInfo

# Configuration constants for contextual blame scanning
CONTEXTUAL_BLAME_LINES = 1  # Default ±1 line search for context
MAX_CONTEXTUAL_BLAME_LINES = 3  # Safety limit to prevent excessive scanning


class TargetingMethod(Enum):
    """Enum for different targeting methods used to resolve a hunk."""

    BLAME_MATCH = "blame_match"
    CONTEXTUAL_BLAME_MATCH = "contextual_blame_match"  # Found via context lines
    FALLBACK_NEW_FILE = "fallback_new_file"
    FALLBACK_EXISTING_FILE = "fallback_existing_file"
    FALLBACK_CONSISTENCY = (
        "fallback_consistency"  # Same target as previous hunk from file
    )


# Use BlameInfo from batch_git_ops
BlameInfo = BatchBlameInfo


@dataclass
class HunkTargetMapping:
    """Maps a hunk to its target commit for squashing."""

    hunk: DiffHunk
    target_commit: Optional[str]
    confidence: str  # 'high', 'medium', 'low'
    blame_info: List[BlameInfo]
    targeting_method: TargetingMethod = TargetingMethod.BLAME_MATCH
    fallback_candidates: Optional[List[str]] = (
        None  # List of commit hashes for fallback scenarios
    )
    needs_user_selection: bool = False  # True if user needs to choose from candidates


class BlameAnalyzer:
    """Analyzes git blame to determine target commits for hunks."""

    def __init__(
        self, git_ops: GitOps, merge_base: str, blame_ref: str = "HEAD"
    ) -> None:
        """Initialize BlameAnalyzer.

        Args:
            git_ops: GitOps instance for running git commands
            merge_base: Merge base commit hash to limit scope
            blame_ref: Git ref to use for blame operations (default: HEAD)
        """
        self.git_ops = git_ops
        self.merge_base = merge_base
        self.blame_ref = blame_ref
        self.batch_ops = BatchGitOperations(git_ops, merge_base, blame_ref=blame_ref)
        self._branch_commits_cache: Optional[Set[str]] = None
        self._commit_timestamp_cache: Dict[str, int] = {}
        self._file_target_cache: Dict[str, str] = {}  # Track previous targets by file
        self._new_files_cache: Optional[Set[str]] = None
        self._file_line_count_cache: Dict[str, int] = {}  # Cache file line counts

    def analyze_hunks(self, hunks: List[DiffHunk]) -> List[HunkTargetMapping]:
        """Analyze hunks and determine target commits for each.

        Args:
            hunks: List of DiffHunk objects to analyze

        Returns:
            List of HunkTargetMapping objects with target commit information
        """
        mappings = []

        for hunk in hunks:
            mapping = self._analyze_single_hunk(hunk)
            mappings.append(mapping)

        return mappings

    def _analyze_single_hunk(self, hunk: DiffHunk) -> HunkTargetMapping:
        """Analyze a single hunk to determine its target commit.

        Args:
            hunk: DiffHunk to analyze

        Returns:
            HunkTargetMapping with target commit information
        """
        # Check if this is a new file
        if self._is_new_file(hunk.file_path):
            return self._create_fallback_mapping(
                hunk, TargetingMethod.FALLBACK_NEW_FILE
            )

        # Check for previous target from same file (consistency)
        if hunk.file_path in self._file_target_cache:
            previous_target = self._file_target_cache[hunk.file_path]
            return HunkTargetMapping(
                hunk=hunk,
                target_commit=previous_target,
                confidence="medium",
                blame_info=[],
                targeting_method=TargetingMethod.FALLBACK_CONSISTENCY,
                needs_user_selection=False,
            )

        # Try blame-based analysis
        if hunk.has_deletions:
            # Get blame for the old lines being modified/deleted
            blame_info = self._get_blame_for_old_lines(hunk)
        else:
            # Pure addition, look at surrounding context
            blame_info = self._get_blame_for_context(hunk)

        if not blame_info:
            # Try contextual blame scanning as a fallback before giving up
            contextual_result = self._try_contextual_blame_fallback(
                hunk, self._get_branch_commits()
            )
            if contextual_result:
                return contextual_result

            return self._create_fallback_mapping(
                hunk, TargetingMethod.FALLBACK_EXISTING_FILE
            )

        # Filter commits to only those within our branch scope
        branch_commits = self._get_branch_commits()
        relevant_blame = [
            info for info in blame_info if info.commit_hash in branch_commits
        ]

        if not relevant_blame:
            # Try contextual blame scanning as a fallback before giving up
            contextual_result = self._try_contextual_blame_fallback(
                hunk, branch_commits
            )
            if contextual_result:
                return contextual_result

            return self._create_fallback_mapping(
                hunk, TargetingMethod.FALLBACK_EXISTING_FILE, blame_info
            )

        # Group by commit and count occurrences
        commit_counts: Dict[str, int] = {}
        for info in relevant_blame:
            commit_counts[info.commit_hash] = commit_counts.get(info.commit_hash, 0) + 1

        # Find most frequent commit, break ties by recency (requirement: take most recent)
        most_frequent_commit, max_count = max(
            commit_counts.items(),
            key=lambda x: (x[1], self._get_commit_timestamp(x[0])),
        )

        total_lines = len(relevant_blame)
        confidence_ratio = max_count / total_lines

        if confidence_ratio >= 0.8:
            confidence = "high"
        elif confidence_ratio >= 0.5:
            confidence = "medium"
        else:
            confidence = "low"

        # Store successful target for file consistency
        self._file_target_cache[hunk.file_path] = most_frequent_commit

        return HunkTargetMapping(
            hunk=hunk,
            target_commit=most_frequent_commit,
            confidence=confidence,
            blame_info=relevant_blame,
            targeting_method=TargetingMethod.BLAME_MATCH,
            needs_user_selection=False,
        )

    def _get_blame_for_old_lines(self, hunk: DiffHunk) -> List[BlameInfo]:
        """Get blame information for lines being deleted/modified.

        Args:
            hunk: DiffHunk with deletions

        Returns:
            List of BlameInfo objects for the deleted lines
        """
        # Run blame on the file at configured ref (before changes)
        success, blame_output = self.git_ops._run_git_command(
            "blame",
            f"-L{hunk.old_start},{hunk.old_start + hunk.old_count - 1}",
            self.blame_ref,
            "--",
            hunk.file_path,
        )

        if not success:
            return []

        return self._parse_blame_output(blame_output)

    def _get_blame_for_context(self, hunk: DiffHunk) -> List[BlameInfo]:
        """Get blame information for context around an addition.

        Args:
            hunk: DiffHunk with additions

        Returns:
            List of BlameInfo objects for surrounding context
        """
        # For additions, we need to map the new coordinates back to old coordinates
        # The insertion happens at new_start, so we look around old_start
        context_lines = 3

        # For pure additions, old_start is where the insertion point was at blame_ref
        start_line = max(1, hunk.old_start - context_lines)
        end_line = hunk.old_start + context_lines

        success, blame_output = self.git_ops._run_git_command(
            "blame", f"-L{start_line},{end_line}", self.blame_ref, "--", hunk.file_path
        )

        if not success:
            return []

        return self._parse_blame_output(blame_output)

    def _get_contextual_lines_for_hunk(
        self, hunk: DiffHunk, context_lines: int = CONTEXTUAL_BLAME_LINES
    ) -> List[int]:
        """Get meaningful (non-whitespace) line numbers around a hunk.

        Uses OLD coordinates since git blame operates on HEAD (pre-change) state.
        For pure additions, searches around the insertion point in the original file.

        Args:
            hunk: DiffHunk to get context for
            context_lines: Number of lines above/below to consider

        Returns:
            List of line numbers that are meaningful context lines in HEAD
        """
        context_lines = min(context_lines, MAX_CONTEXTUAL_BLAME_LINES)

        # Use OLD coordinates for git blame HEAD compatibility
        if hunk.has_deletions or hunk.old_count > 0:
            # For modifications/deletions, use old coordinates
            base_start = hunk.old_start
            base_count = hunk.old_count
        else:
            # For pure additions, use insertion point in original file
            base_start = hunk.old_start
            base_count = 0  # No lines existed at insertion point

        # Get file line count to respect boundaries
        file_line_count = self._get_file_line_count(hunk.file_path)

        # Calculate context range around the hunk
        if base_count > 0:
            # For modifications/deletions: search around existing lines
            start_line = max(1, base_start - context_lines)
            end_line = min(file_line_count, base_start + base_count + context_lines - 1)
        else:
            # For pure additions: search around insertion point
            start_line = max(1, base_start - context_lines)
            end_line = min(file_line_count, base_start + context_lines)

        # Get all potential context lines
        potential_lines = list(range(start_line, end_line + 1))

        # Filter out whitespace-only lines
        meaningful_lines = self._filter_meaningful_lines(
            hunk.file_path, potential_lines
        )

        return meaningful_lines

    def _try_contextual_blame_fallback(
        self, hunk: DiffHunk, branch_commits: Set[str]
    ) -> Optional[HunkTargetMapping]:
        """Try contextual blame as fallback and return mapping if successful.

        Args:
            hunk: DiffHunk to analyze
            branch_commits: Set of commit hashes within branch scope

        Returns:
            HunkTargetMapping if contextual blame finds targets, None otherwise
        """
        contextual_blame_info = self._get_contextual_blame(hunk)

        if not contextual_blame_info:
            return None

        # Filter contextual blame to branch commits
        contextual_relevant_blame = [
            info for info in contextual_blame_info if info.commit_hash in branch_commits
        ]

        if contextual_relevant_blame:
            # Found contextual matches - analyze them
            return self._create_contextual_mapping(hunk, contextual_relevant_blame)

        return None

    def _get_file_line_count(self, file_path: str) -> int:
        """Get total line count for a file with safe fallback strategies.

        Args:
            file_path: Path to file

        Returns:
            Number of lines in file
        """
        if file_path in self._file_line_count_cache:
            return self._file_line_count_cache[file_path]

        # Try multiple approaches in order of preference
        line_count = self._try_get_line_count_from_head(file_path)
        if line_count is None:
            line_count = self._try_get_line_count_from_working_tree(file_path)
        if line_count is None:
            line_count = self._get_conservative_line_count_from_diff(file_path)

        # Cache and return
        self._file_line_count_cache[file_path] = line_count
        return line_count

    def _try_get_line_count_from_head(self, file_path: str) -> Optional[int]:
        """Try to get line count from blame_ref version of file.

        Args:
            file_path: Path to file

        Returns:
            Line count if successful, None otherwise
        """
        success, output = self.git_ops._run_git_command(
            "show", f"{self.blame_ref}:{file_path}"
        )
        if success and output is not None:
            return len(output.split("\n")) if output else 1
        return None

    def _try_get_line_count_from_working_tree(self, file_path: str) -> Optional[int]:
        """Try to get line count from working tree version of file.

        Args:
            file_path: Path to file

        Returns:
            Line count if successful, None otherwise
        """
        import os

        try:
            full_path = os.path.join(self.git_ops.repo_path, file_path)
            if os.path.exists(full_path):
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    return sum(1 for _ in f)
        except (OSError, IOError):
            pass
        return None

    def _get_conservative_line_count_from_diff(self, file_path: str) -> int:
        """Get conservative line count based on diff information.

        Args:
            file_path: Path to file

        Returns:
            Conservative estimate of line count
        """
        success, output = self.git_ops._run_git_command(
            "diff", f"{self.merge_base}..HEAD", "--", file_path
        )

        if success and output:
            # Parse diff to find highest line number mentioned
            max_line = 0
            for line in output.split("\n"):
                if line.startswith("@@"):
                    # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
                    import re

                    match = re.match(
                        r"@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@", line
                    )
                    if match:
                        new_start = int(match.group(3))
                        new_count = int(match.group(4)) if match.group(4) else 1
                        max_line = max(max_line, new_start + new_count - 1)

            if max_line > 0:
                return max_line + 10  # Add buffer for safety

        # Ultra-conservative fallback
        return 50

    def _filter_meaningful_lines(
        self, file_path: str, line_numbers: List[int]
    ) -> List[int]:
        """Filter out whitespace-only lines from a list of line numbers.

        Args:
            file_path: Path to file
            line_numbers: List of line numbers to check

        Returns:
            List of line numbers that contain meaningful content
        """
        if not line_numbers:
            return []

        meaningful_lines = []

        # Get the file content to check line contents
        success, file_content = self.git_ops._run_git_command(
            "show", f"{self.blame_ref}:{file_path}"
        )
        if not success:
            # If we can't read the file, assume all lines are meaningful
            return line_numbers

        lines = file_content.split("\n")

        for line_num in line_numbers:
            if 1 <= line_num <= len(lines):
                line_content = lines[line_num - 1]  # Convert to 0-based indexing
                # Skip empty lines and whitespace-only lines
                if line_content.strip():
                    meaningful_lines.append(line_num)

        return meaningful_lines

    def _get_contextual_blame(self, hunk: DiffHunk) -> List[BlameInfo]:
        """Get blame information for meaningful context lines around a hunk.

        This is used as a fallback when primary blame analysis fails.
        It searches ±1 line (excluding whitespace) for blame information.
        Uses batch operations for improved performance.

        Args:
            hunk: DiffHunk to get contextual blame for

        Returns:
            List of BlameInfo objects from context lines
        """
        context_lines = self._get_contextual_lines_for_hunk(hunk)
        if not context_lines:
            return []

        # Convert individual lines to ranges for batch blame
        line_ranges = [(line_num, line_num) for line_num in context_lines]

        # Use batch blame operation
        batch_blame_info = self.batch_ops.batch_blame_lines(hunk.file_path, line_ranges)

        # Convert batch blame info to regular blame info and expand hashes
        all_blame_info = []
        short_hashes = []

        for line_num in context_lines:
            if line_num in batch_blame_info:
                batch_info = batch_blame_info[line_num]
                short_hashes.append(batch_info.commit_hash)

        # Batch expand hashes
        expanded_hashes = (
            self.batch_ops.batch_expand_hashes(short_hashes) if short_hashes else {}
        )

        # Create BlameInfo objects with expanded hashes
        for line_num in context_lines:
            if line_num in batch_blame_info:
                batch_info = batch_blame_info[line_num]
                expanded_hash = expanded_hashes.get(
                    batch_info.commit_hash, batch_info.commit_hash
                )

                blame_info = BlameInfo(
                    commit_hash=expanded_hash,
                    author=batch_info.author,
                    timestamp=batch_info.timestamp,
                    line_number=batch_info.line_number,
                    line_content=batch_info.line_content,
                )
                all_blame_info.append(blame_info)

        return all_blame_info

    def _get_blame_for_single_line(
        self, file_path: str, line_num: int
    ) -> List[BlameInfo]:
        """Get blame information for a single line.

        Args:
            file_path: Path to file
            line_num: Line number to get blame for

        Returns:
            List of BlameInfo objects (usually just one)
        """
        success, blame_output = self.git_ops._run_git_command(
            "blame", f"-L{line_num},{line_num}", self.blame_ref, "--", file_path
        )

        if not success:
            return []

        return self._parse_blame_output(blame_output)

    def _create_contextual_mapping(
        self, hunk: DiffHunk, contextual_blame: List[BlameInfo]
    ) -> HunkTargetMapping:
        """Create a mapping from contextual blame analysis.

        Args:
            hunk: DiffHunk that was analyzed
            contextual_blame: List of BlameInfo from context lines

        Returns:
            HunkTargetMapping with contextual target commit
        """
        # Group by commit and count occurrences (same logic as primary blame)
        commit_counts: Dict[str, int] = {}
        for info in contextual_blame:
            commit_counts[info.commit_hash] = commit_counts.get(info.commit_hash, 0) + 1

        # Find most frequent commit, break ties by recency
        most_frequent_commit, max_count = max(
            commit_counts.items(),
            key=lambda x: (x[1], self._get_commit_timestamp(x[0])),
        )

        total_lines = len(contextual_blame)
        confidence_ratio = max_count / total_lines

        # Contextual matches have slightly lower confidence than direct matches
        if confidence_ratio >= 0.8:
            confidence = "medium"  # Reduced from "high"
        elif confidence_ratio >= 0.5:
            confidence = "medium"
        else:
            confidence = "low"

        # Store successful target for file consistency
        self._file_target_cache[hunk.file_path] = most_frequent_commit

        return HunkTargetMapping(
            hunk=hunk,
            target_commit=most_frequent_commit,
            confidence=confidence,
            blame_info=contextual_blame,
            targeting_method=TargetingMethod.CONTEXTUAL_BLAME_MATCH,
            needs_user_selection=False,
        )

    def _parse_blame_output(self, blame_output: str) -> List[BlameInfo]:
        """Parse git blame output into BlameInfo objects with batch hash expansion.

        Args:
            blame_output: Raw git blame output

        Returns:
            List of parsed BlameInfo objects with expanded commit hashes
        """
        # First pass: collect all blame entries with short hashes
        raw_blame_infos = []
        short_hashes = []

        for line in blame_output.split("\n"):
            if not line.strip():
                continue

            # Parse blame line format:
            # commit_hash (author timestamp line_num) line_content
            match = re.match(
                r"^([a-f0-9]+)\s+\(([^)]+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\s+(\d+)\)\s*(.*)",
                line,
            )
            if match:
                commit_hash = match.group(1)
                author = match.group(2).strip()
                timestamp = match.group(3)
                line_number = int(match.group(4))
                line_content = match.group(5)

                raw_blame_infos.append(
                    {
                        "commit_hash": commit_hash,
                        "author": author,
                        "timestamp": timestamp,
                        "line_number": line_number,
                        "line_content": line_content,
                    }
                )

                if len(commit_hash) < 40:  # Short hash
                    short_hashes.append(commit_hash)

        # Batch expand short hashes
        expanded_hashes = (
            self.batch_ops.batch_expand_hashes(short_hashes) if short_hashes else {}
        )

        # Second pass: create BlameInfo objects with expanded hashes
        blame_infos = []
        for raw_info in raw_blame_infos:
            commit_hash = str(raw_info["commit_hash"])
            full_commit_hash = expanded_hashes.get(commit_hash, commit_hash)

            blame_info = BlameInfo(
                commit_hash=full_commit_hash,
                author=str(raw_info["author"]),
                timestamp=str(raw_info["timestamp"]),
                line_number=int(raw_info["line_number"]),
                line_content=str(raw_info["line_content"]),
            )
            blame_infos.append(blame_info)

        return blame_infos

    def _get_branch_commits(self) -> Set[str]:
        """Get all commits on current branch since merge base.

        Returns:
            Set of commit hashes within branch scope
        """
        if self._branch_commits_cache is not None:
            return self._branch_commits_cache

        branch_commits = self.batch_ops.get_branch_commits()
        self._branch_commits_cache = set(branch_commits)
        return self._branch_commits_cache

    def _get_commit_timestamp(self, commit_hash: str) -> int:
        """Get timestamp of a commit for recency comparison.

        Args:
            commit_hash: Commit hash to get timestamp for

        Returns:
            Unix timestamp of the commit
        """
        # Use batch operations for better performance
        commit_info = self.batch_ops.batch_load_commit_info([commit_hash])
        if commit_hash in commit_info:
            return commit_info[commit_hash].timestamp
        return 0

    def get_commit_summary(self, commit_hash: str) -> str:
        """Get a short summary of a commit for display.

        Args:
            commit_hash: Commit hash to summarize

        Returns:
            Short commit summary (hash + subject)
        """
        commit_info = self.batch_ops.batch_load_commit_info([commit_hash])
        if commit_hash in commit_info:
            info = commit_info[commit_hash]
            return f"{info.short_hash} {info.subject}"
        return commit_hash[:8]

    def _is_new_file(self, file_path: str) -> bool:
        """Check if a file is new (didn't exist at merge-base).

        Args:
            file_path: Path to check

        Returns:
            True if file is new, False if it existed at merge-base
        """
        if self._new_files_cache is None:
            self._new_files_cache = self.batch_ops.get_new_files()

        return file_path in self._new_files_cache

    def _create_fallback_mapping(
        self,
        hunk: DiffHunk,
        method: TargetingMethod,
        blame_info: Optional[List[BlameInfo]] = None,
    ) -> HunkTargetMapping:
        """Create a fallback mapping that needs user selection.

        Args:
            hunk: DiffHunk to create mapping for
            method: Fallback method used
            blame_info: Optional blame info if available

        Returns:
            HunkTargetMapping with fallback candidates
        """
        candidates = self._get_fallback_candidates(hunk.file_path, method)

        return HunkTargetMapping(
            hunk=hunk,
            target_commit=None,
            confidence="low",
            blame_info=blame_info or [],
            targeting_method=method,
            fallback_candidates=candidates,
            needs_user_selection=True,
        )

    def _get_fallback_candidates(
        self, file_path: str, method: TargetingMethod
    ) -> List[str]:
        """Get prioritized list of candidate commits for fallback scenarios.

        Args:
            file_path: Path of the file being processed
            method: Fallback method to determine candidate ordering

        Returns:
            List of commit hashes ordered by priority
        """
        branch_commits = self._get_ordered_branch_commits()

        if method == TargetingMethod.FALLBACK_NEW_FILE:
            # For new files, just return recent commits first, merges last
            return branch_commits

        elif method == TargetingMethod.FALLBACK_EXISTING_FILE:
            # For existing files, prioritize commits that touched this file
            file_commits = self._get_commits_touching_file(file_path)
            other_commits = [c for c in branch_commits if c not in file_commits]
            return file_commits + other_commits

        return branch_commits

    def _get_ordered_branch_commits(self) -> List[str]:
        """Get branch commits ordered by recency, with merge commits last.

        Returns:
            List of commit hashes ordered by priority
        """
        branch_commits = list(self._get_branch_commits())
        if not branch_commits:
            return []

        # Use batch operations to get ordered commits
        ordered_commits = self.batch_ops.get_ordered_commits_by_recency(branch_commits)
        return [commit.commit_hash for commit in ordered_commits]

    def _get_commits_touching_file(self, file_path: str) -> List[str]:
        """Get commits that modified a specific file, ordered by recency.

        Args:
            file_path: Path to check for modifications

        Returns:
            List of commit hashes that touched the file
        """
        return self.batch_ops.get_commits_touching_file(file_path)

    def _is_merge_commit(self, commit_hash: str) -> bool:
        """Check if a commit is a merge commit.

        Args:
            commit_hash: Commit to check

        Returns:
            True if commit is a merge commit
        """
        commit_info = self.batch_ops.batch_load_commit_info([commit_hash])
        if commit_hash in commit_info:
            return commit_info[commit_hash].is_merge
        return False

    def set_target_for_file(self, file_path: str, target_commit: str) -> None:
        """Set target commit for a file to ensure consistency.

        Args:
            file_path: File path
            target_commit: Commit hash to use as target
        """
        self._file_target_cache[file_path] = target_commit

    def clear_file_cache(self) -> None:
        """Clear the file target cache for a fresh analysis."""
        self._file_target_cache.clear()
        self.batch_ops.clear_caches()
        self._branch_commits_cache = None
        self._new_files_cache = None
        self._file_line_count_cache.clear()
