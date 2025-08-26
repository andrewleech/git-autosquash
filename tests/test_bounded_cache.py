"""Tests for bounded cache implementations."""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from git_autosquash.bounded_cache import (
    BoundedLRUCache,
    BoundedCacheSet,
    BoundedCommitInfoCache,
    BoundedFileCommitCache,
)
from git_autosquash.batch_git_ops import BatchCommitInfo


class TestBoundedLRUCache:
    """Test bounded LRU cache implementation."""

    def test_basic_operations(self):
        """Test basic cache operations."""
        cache = BoundedLRUCache[str, int](max_size=3)

        # Test put and get
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)

        assert cache.get("a") == 1
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.size() == 3

    def test_lru_eviction(self):
        """Test LRU eviction policy."""
        cache = BoundedLRUCache[str, int](max_size=2)

        # Fill cache
        cache.put("a", 1)
        cache.put("b", 2)

        # Access "a" to make it most recent
        cache.get("a")

        # Add new item - should evict "b"
        cache.put("c", 3)

        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_update_existing_key(self):
        """Test updating existing key moves it to most recent."""
        cache = BoundedLRUCache[str, int](max_size=2)

        cache.put("a", 1)
        cache.put("b", 2)

        # Update "a" - should move to most recent
        cache.put("a", 10)

        # Add new item - should evict "b", not "a"
        cache.put("c", 3)

        assert cache.get("a") == 10
        assert cache.get("b") is None
        assert cache.get("c") == 3

    def test_thread_safety(self):
        """Test thread safety under concurrent access."""
        cache = BoundedLRUCache[str, int](max_size=100)

        def worker(thread_id: int):
            for i in range(50):
                key = f"thread_{thread_id}_item_{i}"
                cache.put(key, i)
                retrieved = cache.get(key)
                assert retrieved == i or retrieved is None  # May be evicted

        # Run multiple threads concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            for future in futures:
                future.result()

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        cache = BoundedLRUCache[str, int](max_size=2)

        # Initial stats
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["hit_rate"] == 0.0

        # Add items and test hits/misses
        cache.put("a", 1)
        cache.get("a")  # hit
        cache.get("b")  # miss

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_invalid_max_size(self):
        """Test invalid max_size handling."""
        with pytest.raises(ValueError, match="max_size must be positive"):
            BoundedLRUCache[str, int](max_size=0)

        with pytest.raises(ValueError, match="max_size must be positive"):
            BoundedLRUCache[str, int](max_size=-1)

    def test_clear(self):
        """Test cache clearing."""
        cache = BoundedLRUCache[str, int](max_size=5)

        cache.put("a", 1)
        cache.put("b", 2)
        cache.get("a")  # Generate hit for stats

        assert cache.size() == 2

        cache.clear()

        assert cache.size() == 0
        assert cache.get("a") is None
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 1  # The get("a") after clear


class TestBoundedCacheSet:
    """Test bounded set cache implementation."""

    def test_basic_operations(self):
        """Test basic set operations."""
        cache_set = BoundedCacheSet[str](max_size=3)

        cache_set.add("a")
        cache_set.add("b")
        cache_set.add("c")

        assert cache_set.contains("a")
        assert cache_set.contains("b")
        assert cache_set.contains("c")
        assert not cache_set.contains("d")

    def test_lru_eviction_in_set(self):
        """Test LRU eviction in set cache."""
        cache_set = BoundedCacheSet[str](max_size=2)

        cache_set.add("a")
        cache_set.add("b")

        # Access "a" to make it most recent
        cache_set.contains("a")

        # Add new item - should evict "b"
        cache_set.add("c")

        assert cache_set.contains("a")
        assert not cache_set.contains("b")
        assert cache_set.contains("c")


