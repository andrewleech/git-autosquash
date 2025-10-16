"""Tests for hunk target resolver edge cases and error handling."""

from unittest.mock import MagicMock


from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.hunk_target_resolver import (
    HunkTargetResolver,
    BlameAnalysisEngine,
    FallbackTargetProvider,
    FileConsistencyTracker,
    TargetingMethod,
)


class TestBlameAnalysisEngineEdgeCases:
    """Test edge cases in blame analysis engine."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_git_ops = MagicMock(spec=GitOps)
        mock_merge_base = "abc123"
        self.engine = BlameAnalysisEngine(self.mock_git_ops, mock_merge_base)

    def test_empty_blame_output_handling(self):
        """Test handling of empty blame output."""
        self.mock_git_ops._run_git_command.return_value = (True, "")

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        result = self.engine.get_blame_for_old_lines(hunk)
        assert result == []

    def test_malformed_blame_output_handling(self):
        """Test handling of malformed blame output."""
        malformed_outputs = [
            "incomplete line without proper format",
            "abc123 (Author incomplete",
            "abc123 (Author 2023-01-01 12:00:00 +0000",  # Missing line number
            "",  # Empty
            "   ",  # Only whitespace
        ]

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        for malformed_output in malformed_outputs:
            self.mock_git_ops._run_git_command.return_value = (True, malformed_output)
            result = self.engine.get_blame_for_old_lines(hunk)
            # Should handle gracefully without exceptions
            assert isinstance(result, list)

    def test_unicode_in_blame_output(self):
        """Test handling of unicode characters in blame output (porcelain format)."""
        # Git blame --porcelain format with unicode
        unicode_blame = """abc123def456789012345678901234567890abcd 1 1 1
author Tëst Üser
author-mail <test@example.com>
author-time 1640995200
author-tz +0000
committer Tëst Üser
committer-mail <test@example.com>
committer-time 1640995200
committer-tz +0000
summary Test commit
filename test.py
\tprint('Hëllo Wörld with émojis 🚀')"""

        self.mock_git_ops._run_git_command.return_value = (True, unicode_blame)

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        result = self.engine.get_blame_for_old_lines(hunk)
        assert len(result) == 1
        assert result[0].author == "Tëst Üser"
        assert "émojis 🚀" in result[0].line_content

    def test_blame_with_unusual_line_numbers(self):
        """Test blame parsing with unusual line number scenarios (porcelain format)."""
        # Very high line numbers in porcelain format
        high_line_blame = """abc123def456789012345678901234567890abcd 99999 99999 1
author Author Name
author-mail <author@example.com>
author-time 1672574400
author-tz +0000
committer Author Name
committer-mail <author@example.com>
committer-time 1672574400
committer-tz +0000
summary Test commit with high line number
filename test.py
\tline content at very high line number"""

        self.mock_git_ops._run_git_command.return_value = (True, high_line_blame)

        hunk = DiffHunk(
            file_path="test.py",
            old_start=99999,
            old_count=1,
            new_start=99999,
            new_count=1,
            lines=["@@ -99999,1 +99999,1 @@", "-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        result = self.engine.get_blame_for_old_lines(hunk)
        assert len(result) == 1
        assert result[0].line_number == 99999

    def test_git_command_failure_in_blame(self):
        """Test git command failure scenarios in blame analysis."""
        self.mock_git_ops._run_git_command.return_value = (
            False,
            "fatal: file not found",
        )

        hunk = DiffHunk(
            file_path="nonexistent.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        result = self.engine.get_blame_for_old_lines(hunk)
        assert result == []

    def test_context_blame_edge_cases(self):
        """Test edge cases in context blame analysis (porcelain format)."""
        # Test hunk at beginning of file with porcelain format
        hunk_at_start = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=0,
            new_start=1,
            new_count=1,
            lines=["@@ -1,0 +1,1 @@", "+new first line"],
            context_before=[],
            context_after=[],
        )

        porcelain_blame = """abc123def456789012345678901234567890abcd 1 1 1
