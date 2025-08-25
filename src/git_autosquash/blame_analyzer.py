"""Git blame analysis and target commit resolution."""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from enum import Enum

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.batch_git_ops import BatchGitOperations


class TargetingMethod(Enum):
    """Enum for different targeting methods used to resolve a hunk."""
    BLAME_MATCH = "blame_match"
    FALLBACK_NEW_FILE = "fallback_new_file"
    FALLBACK_EXISTING_FILE = "fallback_existing_file"
    FALLBACK_CONSISTENCY = "fallback_consistency"  # Same target as previous hunk from file


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
    targeting_method: TargetingMethod = TargetingMethod.BLAME_MATCH
    fallback_candidates: Optional[List[str]] = None  # List of commit hashes for fallback scenarios
    needs_user_selection: bool = False  # True if user needs to choose from candidates


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
        self.batch_ops = BatchGitOperations(git_ops, merge_base)
        self._branch_commits_cache: Optional[Set[str]] = None
        self._commit_timestamp_cache: Dict[str, int] = {}
        self._file_target_cache: Dict[str, str] = {}  # Track previous targets by file
        self._new_files_cache: Optional[Set[str]] = None

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
            return self._create_fallback_mapping(hunk, TargetingMethod.FALLBACK_NEW_FILE)
        
        # Check for previous target from same file (consistency)
        if hunk.file_path in self._file_target_cache:
            previous_target = self._file_target_cache[hunk.file_path]
            return HunkTargetMapping(
                hunk=hunk,
                target_commit=previous_target,
                confidence="medium",
                blame_info=[],
                targeting_method=TargetingMethod.FALLBACK_CONSISTENCY,
                needs_user_selection=False
            )

        # Try blame-based analysis
        if hunk.has_deletions:
            # Get blame for the old lines being modified/deleted
            blame_info = self._get_blame_for_old_lines(hunk)
        else:
            # Pure addition, look at surrounding context
            blame_info = self._get_blame_for_context(hunk)

        if not blame_info:
            return self._create_fallback_mapping(hunk, TargetingMethod.FALLBACK_EXISTING_FILE)

        # Filter commits to only those within our branch scope
        branch_commits = self._get_branch_commits()
        relevant_blame = [
            info for info in blame_info if info.commit_hash in branch_commits
        ]

        if not relevant_blame:
            return self._create_fallback_mapping(hunk, TargetingMethod.FALLBACK_EXISTING_FILE, blame_info)

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
            needs_user_selection=False
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
        blame_info: List[BlameInfo] = None
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
            needs_user_selection=True
        )

    def _get_fallback_candidates(self, file_path: str, method: TargetingMethod) -> List[str]:
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
