"""Thread-safe bounded LRU cache implementations."""

import threading
from collections import OrderedDict
from typing import Dict, Generic, List, Optional, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from git_autosquash.batch_git_ops import BatchCommitInfo

K = TypeVar("K")  # Key type
V = TypeVar("V")  # Value type


class BoundedLRUCache(Generic[K, V]):
    """Thread-safe bounded LRU cache with size limits."""

    def __init__(self, max_size: int = 1000):
        """Initialize bounded LRU cache.

        Args:
            max_size: Maximum number of entries to cache
        """
        if max_size <= 0:
            raise ValueError("max_size must be positive")

        self.max_size = max_size
        self._cache: OrderedDict[K, V] = OrderedDict()
        self._lock = threading.RLock()

        # Statistics
        self._hits = 0
        self._misses = 0

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Get value from cache, moving it to end (most recent).

        Args:
            key: Key to lookup
            default: Default value if key not found

        Returns:
            Cached value or default
        """
        with self._lock:
            if key in self._cache:
                # Move to end (most recent)
                value = self._cache.pop(key)
                self._cache[key] = value
                self._hits += 1
                return value
            else:
                self._misses += 1
                return default

    def put(self, key: K, value: V) -> None:
        """Put value in cache, evicting oldest if at capacity.

        Args:
            key: Key to store
            value: Value to store
        """
        with self._lock:
            if key in self._cache:
                # Update existing entry and move to end
                self._cache.pop(key)
            elif len(self._cache) >= self.max_size:
                # Evict oldest entry
                self._cache.popitem(last=False)

            # Add new entry at end (most recent)
            self._cache[key] = value

    def contains(self, key: K) -> bool:
        """Check if key exists in cache without updating access order.

        Args:
            key: Key to check

        Returns:
            True if key exists
        """
        with self._lock:
            return key in self._cache

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def size(self) -> int:
        """Get current number of cached entries."""
        with self._lock:
            return len(self._cache)

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with hits, misses, size, and hit_rate
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests) if total_requests > 0 else 0.0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hit_rate": hit_rate,
            }


class BoundedCacheSet(Generic[K]):
    """Thread-safe bounded set-like cache for existence checks."""

    def __init__(self, max_size: int = 1000):
        """Initialize bounded set cache.

        Args:
            max_size: Maximum number of entries to cache
        """
        if max_size <= 0:
            raise ValueError("max_size must be positive")

        self.max_size = max_size
        self._cache: OrderedDict[K, bool] = OrderedDict()
        self._lock = threading.RLock()

    def add(self, key: K) -> None:
        """Add key to set cache.

        Args:
            key: Key to add
        """
        with self._lock:
            if key in self._cache:
                # Move to end (most recent)
                self._cache.pop(key)
            elif len(self._cache) >= self.max_size:
                # Evict oldest entry
                self._cache.popitem(last=False)

            # Add at end (most recent)
            self._cache[key] = True

    def contains(self, key: K) -> bool:
        """Check if key exists in set cache.

        Args:
            key: Key to check

        Returns:
            True if key exists
        """
        with self._lock:
            if key in self._cache:
                # Move to end (most recent) on access
                value = self._cache.pop(key)
                self._cache[key] = value
                return True
            return False

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        """Get current number of cached entries."""
        with self._lock:
            return len(self._cache)


class BoundedCommitInfoCache:
    """Specialized bounded cache for BatchCommitInfo objects."""

    def __init__(self, max_size: int = 500):
        """Initialize bounded commit info cache.

        Args:
            max_size: Maximum number of commit entries to cache
        """
        self._cache = BoundedLRUCache[str, "BatchCommitInfo"](max_size)

    def get_batch(self, commit_hashes: List[str]) -> Dict[str, "BatchCommitInfo"]:
        """Get multiple commits from cache.

        Args:
            commit_hashes: List of commit hashes to retrieve

        Returns:
            Dictionary mapping commit hash to BatchCommitInfo for cached entries
        """
        result = {}
        for commit_hash in commit_hashes:
            cached_info = self._cache.get(commit_hash)
            if cached_info is not None:
                result[commit_hash] = cached_info
        return result

    def put_batch(self, commit_infos: Dict[str, "BatchCommitInfo"]) -> None:
        """Put multiple commits in cache.

        Args:
            commit_infos: Dictionary mapping commit hash to BatchCommitInfo
        """
        for commit_hash, commit_info in commit_infos.items():
            self._cache.put(commit_hash, commit_info)

    def get_uncached(self, commit_hashes: List[str]) -> List[str]:
        """Get list of commit hashes that are not cached.

        Args:
            commit_hashes: List of commit hashes to check

        Returns:
            List of uncached commit hashes
        """
        return [h for h in commit_hashes if not self._cache.contains(h)]

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return self._cache.get_stats()


class BoundedFileCommitCache:
    """Specialized bounded cache for file commit mappings."""

    def __init__(self, max_size: int = 200):
        """Initialize bounded file commit cache.

        Args:
            max_size: Maximum number of file entries to cache
        """
        self._cache = BoundedLRUCache[str, List[str]](max_size)

    def get(self, file_path: str) -> Optional[List[str]]:
        """Get commits for a file path.

        Args:
            file_path: File path to lookup

        Returns:
            Copy of list of commit hashes or None if not cached
        """
        cached_list = self._cache.get(file_path)
        return cached_list.copy() if cached_list is not None else None

    def put(self, file_path: str, commits: List[str]) -> None:
        """Cache commits for a file path.

        Args:
            file_path: File path
            commits: List of commit hashes
        """
        self._cache.put(file_path, commits.copy())  # Store a copy to avoid mutation

    def contains(self, file_path: str) -> bool:
        """Check if file path is cached.

        Args:
            file_path: File path to check

        Returns:
            True if cached
        """
        return self._cache.contains(file_path)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return self._cache.get_stats()
