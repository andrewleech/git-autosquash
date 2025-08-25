"""Tests for batch git operations edge cases and error handling."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from git_autosquash.batch_git_ops import BatchGitOperations, BatchCommitInfo
from git_autosquash.git_ops import GitOps


class TestBatchGitOperationsEdgeCases:
    """Test edge cases and error handling in batch git operations."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_git_ops = MagicMock(spec=GitOps)
        self.merge_base = "main"
        self.batch_ops = BatchGitOperations(self.mock_git_ops, self.merge_base)

    def test_empty_commit_list_handling(self):
        """Test handling of empty commit lists."""
        # Test batch_load_commit_info with empty list
        result = self.batch_ops.batch_load_commit_info([])
        assert result == {}

    def test_malformed_git_output_handling(self):
        """Test handling of malformed git command output."""
        # Test malformed commit info output
        self.mock_git_ops._run_git_command.return_value = (True, "malformed|incomplete")
        
        result = self.batch_ops.batch_load_commit_info(["abc123"])
        assert result == {}  # Should handle gracefully

    def test_git_command_failure_handling(self):
        """Test handling of git command failures."""
        # Test failed git commands
        self.mock_git_ops._run_git_command.return_value = (False, "fatal: not a git repository")
        
        # Should handle gracefully without exceptions
        result = self.batch_ops.get_branch_commits()
        assert result == []
        
        result = self.batch_ops.batch_load_commit_info(["abc123"])
        assert result == {}

    def test_invalid_commit_hash_handling(self):
        """Test handling of invalid commit hashes."""
        # Mock git output with invalid timestamp
        self.mock_git_ops._run_git_command.side_effect = [
            (True, "abc123|abc|Test|Author|invalid_timestamp"),  # Basic info with invalid timestamp
            (True, "abc123 parent1 parent2")  # Parent info
        ]
        
        result = self.batch_ops.batch_load_commit_info(["abc123"])
        
        # Should create commit info with timestamp=0 for invalid timestamp
        assert "abc123" in result
        assert result["abc123"].timestamp == 0

    def test_unicode_handling_in_commit_messages(self):
        """Test handling of unicode characters in commit messages."""
        unicode_subject = "Add 测试 feature with émojis 🚀"
        unicode_author = "Tést Üser"
        
        self.mock_git_ops._run_git_command.side_effect = [
            (True, f"abc123|abc|{unicode_subject}|{unicode_author}|1234567890"),
            (True, "abc123 parent1")
        ]
        
        result = self.batch_ops.batch_load_commit_info(["abc123"])
        
        assert "abc123" in result
        assert result["abc123"].subject == unicode_subject
        assert result["abc123"].author == unicode_author

    def test_very_long_commit_info_handling(self):
        """Test handling of very long commit messages and author names."""
        long_subject = "A" * 1000  # Very long commit subject
        long_author = "B" * 500   # Very long author name
        
        self.mock_git_ops._run_git_command.side_effect = [
            (True, f"abc123|abc|{long_subject}|{long_author}|1234567890"),
            (True, "abc123 parent1")
        ]
        
        result = self.batch_ops.batch_load_commit_info(["abc123"])
        
        assert "abc123" in result
        assert result["abc123"].subject == long_subject
        assert result["abc123"].author == long_author

    def test_concurrent_cache_access_patterns(self):
        """Test concurrent access to caches under various patterns."""
        # Mock git operations
        def mock_git_response(command, *args):
            if command == "rev-list":
                return (True, "commit1\ncommit2\ncommit3")
            elif command == "show":
                if "--format=%H|%h|%s|%an|%ct" in args:
                    return (True, "commit1|c1|Subject 1|Author|1234567890\ncommit2|c2|Subject 2|Author|1234567891")
                elif "--format=%H %P" in args:
                    return (True, "commit1 parent1\ncommit2 parent1 parent2")
            elif command == "log":
                return (True, "commit1\ncommit2")
            elif command == "diff":
                return (True, "new_file.py\nanother_new_file.py")
            return (False, "Unknown command")
        
        self.mock_git_ops._run_git_command.side_effect = mock_git_response

        def worker(worker_id: int):
            """Worker function for concurrent testing."""
            # Mix different operations
            commits = self.batch_ops.get_branch_commits()
            if commits:
                commit_info = self.batch_ops.batch_load_commit_info([commits[0]])
                file_commits = self.batch_ops.get_commits_touching_file(f"file_{worker_id}.py")
                is_new = self.batch_ops.is_new_file(f"file_{worker_id}.py")
                
                # Verify results are consistent
                assert isinstance(commits, list)
                assert isinstance(commit_info, dict)
                assert isinstance(file_commits, list)
                assert isinstance(is_new, bool)

        # Run concurrent operations
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(10)]
            for future in futures:
                future.result()  # Will raise exception if any worker failed

    def test_cache_memory_limits_under_load(self):
        """Test that caches respect memory limits under heavy load."""
        # Create large dataset that would exceed cache limits
        large_commit_list = [f"commit_{i:04d}" for i in range(1000)]
        
        def mock_git_response(command, *args):
            if command == "show" and "--format=%H|%h|%s|%an|%ct" in args:
                # Return data for all requested commits
                lines = []
                for commit in args:
                    if commit.startswith("commit_"):
                        lines.append(f"{commit}|{commit[:7]}|Subject for {commit}|Author|1234567890")
                return (True, "\n".join(lines))
            elif command == "show" and "--format=%H %P" in args:
                lines = []
                for commit in args:
                    if commit.startswith("commit_"):
                        lines.append(f"{commit} parent1")
                return (True, "\n".join(lines))
            return (False, "Unknown command")
        
        self.mock_git_ops._run_git_command.side_effect = mock_git_response

        # Load more commits than cache can hold
        for i in range(0, 1000, 50):  # Process in batches
            batch = large_commit_list[i:i+50]
            self.batch_ops.batch_load_commit_info(batch)

        # Verify cache stats show bounded size
        stats = self.batch_ops.get_cache_stats()
        assert stats['size'] <= 500  # Should respect max_size limit

    def test_error_recovery_after_git_failures(self):
        """Test that operations continue to work after git command failures."""
        # Start with failing git commands
        self.mock_git_ops._run_git_command.return_value = (False, "git error")
        
        # Operations should handle failures gracefully
        result = self.batch_ops.get_branch_commits()
        assert result == []
        
        result = self.batch_ops.batch_load_commit_info(["abc123"])
        assert result == {}

        # Now fix git commands
        def fixed_git_response(command, *args):
            if command == "rev-list":
                return (True, "commit1\ncommit2")
            elif command == "show":
                if "--format=%H|%h|%s|%an|%ct" in args:
                    return (True, "commit1|c1|Subject|Author|1234567890")
                elif "--format=%H %P" in args:
                    return (True, "commit1 parent1")
            return (True, "")
        
        self.mock_git_ops._run_git_command.side_effect = fixed_git_response

        # Operations should work normally after recovery
        self.batch_ops.clear_caches()  # Clear any cached failures
        
        result = self.batch_ops.get_branch_commits()
        assert len(result) == 2

    def test_partial_data_scenarios(self):
        """Test scenarios with partial or inconsistent data."""
        # Mock scenario where basic info succeeds but parent info fails
        def partial_git_response(command, *args):
            if command == "show":
                if "--format=%H|%h|%s|%an|%ct" in args:
                    return (True, "commit1|c1|Subject|Author|1234567890")
                elif "--format=%H %P" in args:
                    return (False, "failed to get parent info")
            return (True, "")
        
        self.mock_git_ops._run_git_command.side_effect = partial_git_response

        result = self.batch_ops.batch_load_commit_info(["commit1"])
        
        # Should create commit info with default parent_count=0
        assert "commit1" in result
        assert result["commit1"].parent_count == 0
        assert result["commit1"].is_merge is False

    def test_file_path_edge_cases(self):
        """Test edge cases with file paths."""
        edge_case_files = [
            "file with spaces.py",
            "file-with-dashes.py",
            "file_with_underscores.py",
            "filé-with-unicode.py",
            "very/deep/nested/path/file.py",
            ".hidden_file",
            "file.with.many.dots.py"
        ]
        
        def file_git_response(command, *args):
            if command == "log":
                # Return some commits for each file
                return (True, "commit1\ncommit2")
            elif command == "diff":
                # Return some of the files as new
                return (True, "\n".join(edge_case_files[:3]))
            return (True, "")
        
        self.mock_git_ops._run_git_command.side_effect = file_git_response

        # Test each edge case file
        for file_path in edge_case_files:
            commits = self.batch_ops.get_commits_touching_file(file_path)
            assert isinstance(commits, list)
            
            is_new = self.batch_ops.is_new_file(file_path)
            assert isinstance(is_new, bool)

    def test_cache_consistency_under_concurrent_modifications(self):
        """Test cache consistency when multiple threads modify the same data."""
        def git_response_with_delays(command, *args):
            # Simulate git commands that take time
            import time
            time.sleep(0.01)  # Small delay
            
            if command == "log":
                return (True, "commit1\ncommit2\ncommit3")
            elif command == "show":
                if "--format=%H|%h|%s|%an|%ct" in args:
                    return (True, "commit1|c1|Subject|Author|1234567890")
                elif "--format=%H %P" in args:
                    return (True, "commit1 parent1")
            return (True, "")
        
        self.mock_git_ops._run_git_command.side_effect = git_response_with_delays

        results = []
        
        def concurrent_worker():
            # Multiple operations on same file
            commits1 = self.batch_ops.get_commits_touching_file("test_file.py")
            commits2 = self.batch_ops.get_commits_touching_file("test_file.py")
            
            # Results should be consistent
            results.append((commits1, commits2))

        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(concurrent_worker) for _ in range(5)]
            for future in futures:
                future.result()

        # Verify all results are consistent
        for commits1, commits2 in results:
            assert commits1 == commits2

    def test_memory_cleanup_on_clear(self):
        """Test that clear operations properly clean up memory."""
        # Fill caches with data
        self.mock_git_ops._run_git_command.side_effect = [
            (True, "commit1\ncommit2"),  # branch commits
            (True, "commit1|c1|Subject|Author|1234567890"),  # basic info
            (True, "commit1 parent1"),  # parent info
            (True, "commit1\ncommit2"),  # file commits
            (True, "file1.py\nfile2.py")  # new files
        ]

        # Load data into caches
        self.batch_ops.get_branch_commits()
        self.batch_ops.batch_load_commit_info(["commit1"])
        self.batch_ops.get_commits_touching_file("test_file.py")
        self.batch_ops.is_new_file("test_file.py")

        # Verify caches have data
        stats_before = self.batch_ops.get_cache_stats()
        assert stats_before['size'] > 0 or stats_before['file_size'] > 0

        # Clear caches
        self.batch_ops.clear_caches()

        # Verify caches are empty
        stats_after = self.batch_ops.get_cache_stats()
        assert stats_after['size'] == 0
        assert stats_after['file_size'] == 0
        assert stats_after['new_files_cache_size'] == 0

    def test_large_repository_simulation(self):
        """Test behavior with large repository simulation."""
        # Simulate repository with many commits and files
        large_commit_count = 1000
        large_file_count = 200
        
        def large_repo_response(command, *args):
            if command == "rev-list":
                commits = [f"commit_{i:04d}" for i in range(large_commit_count)]
                return (True, "\n".join(commits))
            elif command == "show":
                if "--format=%H|%h|%s|%an|%ct" in args:
                    lines = []
                    for arg in args:
                        if arg.startswith("commit_"):
                            lines.append(f"{arg}|{arg[:7]}|Subject {arg}|Author|1234567890")
                    return (True, "\n".join(lines))
                elif "--format=%H %P" in args:
                    lines = []
                    for arg in args:
                        if arg.startswith("commit_"):
                            lines.append(f"{arg} parent1")
                    return (True, "\n".join(lines))
            elif command == "log":
                # Return commits for any file
                return (True, "commit_0001\ncommit_0002\ncommit_0003")
            elif command == "diff":
                files = [f"file_{i:03d}.py" for i in range(large_file_count)]
                return (True, "\n".join(files))
            return (True, "")
        
        self.mock_git_ops._run_git_command.side_effect = large_repo_response

        # Test that operations complete without errors or excessive memory usage
        commits = self.batch_ops.get_branch_commits()
        assert len(commits) == large_commit_count

        # Test batch loading with large commit set
        first_100_commits = commits[:100]
        commit_info = self.batch_ops.batch_load_commit_info(first_100_commits)
        assert len(commit_info) == 100

        # Verify caches maintain reasonable size limits
        stats = self.batch_ops.get_cache_stats()
        assert stats['size'] <= 500  # Should be bounded
        assert stats['file_size'] <= 200  # Should be bounded