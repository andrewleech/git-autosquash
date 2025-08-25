"""Batch git operations for improved performance."""

import logging
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from functools import lru_cache

from git_autosquash.git_ops import GitOps
from git_autosquash.bounded_cache import BoundedCommitInfoCache, BoundedFileCommitCache, BoundedCacheSet


@dataclass
class BatchCommitInfo:
    """Batch-loaded commit information."""
    commit_hash: str
    short_hash: str
    subject: str
    author: str
    timestamp: int
    is_merge: bool
    parent_count: int


class BatchGitOperations:
    """Efficient batch operations for git commands to reduce subprocess overhead."""
    
    def __init__(self, git_ops: GitOps, merge_base: str) -> None:
        """Initialize batch operations.
        
        Args:
            git_ops: GitOps instance for git command execution
            merge_base: Merge base commit hash
        """
        self.git_ops = git_ops
        self.merge_base = merge_base
        self.logger = logging.getLogger(__name__)
        
        # Bounded caches to prevent memory growth
        self._commit_info_cache = BoundedCommitInfoCache(max_size=500)
        self._file_commit_cache = BoundedFileCommitCache(max_size=200)
        self._new_files_cache = BoundedCacheSet[str](max_size=1000)
        self._branch_commits_cache: Optional[List[str]] = None
        
        # Thread synchronization locks for atomic cache updates
        self._branch_commits_lock = threading.RLock()
        self._new_files_populated = False  # Track if new_files_cache is populated
        self._new_files_lock = threading.RLock()
    
    @lru_cache(maxsize=1)
    def get_branch_commits(self) -> List[str]:
        """Get all branch commits in a single operation.
        
        Returns:
            List of commit hashes from most recent to oldest
        """
        with self._branch_commits_lock:
            if self._branch_commits_cache is not None:
                return self._branch_commits_cache
            
            success, output = self.git_ops._run_git_command(
                "rev-list", "--reverse", f"{self.merge_base}..HEAD"
            )
            
            if not success:
                self._branch_commits_cache = []
            else:
                commits = [line.strip() for line in output.split('\n') if line.strip()]
                # Reverse to get most recent first
                self._branch_commits_cache = list(reversed(commits))
            
            return self._branch_commits_cache
    
    def batch_load_commit_info(self, commit_hashes: List[str]) -> Dict[str, BatchCommitInfo]:
        """Load commit information for multiple commits in batch operations.
        
        Args:
            commit_hashes: List of commit hashes to load info for
            
        Returns:
            Dictionary mapping commit hash to BatchCommitInfo
        """
        # Get already cached commits
        cached_results = self._commit_info_cache.get_batch(commit_hashes)
        
        # Find uncached commits
        uncached = self._commit_info_cache.get_uncached(commit_hashes)
        
        if uncached:
            # Batch load basic commit info
            basic_info = self._batch_load_basic_info(uncached)
            
            # Batch load parent info for merge detection
            parent_info = self._batch_load_parent_info(uncached)
            
            # Build new entries for caching
            new_entries = {}
            for commit_hash in uncached:
                basic = basic_info.get(commit_hash)
                parents = parent_info.get(commit_hash, 0)
                
                if basic:
                    commit_info = BatchCommitInfo(
                        commit_hash=commit_hash,
                        short_hash=basic['short_hash'],
                        subject=basic['subject'],
                        author=basic['author'],
                        timestamp=basic['timestamp'],
                        is_merge=parents > 1,
                        parent_count=parents
                    )
                    new_entries[commit_hash] = commit_info
                    cached_results[commit_hash] = commit_info
            
            # Cache new entries
            self._commit_info_cache.put_batch(new_entries)
        
        return cached_results
    
    def _batch_load_basic_info(self, commit_hashes: List[str]) -> Dict[str, Dict[str, any]]:
        """Load basic commit info in a single git command.
        
        Args:
            commit_hashes: List of commit hashes
            
        Returns:
            Dictionary mapping commit hash to basic info dict
        """
        if not commit_hashes:
            return {}
        
        format_str = "%H|%h|%s|%an|%ct"
        success, output = self.git_ops._run_git_command(
            "show", "-s", f"--format={format_str}", *commit_hashes
        )
        
        if not success:
            return {}
        
        result = {}
        for line in output.split('\n'):
            if not line.strip():
                continue
                
            parts = line.split('|', 4)
            if len(parts) >= 5:
                commit_hash, short_hash, subject, author, timestamp_str = parts
                
                try:
                    timestamp = int(timestamp_str)
                except ValueError:
                    timestamp = 0
                
                result[commit_hash] = {
                    'short_hash': short_hash,
                    'subject': subject,
                    'author': author,
                    'timestamp': timestamp
                }
        
        return result
    
    def _batch_load_parent_info(self, commit_hashes: List[str]) -> Dict[str, int]:
        """Load parent count for multiple commits in batch.
        
        Args:
            commit_hashes: List of commit hashes
            
        Returns:
            Dictionary mapping commit hash to parent count
        """
        if not commit_hashes:
            return {}
        
        success, output = self.git_ops._run_git_command(
            "show", "-s", "--format=%H %P", *commit_hashes
        )
        
        if not success:
            return {}
        
        result = {}
        for line in output.split('\n'):
            if not line.strip():
                continue
                
            parts = line.split()
            if len(parts) >= 1:
                commit_hash = parts[0]
                parent_count = len(parts) - 1  # First part is commit hash, rest are parents
                result[commit_hash] = parent_count
        
        return result
    
    def get_commits_touching_file(self, file_path: str) -> List[str]:
        """Get commits that modified a specific file.
        
        Args:
            file_path: Path to check for modifications
            
        Returns:
            List of commit hashes that touched the file, most recent first
        """
        # Check cache first
        cached_commits = self._file_commit_cache.get(file_path)
        if cached_commits is not None:
            return cached_commits
        
        # Load from git
        success, output = self.git_ops._run_git_command(
            "log", "--format=%H", f"{self.merge_base}..HEAD", "--", file_path
        )
        
        if success:
            commits = [line.strip() for line in output.split('\n') if line.strip()]
        else:
            commits = []
        
        # Cache the result
        self._file_commit_cache.put(file_path, commits)
        return commits
    
    @lru_cache(maxsize=1)
    def get_new_files(self) -> Set[str]:
        """Get set of files that are new since merge-base.
        
        Returns:
            Set of file paths that didn't exist at merge-base
        """
        with self._new_files_lock:
            if self._new_files_populated:
                # Return all files currently in the cache
                # Note: This is a simplification - in practice we'd store the complete set
                # For now, we'll use a traditional cache for this method
                return getattr(self, '_complete_new_files_set', set())
            
            success, output = self.git_ops._run_git_command(
                "diff", "--name-only", "--diff-filter=A", f"{self.merge_base}..HEAD"
            )
            
            if success:
                new_files = set(line.strip() for line in output.split('\n') if line.strip())
            else:
                new_files = set()
            
            # Store complete set and mark as populated
            self._complete_new_files_set = new_files
            self._new_files_populated = True
            
            # Also add individual files to the bounded cache for faster lookups
            for file_path in new_files:
                self._new_files_cache.add(file_path)
            
            return new_files
    
    def is_new_file(self, file_path: str) -> bool:
        """Check if a specific file is new (more efficient than getting full set).
        
        Args:
            file_path: File path to check
            
        Returns:
            True if file is new
        """
        with self._new_files_lock:
            # First check the bounded cache for individual lookups
            if self._new_files_cache.contains(file_path):
                return True
            
            # If not in cache and we haven't populated the full set, check git
            if not self._new_files_populated:
                # Load the complete set
                self.get_new_files()
                
            # Check if it's in the complete set
            complete_set = getattr(self, '_complete_new_files_set', set())
            is_new = file_path in complete_set
            
            # Cache the result for future lookups
            if is_new:
                self._new_files_cache.add(file_path)
                
            return is_new
    
    def batch_load_file_commit_info(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """Batch load commit information for multiple files.
        
        Args:
            file_paths: List of file paths to analyze
            
        Returns:
            Dictionary mapping file path to list of commit hashes
        """
        result = {}
        uncached_files = []
        
        # Check which files are not cached
        for file_path in file_paths:
            cached_commits = self._file_commit_cache.get(file_path)
            if cached_commits is not None:
                result[file_path] = cached_commits
            else:
                uncached_files.append(file_path)
        
        # Load uncached files
        for file_path in uncached_files:
            commits = self.get_commits_touching_file(file_path)  # This caches the result
            result[file_path] = commits
        
        return result
    
    def get_ordered_commits_by_recency(self, commit_hashes: List[str]) -> List[BatchCommitInfo]:
        """Get commits ordered by recency with merge commits last.
        
        Args:
            commit_hashes: List of commit hashes to order
            
        Returns:
            List of BatchCommitInfo objects ordered by priority
        """
        if not commit_hashes:
            return []
        
        # Batch load all commit info
        commit_info_dict = self.batch_load_commit_info(commit_hashes)
        commit_infos = [commit_info_dict[h] for h in commit_hashes if h in commit_info_dict]
        
        # Sort: non-merge commits by recency first, then merge commits by recency
        commit_infos.sort(key=lambda c: (c.is_merge, -c.timestamp))
        
        return commit_infos
    
    def get_file_relevant_commits(
        self, 
        commit_hashes: List[str], 
        file_path: str
    ) -> Tuple[List[BatchCommitInfo], List[BatchCommitInfo]]:
        """Get commits ordered by file relevance.
        
        Args:
            commit_hashes: All available commit hashes
            file_path: File path for relevance filtering
            
        Returns:
            Tuple of (file_relevant_commits, other_commits) both ordered by recency
        """
        file_commits = set(self.get_commits_touching_file(file_path))
        
        # Separate commits that touched the file vs others
        relevant_hashes = [h for h in commit_hashes if h in file_commits]
        other_hashes = [h for h in commit_hashes if h not in file_commits]
        
        # Order both groups by recency
        relevant_infos = self.get_ordered_commits_by_recency(relevant_hashes)
        other_infos = self.get_ordered_commits_by_recency(other_hashes)
        
        return relevant_infos, other_infos
    
    def clear_caches(self) -> None:
        """Clear all internal caches with proper synchronization."""
        # Clear bounded caches (they have their own thread safety)
        self._commit_info_cache.clear()
        self._file_commit_cache.clear()
        self._new_files_cache.clear()
        
        # Clear branch commits cache with lock
        with self._branch_commits_lock:
            self._branch_commits_cache = None
            self.get_branch_commits.cache_clear()
        
        # Clear new files state with lock
        with self._new_files_lock:
            self._new_files_populated = False
            if hasattr(self, '_complete_new_files_set'):
                delattr(self, '_complete_new_files_set')
            self.get_new_files.cache_clear()
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get statistics about cache usage.
        
        Returns:
            Dictionary with cache size information
        """
        stats = {
            'branch_commits_cached': 1 if self._branch_commits_cache is not None else 0,
            'new_files_populated': 1 if self._new_files_populated else 0,
            'branch_commits_lru_info': self.get_branch_commits.cache_info()._asdict(),
            'new_files_lru_info': self.get_new_files.cache_info()._asdict(),
        }
        
        # Add bounded cache statistics
        stats.update(self._commit_info_cache.get_stats())
        stats.update({'file_' + k: v for k, v in self._file_commit_cache.get_stats().items()})
        stats['new_files_cache_size'] = self._new_files_cache.size()
        
        return stats