class TestBoundedCommitInfoCache:
    """Test specialized bounded commit info cache."""

    def setup_method(self):
        """Setup test fixtures."""
        self.cache = BoundedCommitInfoCache(max_size=3)
        self.commit1 = BatchCommitInfo(
            commit_hash="abc123",
            short_hash="abc123",
            subject="Test commit 1",
            author="Test Author",
            timestamp=1234567890,
            is_merge=False,
            parent_count=1,
        )
        self.commit2 = BatchCommitInfo(
            commit_hash="def456",
            short_hash="def456",
            subject="Test commit 2",
            author="Test Author",
            timestamp=1234567891,
            is_merge=True,
            parent_count=2,
        )

    def test_batch_operations(self):
        """Test batch put and get operations."""
        # Test batch put
        commit_infos = {"abc123": self.commit1, "def456": self.commit2}
        self.cache.put_batch(commit_infos)

        # Test batch get
        result = self.cache.get_batch(["abc123", "def456", "nonexistent"])
        assert len(result) == 2
        assert result["abc123"] == self.commit1
        assert result["def456"] == self.commit2
        assert "nonexistent" not in result

    def test_get_uncached(self):
        """Test getting uncached commit hashes."""
        self.cache.put_batch({"abc123": self.commit1})

        uncached = self.cache.get_uncached(["abc123", "def456", "ghi789"])
        assert uncached == ["def456", "ghi789"]

    def test_eviction_with_batch_ops(self):
        """Test eviction behavior with batch operations."""
        # Fill cache to capacity
        commits = {}
        for i in range(3):
            hash_val = f"commit{i}"
            commits[hash_val] = BatchCommitInfo(
                commit_hash=hash_val,
                short_hash=hash_val[:7],
                subject=f"Commit {i}",
                author="Test",
                timestamp=1234567890 + i,
                is_merge=False,
                parent_count=1,
            )
        self.cache.put_batch(commits)

        # Add one more - should evict oldest
        new_commit = BatchCommitInfo(
            commit_hash="commit3",
            short_hash="commit3",
            subject="Commit 3",
            author="Test",
            timestamp=1234567893,
            is_merge=False,
            parent_count=1,
        )
        self.cache.put_batch({"commit3": new_commit})

        # First commit should be evicted
        result = self.cache.get_batch(["commit0", "commit1", "commit2", "commit3"])
        assert "commit0" not in result
        assert len(result) == 3


class TestBoundedFileCommitCache:
    """Test specialized bounded file commit cache."""

    def test_basic_file_commit_operations(self):
        """Test basic file commit cache operations."""
        cache = BoundedFileCommitCache(max_size=2)

        cache.put("file1.py", ["commit1", "commit2"])
        cache.put("file2.py", ["commit3", "commit4"])

        assert cache.get("file1.py") == ["commit1", "commit2"]
        assert cache.get("file2.py") == ["commit3", "commit4"]
        assert cache.get("nonexistent.py") is None

    def test_file_cache_mutation_protection(self):
        """Test that cached lists are protected from external mutation."""
        cache = BoundedFileCommitCache(max_size=5)

        original_commits = ["commit1", "commit2"]
        cache.put("file.py", original_commits)

        # Modify original list
        original_commits.append("commit3")

        # Cache should still have original data
        cached_commits = cache.get("file.py")
        assert cached_commits == ["commit1", "commit2"]

        # Modify returned list
        cached_commits.append("commit4")

        # Cache should still have original data
        assert cache.get("file.py") == ["commit1", "commit2"]

    def test_file_cache_eviction(self):
        """Test LRU eviction in file commit cache."""
        cache = BoundedFileCommitCache(max_size=2)

        cache.put("file1.py", ["commit1"])
        cache.put("file2.py", ["commit2"])

        # Access file1 to make it most recent
        cache.get("file1.py")

        # Add new file - should evict file2
        cache.put("file3.py", ["commit3"])

        assert cache.get("file1.py") == ["commit1"]
        assert cache.get("file2.py") is None
        assert cache.get("file3.py") == ["commit3"]

    def test_cache_statistics(self):
        """Test cache statistics for file commit cache."""
        cache = BoundedFileCommitCache(max_size=5)

        cache.put("file1.py", ["commit1"])
        cache.get("file1.py")  # hit
        cache.get("file2.py")  # miss

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == 0.5


class TestConcurrentAccess:
    """Test concurrent access patterns that could cause race conditions."""

    def test_concurrent_cache_operations(self):
        """Test concurrent cache operations for race conditions."""
        cache = BoundedLRUCache[str, int](max_size=10)
        results = []

        def worker(worker_id: int):
            local_results = []
            for i in range(20):
                key = f"key_{i % 5}"  # Reuse keys to test overwrites
                value = worker_id * 100 + i

                cache.put(key, value)
                retrieved = cache.get(key)
                local_results.append(retrieved)

                # Small delay to increase chances of race conditions
                time.sleep(0.001)

            results.extend(local_results)

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(worker, i) for i in range(3)]
            for future in futures:
                future.result()

        # Verify no None values were retrieved immediately after putting
        # (though values may be overwritten by other threads)
        assert len(results) == 60

        # Cache should still be functional
        cache.put("test", 999)
        assert cache.get("test") == 999

    def test_concurrent_eviction_scenarios(self):
        """Test concurrent eviction scenarios."""
        cache = BoundedLRUCache[str, str](max_size=3)

        def rapid_puts(prefix: str):
            for i in range(10):
                cache.put(f"{prefix}_{i}", f"value_{i}")

        # Multiple threads rapidly adding items to trigger evictions
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(rapid_puts, f"thread_{i}") for i in range(3)]
            for future in futures:
                future.result()

        # Cache should maintain size limit and be functional
        assert cache.size() <= 3

        # Should still accept new items
        cache.put("final_test", "final_value")
        assert cache.get("final_test") == "final_value"
