"""Commit history analysis for fallback target suggestions."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from enum import Enum

from git_autosquash.git_ops import GitOps
from git_autosquash.batch_git_ops import BatchGitOperations


@dataclass
class CommitInfo:
    """Information about a commit for display and selection."""
    
    commit_hash: str
    short_hash: str
    subject: str
    author: str
    timestamp: int
    is_merge: bool
    files_touched: Optional[List[str]] = None


class CommitSelectionStrategy(Enum):
    """Strategy for ordering commit suggestions."""
    RECENCY = "recency"  # Most recent commits first
    FILE_RELEVANCE = "file_relevance"  # Commits that touched specific files first
    MIXED = "mixed"  # File-relevant first, then by recency


class CommitHistoryAnalyzer:
    """Analyzes commit history to provide prioritized suggestions for fallback scenarios."""
    
    def __init__(self, git_ops: GitOps, merge_base: str) -> None:
        """Initialize CommitHistoryAnalyzer.
        
        Args:
            git_ops: GitOps instance for running git commands
            merge_base: Merge base commit hash to limit scope
        """
        self.git_ops = git_ops
        self.merge_base = merge_base
        self.batch_ops = BatchGitOperations(git_ops, merge_base)
        self._commit_cache: Dict[str, CommitInfo] = {}
        self._branch_commits_cache: Optional[List[str]] = None
        self._file_commit_cache: Dict[str, List[str]] = {}
    
    def get_commit_suggestions(
        self,
        strategy: CommitSelectionStrategy,
        target_file: Optional[str] = None
    ) -> List[CommitInfo]:
        """Get prioritized list of commit suggestions.
        
        Args:
            strategy: Strategy for ordering suggestions
            target_file: Optional file path for file-relevant strategies
            
        Returns:
            List of CommitInfo objects ordered by priority
        """
        branch_commits = self._get_branch_commits()
        
        if strategy == CommitSelectionStrategy.RECENCY:
            return self._order_by_recency(branch_commits)
        
        elif strategy == CommitSelectionStrategy.FILE_RELEVANCE and target_file:
            return self._order_by_file_relevance(branch_commits, target_file)
        
        elif strategy == CommitSelectionStrategy.MIXED and target_file:
            return self._order_mixed(branch_commits, target_file)
        
        # Default to recency if strategy doesn't match or missing target_file
        return self._order_by_recency(branch_commits)
    
    def get_commit_info(self, commit_hash: str) -> CommitInfo:
        """Get detailed information about a specific commit.
        
        Args:
            commit_hash: Commit hash to get info for
            
        Returns:
            CommitInfo object with commit details
        """
        if commit_hash not in self._commit_cache:
            batch_info = self.batch_ops.batch_load_commit_info([commit_hash])
            if commit_hash in batch_info:
                batch_commit = batch_info[commit_hash]
                self._commit_cache[commit_hash] = CommitInfo(
                    commit_hash=batch_commit.commit_hash,
                    short_hash=batch_commit.short_hash,
                    subject=batch_commit.subject,
                    author=batch_commit.author,
                    timestamp=batch_commit.timestamp,
                    is_merge=batch_commit.is_merge
                )
            else:
                # Fallback for error cases
                self._commit_cache[commit_hash] = CommitInfo(
                    commit_hash=commit_hash,
                    short_hash=commit_hash[:8],
                    subject="(unknown)",
                    author="(unknown)",
                    timestamp=0,
                    is_merge=False
                )
        
        return self._commit_cache[commit_hash]
    
    def get_commits_touching_file(self, file_path: str) -> List[str]:
        """Get commits that modified a specific file, ordered by recency.
        
        Args:
            file_path: Path to check for modifications
            
        Returns:
            List of commit hashes that touched the file, most recent first
        """
        if file_path not in self._file_commit_cache:
            self._file_commit_cache[file_path] = self.batch_ops.get_commits_touching_file(file_path)
        
        return self._file_commit_cache[file_path]
    
    def is_new_file(self, file_path: str) -> bool:
        """Check if a file is new (added since merge-base).
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file was added since merge-base
        """
        new_files = self.batch_ops.get_new_files()
        return file_path in new_files
    
    def _get_branch_commits(self) -> List[str]:
        """Get all commits on current branch since merge base, ordered by recency.
        
        Returns:
            List of commit hashes from most recent to oldest
        """
        if self._branch_commits_cache is not None:
            return self._branch_commits_cache
        
        self._branch_commits_cache = self.batch_ops.get_branch_commits()
        return self._branch_commits_cache
    
    
    def _order_by_recency(self, commit_hashes: List[str]) -> List[CommitInfo]:
        """Order commits by recency with merge commits last.
        
        Args:
            commit_hashes: List of commit hashes to order
            
        Returns:
            List of CommitInfo objects ordered by recency
        """
        # Use batch operations for efficient loading and ordering
        batch_commits = self.batch_ops.get_ordered_commits_by_recency(commit_hashes)
        
        # Convert to CommitInfo objects
        commit_infos = []
        for batch_commit in batch_commits:
            commit_info = CommitInfo(
                commit_hash=batch_commit.commit_hash,
                short_hash=batch_commit.short_hash,
                subject=batch_commit.subject,
                author=batch_commit.author,
                timestamp=batch_commit.timestamp,
                is_merge=batch_commit.is_merge
            )
            self._commit_cache[batch_commit.commit_hash] = commit_info
            commit_infos.append(commit_info)
        
        return commit_infos
    
    def _order_by_file_relevance(self, commit_hashes: List[str], file_path: str) -> List[CommitInfo]:
        """Order commits by file relevance - commits touching file first.
        
        Args:
            commit_hashes: List of commit hashes to order
            file_path: File path for relevance filtering
            
        Returns:
            List of CommitInfo objects ordered by file relevance
        """
        # Use batch operations for efficient file relevance ordering
        relevant_commits, other_commits = self.batch_ops.get_file_relevant_commits(commit_hashes, file_path)
        
        # Convert to CommitInfo objects
        all_commit_infos = []
        
        # Add relevant commits first
        for batch_commit in relevant_commits:
            commit_info = CommitInfo(
                commit_hash=batch_commit.commit_hash,
                short_hash=batch_commit.short_hash,
                subject=batch_commit.subject,
                author=batch_commit.author,
                timestamp=batch_commit.timestamp,
                is_merge=batch_commit.is_merge
            )
            self._commit_cache[batch_commit.commit_hash] = commit_info
            all_commit_infos.append(commit_info)
        
        # Add other commits
        for batch_commit in other_commits:
            commit_info = CommitInfo(
                commit_hash=batch_commit.commit_hash,
                short_hash=batch_commit.short_hash,
                subject=batch_commit.subject,
                author=batch_commit.author,
                timestamp=batch_commit.timestamp,
                is_merge=batch_commit.is_merge
            )
            self._commit_cache[batch_commit.commit_hash] = commit_info
            all_commit_infos.append(commit_info)
        
        return all_commit_infos
    
    def _order_mixed(self, commit_hashes: List[str], file_path: str) -> List[CommitInfo]:
        """Order commits using mixed strategy - file relevance with recency fallback.
        
        Args:
            commit_hashes: List of commit hashes to order
            file_path: File path for relevance filtering
            
        Returns:
            List of CommitInfo objects ordered by mixed strategy
        """
        # For now, mixed strategy is the same as file relevance
        # Could be enhanced later with additional heuristics
        return self._order_by_file_relevance(commit_hashes, file_path)
    
    def get_commit_display_info(self, commit_hash: str) -> str:
        """Get formatted display string for a commit.
        
        Args:
            commit_hash: Commit hash to format
            
        Returns:
            Formatted string for display in UI
        """
        commit_info = self.get_commit_info(commit_hash)
        
        merge_marker = " (merge)" if commit_info.is_merge else ""
        return f"{commit_info.short_hash} {commit_info.subject}{merge_marker}"
    
    def clear_caches(self) -> None:
        """Clear all internal caches for fresh analysis."""
        self._commit_cache.clear()
        self._branch_commits_cache = None
        self._file_commit_cache.clear()
        self.batch_ops.clear_caches()