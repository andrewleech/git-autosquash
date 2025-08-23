"""Git blame analysis and target commit resolution."""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk


@dataclass
class BlameInfo:
    """Represents git blame information for a line."""

    commit_hash: str
    author: str
    timestamp: str
    line_number: int
    line_content: str


@dataclass
class HunkTargetMapping:
    """Maps a hunk to its target commit for squashing."""

    hunk: DiffHunk
    target_commit: Optional[str]
    confidence: str  # 'high', 'medium', 'low'
    blame_info: List[BlameInfo]


class BlameAnalyzer:
    """Analyzes git blame to determine target commits for hunks."""

    def __init__(self, git_ops: GitOps, merge_base: str) -> None:
        """Initialize BlameAnalyzer.

        Args:
            git_ops: GitOps instance for running git commands
            merge_base: Merge base commit hash to limit scope
        """
        self.git_ops = git_ops
        self.merge_base = merge_base
        self._branch_commits_cache: Optional[Set[str]] = None
        self._commit_timestamp_cache: Dict[str, int] = {}

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
        # For additions, we need to look at surrounding context
        # For deletions/modifications, we look at the deleted lines
        if hunk.has_deletions:
            # Get blame for the old lines being modified/deleted
            blame_info = self._get_blame_for_old_lines(hunk)
        else:
            # Pure addition, look at surrounding context
            blame_info = self._get_blame_for_context(hunk)

        if not blame_info:
            return HunkTargetMapping(
                hunk=hunk, target_commit=None, confidence="low", blame_info=[]
            )

        # Filter commits to only those within our branch scope
        branch_commits = self._get_branch_commits()
        relevant_blame = [
            info for info in blame_info if info.commit_hash in branch_commits
        ]

        if not relevant_blame:
            return HunkTargetMapping(
                hunk=hunk, target_commit=None, confidence="low", blame_info=blame_info
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

        return HunkTargetMapping(
            hunk=hunk,
            target_commit=most_frequent_commit,
            confidence=confidence,
            blame_info=relevant_blame,
        )

    def _get_blame_for_old_lines(self, hunk: DiffHunk) -> List[BlameInfo]:
        """Get blame information for lines being deleted/modified.

        Args:
            hunk: DiffHunk with deletions

        Returns:
            List of BlameInfo objects for the deleted lines
        """
        # Run blame on the file at HEAD (before changes)
        success, blame_output = self.git_ops._run_git_command(
            "blame",
            f"-L{hunk.old_start},{hunk.old_start + hunk.old_count - 1}",
            "HEAD",
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
        # For additions, look at a few lines before and after
        context_lines = 3
        start_line = max(1, hunk.new_start - context_lines)
        end_line = hunk.new_start + context_lines

        success, blame_output = self.git_ops._run_git_command(
            "blame", f"-L{start_line},{end_line}", "HEAD", "--", hunk.file_path
        )

        if not success:
            return []

        return self._parse_blame_output(blame_output)

    def _parse_blame_output(self, blame_output: str) -> List[BlameInfo]:
        """Parse git blame output into BlameInfo objects.

        Args:
            blame_output: Raw git blame output

        Returns:
            List of parsed BlameInfo objects
        """
        blame_infos = []

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

                blame_info = BlameInfo(
                    commit_hash=commit_hash,
                    author=author,
                    timestamp=timestamp,
                    line_number=line_number,
                    line_content=line_content,
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

        success, output = self.git_ops._run_git_command(
            "rev-list", f"{self.merge_base}..HEAD"
        )

        if not success:
            self._branch_commits_cache = set()
        else:
            self._branch_commits_cache = (
                set(output.strip().split("\n")) if output.strip() else set()
            )

        return self._branch_commits_cache

    def _get_commit_timestamp(self, commit_hash: str) -> int:
        """Get timestamp of a commit for recency comparison.

        Args:
            commit_hash: Commit hash to get timestamp for

        Returns:
            Unix timestamp of the commit
        """
        # Use cache for performance
        if commit_hash in self._commit_timestamp_cache:
            return self._commit_timestamp_cache[commit_hash]

        success, output = self.git_ops._run_git_command(
            "show", "-s", "--format=%ct", commit_hash
        )

        timestamp = 0
        if success:
            try:
                timestamp = int(output.strip())
            except ValueError:
                timestamp = 0

        self._commit_timestamp_cache[commit_hash] = timestamp
        return timestamp

    def get_commit_summary(self, commit_hash: str) -> str:
        """Get a short summary of a commit for display.

        Args:
            commit_hash: Commit hash to summarize

        Returns:
            Short commit summary (hash + subject)
        """
        success, output = self.git_ops._run_git_command(
            "show", "-s", "--format=%h %s", commit_hash
        )

        if not success:
            return commit_hash[:8]

        return output.strip()