author Author Name
author-mail <author@example.com>
author-time 1672574400
author-tz +0000
committer Author Name
committer-mail <author@example.com>
committer-time 1672574400
committer-tz +0000
summary Test commit at file start
filename test.py
\texisting line"""

        self.mock_git_ops._run_git_command.return_value = (True, porcelain_blame)

        result = self.engine.get_blame_for_context(hunk_at_start)
        assert len(result) == 1

        # Test very large line numbers for context with porcelain format
        hunk_large_lines = DiffHunk(
            file_path="test.py",
            old_start=1000000,
            old_count=0,
            new_start=1000000,
            new_count=1,
            lines=["@@ -1000000,0 +1000000,1 @@", "+new line"],
            context_before=[],
            context_after=[],
        )

        large_line_blame = """abc123def456789012345678901234567890abcd 1000000 1000000 1
author Author Name
author-mail <author@example.com>
author-time 1672574400
author-tz +0000
committer Author Name
committer-mail <author@example.com>
committer-time 1672574400
committer-tz +0000
summary Test commit with very large line number
filename test.py
\tline at 1000000"""

        self.mock_git_ops._run_git_command.return_value = (True, large_line_blame)

        result = self.engine.get_blame_for_context(hunk_large_lines)
        # Should handle without exceptions
        assert isinstance(result, list)


class TestFileConsistencyTrackerEdgeCases:
    """Test edge cases in file consistency tracking."""

    def test_file_path_edge_cases(self):
        """Test edge cases with file paths."""
        tracker = FileConsistencyTracker()

        edge_case_paths = [
            "file with spaces.py",
            "filé-with-unicode.py",
            "very/deep/nested/path/file.py",
            ".hidden_file",
            "file.with.many.dots.py",
            "",  # Empty string
            "a" * 1000,  # Very long path
        ]

        for i, path in enumerate(edge_case_paths):
            commit = f"commit_{i}"
            tracker.set_target_for_file(path, commit)
            assert tracker.get_consistent_target(path) == commit

    def test_consistency_with_none_values(self):
        """Test consistency tracking with None values."""
        tracker = FileConsistencyTracker()

        # Should handle None gracefully
        assert tracker.get_consistent_target("nonexistent.py") is None

    def test_overwrite_consistency(self):
        """Test overwriting consistency targets."""
        tracker = FileConsistencyTracker()

        tracker.set_target_for_file("test.py", "commit1")
        assert tracker.get_consistent_target("test.py") == "commit1"

        # Overwrite with new target
        tracker.set_target_for_file("test.py", "commit2")
        assert tracker.get_consistent_target("test.py") == "commit2"


class TestFallbackTargetProviderEdgeCases:
    """Test edge cases in fallback target provider."""

    def setup_method(self):
        """Setup test fixtures."""
        from git_autosquash.batch_git_ops import BatchGitOperations
        from git_autosquash.squash_context import SquashContext

        self.mock_git_ops = MagicMock(spec=GitOps)
        self.batch_ops = MagicMock(spec=BatchGitOperations)
        self.mock_context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )
        self.provider = FallbackTargetProvider(
            self.batch_ops, context=self.mock_context
        )

    def test_empty_branch_commits(self):
        """Test fallback provider with empty branch commits."""
        self.batch_ops.get_branch_commits.return_value = []
        self.batch_ops.get_ordered_commits_by_recency.return_value = []
        self.batch_ops.get_file_relevant_commits.return_value = ([], [])

        result = self.provider.get_fallback_candidates(
            "test.py", TargetingMethod.FALLBACK_NEW_FILE
        )
        assert result == []

    def test_fallback_with_file_relevance_no_matches(self):
        """Test fallback when no commits touched the file."""
        self.batch_ops.get_branch_commits.return_value = ["commit1", "commit2"]
        self.batch_ops.get_file_relevant_commits.return_value = (
            [],
            [],
        )  # No file-relevant commits

        result = self.provider.get_fallback_candidates(
            "untouched_file.py", TargetingMethod.FALLBACK_EXISTING_FILE
        )
        # Should still return something (the "other" commits)
        assert isinstance(result, list)

    def test_unknown_targeting_method(self):
        """Test fallback provider with unknown targeting method."""
        self.batch_ops.get_branch_commits.return_value = ["commit1", "commit2"]
        self.batch_ops.get_ordered_commits_by_recency.return_value = [
            MagicMock(commit_hash="commit1"),
            MagicMock(commit_hash="commit2"),
        ]

        # Use invalid enum value (simulate future enum addition)
        unknown_method = "unknown_method"

        result = self.provider.get_fallback_candidates("test.py", unknown_method)
        # Should fall back to default behavior
        assert len(result) == 2


class TestHunkTargetResolverIntegrationEdgeCases:
    """Test edge cases in the full hunk target resolver integration."""

    def setup_method(self):
        """Setup test fixtures."""
        from git_autosquash.squash_context import SquashContext

        self.mock_git_ops = MagicMock(spec=GitOps)
        self.merge_base = "main"
        self.mock_context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )
        self.resolver = HunkTargetResolver(
            self.mock_git_ops, self.merge_base, context=self.mock_context
        )

    def test_resolve_empty_hunk_list(self):
        """Test resolving empty hunk list."""
        result = self.resolver.resolve_targets([])
        assert result == []

    def test_resolve_hunk_with_git_failures(self):
        """Test resolving hunks when git operations fail."""
        # Mock all git operations to fail
        self.mock_git_ops._run_git_command.return_value = (False, "git error")

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        result = self.resolver.resolve_targets([hunk])

        # Should handle gracefully and create fallback mapping
        assert len(result) == 1
        mapping = result[0]
        assert mapping.needs_user_selection is True
        assert mapping.targeting_method in [
            TargetingMethod.FALLBACK_NEW_FILE,
            TargetingMethod.FALLBACK_EXISTING_FILE,
        ]

    def test_resolve_with_partial_blame_success(self):
        """Test resolution with partial blame analysis success."""

        # Mock new files check to fail, but blame to partially succeed
        def mock_git_response(command, *args):
            if command == "diff" and "--diff-filter=A" in args:
                return (False, "error checking new files")
            elif command == "blame":
                return (
                    True,
                    "abc123 (Author 2023-01-01 12:00:00 +0000    1) some line",
                )
            elif command == "rev-list":
                return (True, "abc123\ndef456")
            return (False, "default error")

        self.mock_git_ops._run_git_command.side_effect = mock_git_response

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        result = self.resolver.resolve_targets([hunk])
        assert len(result) == 1

    def test_blame_consensus_edge_cases(self):
        """Test edge cases in blame consensus analysis."""

        # Mock git operations for blame consensus
        def mock_git_response(command, *args):
            if command == "diff" and "--diff-filter=A" in args:
                return (True, "")  # Not a new file
            elif command == "blame":
                # Return blame with equal vote counts to test tie-breaking
                return (
                    True,
                    "commit1 (Author1 2023-01-01 12:00:00 +0000    1) line 1\n"
                    "commit2 (Author2 2023-01-02 12:00:00 +0000    2) line 2",
                )
            elif command == "rev-list":
                return (True, "commit1\ncommit2")
            elif command == "show":
                if "commit1" in args:
                    return (
                        True,
                        "commit1|c1|Subject 1|Author|1640995200",
                    )  # Earlier timestamp
                elif "commit2" in args:
                    return (
                        True,
                        "commit2|c2|Subject 2|Author|1641081600",
                    )  # Later timestamp
            return (False, "default error")

        self.mock_git_ops._run_git_command.side_effect = mock_git_response

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=2,
            new_start=1,
            new_count=2,
            lines=[
                "@@ -1,2 +1,2 @@",
                "-old line 1",
                "-old line 2",
                "+new line 1",
                "+new line 2",
            ],
            context_before=[],
            context_after=[],
        )

        result = self.resolver.resolve_targets([hunk])

        # Should break tie by recency (commit2 has later timestamp)
        assert len(result) == 1
        mapping = result[0]
        if not mapping.needs_user_selection:
            assert mapping.target_commit == "commit2"  # More recent commit wins tie

    def test_very_large_hunk_processing(self):
        """Test processing very large hunks."""
        # Create hunk with many lines
        large_hunk_lines = ["@@ -1,1000 +1,1000 @@"]
        for i in range(500):
            large_hunk_lines.append(f"-old line {i}")
            large_hunk_lines.append(f"+new line {i}")

        large_hunk = DiffHunk(
            file_path="large_file.py",
            old_start=1,
            old_count=1000,
            new_start=1,
            new_count=1000,
            lines=large_hunk_lines,
            context_before=[],
            context_after=[],
        )

        # Mock git to return successful blame
        def mock_large_response(command, *args):
            if command == "blame":
                # Generate blame for large line range
                blame_lines = []
                for i in range(1, 1001):
                    blame_lines.append(
                        f"commit1 (Author 2023-01-01 12:00:00 +0000 {i}) line {i}"
                    )
                return (True, "\n".join(blame_lines))
            elif command == "diff" and "--diff-filter=A" in args:
                return (True, "")  # Not new file
            elif command == "rev-list":
                return (True, "commit1")
            return (False, "error")

        self.mock_git_ops._run_git_command.side_effect = mock_large_response

        result = self.resolver.resolve_targets([large_hunk])

        # Should handle large hunk without issues
        assert len(result) == 1

    def test_concurrent_resolution_consistency(self):
        """Test that concurrent resolution produces consistent results."""
        from concurrent.futures import ThreadPoolExecutor

        # Mock stable git responses
        def stable_git_response(command, *args):
            if command == "diff" and "--diff-filter=A" in args:
                return (True, "")
            elif command == "blame":
                return (
                    True,
                    "commit1 (Author 2023-01-01 12:00:00 +0000    1) stable line",
                )
            elif command == "rev-list":
                return (True, "commit1\ncommit2")
            return (False, "error")

        self.mock_git_ops._run_git_command.side_effect = stable_git_response

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        results = []

        def worker():
            result = self.resolver.resolve_targets([hunk])
            results.append(result)

        # Run concurrent resolutions
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(worker) for _ in range(5)]
            for future in futures:
                future.result()

        # All results should be consistent
        first_result = results[0]
        for result in results[1:]:
            assert len(result) == len(first_result)
            for i, mapping in enumerate(result):
                first_mapping = first_result[i]
                assert mapping.target_commit == first_mapping.target_commit
                assert (
                    mapping.needs_user_selection == first_mapping.needs_user_selection
                )

    def test_get_commit_summary_edge_cases(self):
        """Test edge cases in commit summary retrieval."""
        # Test with invalid commit hash
        self.mock_git_ops._run_git_command.return_value = (False, "invalid commit")

        summary = self.resolver.get_commit_summary("invalid_hash")
        assert summary == "invalid_"  # Should return truncated hash

        # Test with valid commit
        self.mock_git_ops._run_git_command.return_value = (
            True,
            "abc123|abc|Test Subject|Author|1234567890",
        )

        summary = self.resolver.get_commit_summary("abc123")
        assert "Test Subject" in summary

    def test_cache_clearing_edge_cases(self):
        """Test cache clearing under various conditions."""
        # Fill caches with some data first
        self.mock_git_ops._run_git_command.return_value = (True, "commit1")

        # Should not raise exceptions even if caches are empty or partially filled
        self.resolver.clear_caches()

        # Should be safe to call multiple times
        self.resolver.clear_caches()
        self.resolver.clear_caches()
