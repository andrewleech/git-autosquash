"""Test cases for contextual blame scanning functionality."""

import pytest
from unittest.mock import Mock, patch

from git_autosquash.blame_analyzer import BlameAnalyzer, BlameInfo, TargetingMethod
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.git_ops import GitOps


class TestContextualBlame:
    """Test contextual blame scanning when direct blame fails."""

    @pytest.fixture
    def mock_git_ops(self):
        """Mock GitOps for testing."""
        git_ops = Mock(spec=GitOps)
        return git_ops

    @pytest.fixture
    def blame_analyzer(self, mock_git_ops):
        """Create BlameAnalyzer instance for testing."""
        return BlameAnalyzer(mock_git_ops, "merge-base-hash")

    def test_contextual_lines_detection(self, blame_analyzer):
        """Test detection of meaningful context lines around a hunk."""
        # Create a test hunk (modification)
        hunk = DiffHunk(
            file_path="test.c",
            old_start=10,
            old_count=1,
            new_start=10,
            new_count=1,
            lines=["-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        # Mock file content with meaningful lines around the hunk
        # Need at least 11 lines since we're looking for context around line 10
        file_content = """line 1
line 2
line 3
line 4
line 5
line 6
line 7
line 8
// Comment above target
#define TARGET_LINE value
// Comment below target"""

        blame_analyzer.git_ops._run_git_command.return_value = (True, file_content)

        # Test getting contextual lines
        context_lines = blame_analyzer._get_contextual_lines_for_hunk(
            hunk, context_lines=1
        )

        # Should find lines 9, 10, and 11 (meaningful lines around the modification)
        expected_lines = [9, 10, 11]  # Lines with meaningful content
        assert context_lines == expected_lines

    def test_filter_meaningful_lines_excludes_whitespace(self, blame_analyzer):
        """Test that whitespace-only lines are filtered out."""
        file_content = """meaningful line 1

    
meaningful line 4
   
meaningful line 6"""

        blame_analyzer.git_ops._run_git_command.return_value = (True, file_content)

        # Test with lines 1-6
        line_numbers = [1, 2, 3, 4, 5, 6]
        meaningful_lines = blame_analyzer._filter_meaningful_lines(
            "test.c", line_numbers
        )

        # Should only return lines with non-whitespace content
        assert meaningful_lines == [1, 4, 6]

    def test_contextual_blame_fallback_success(self, blame_analyzer):
        """Test successful contextual blame when direct blame fails."""
        # Create a test hunk
        hunk = DiffHunk(
            file_path="test.c",
            old_start=10,
            old_count=1,
            new_start=10,
            new_count=1,
            lines=["-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        # Mock the necessary methods
        with (
            patch.object(blame_analyzer, "_is_new_file", return_value=False),
            patch.object(blame_analyzer, "_get_blame_for_old_lines", return_value=[]),
            patch.object(
                blame_analyzer,
                "_get_branch_commits",
                return_value={"commit123", "commit456"},
            ),
            patch.object(
                blame_analyzer, "_get_contextual_blame"
            ) as mock_contextual_blame,
            patch.object(
                blame_analyzer, "_create_contextual_mapping"
            ) as mock_create_contextual,
        ):
            # Mock contextual blame returning results
            contextual_blame_info = [
                BlameInfo("commit123", "author", "2024-01-01", 9, "// Comment above"),
                BlameInfo("commit123", "author", "2024-01-01", 11, "// Comment below"),
            ]
            mock_contextual_blame.return_value = contextual_blame_info

            # Mock the contextual mapping creation
            expected_mapping = Mock()
            mock_create_contextual.return_value = expected_mapping

            # Analyze the hunk
            result = blame_analyzer._analyze_single_hunk(hunk)

            # Should have tried contextual blame and created contextual mapping
            mock_contextual_blame.assert_called_once_with(hunk)
            mock_create_contextual.assert_called_once()
            assert result == expected_mapping

    def test_contextual_blame_with_branch_filtering(self, blame_analyzer):
        """Test that contextual blame filters to branch commits only."""
        # Create a test hunk
        hunk = DiffHunk(
            file_path="test.c",
            old_start=10,
            old_count=1,
            new_start=10,
            new_count=1,
            lines=["-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        # Mock contextual blame info with mixed commits
        contextual_blame_info = [
            BlameInfo("branch_commit", "author", "2024-01-01", 9, "// Comment above"),
            BlameInfo("other_commit", "author", "2024-01-01", 11, "// Comment below"),
        ]

        branch_commits = {"branch_commit"}

        with (
            patch.object(blame_analyzer, "_is_new_file", return_value=False),
            patch.object(blame_analyzer, "_get_blame_for_old_lines", return_value=[]),
            patch.object(
                blame_analyzer, "_get_branch_commits", return_value=branch_commits
            ),
            patch.object(
                blame_analyzer,
                "_get_contextual_blame",
                return_value=contextual_blame_info,
            ),
            patch.object(
                blame_analyzer, "_create_contextual_mapping"
            ) as mock_create_contextual,
        ):
            blame_analyzer._analyze_single_hunk(hunk)

            # Should have called contextual mapping with only branch commits
            mock_create_contextual.assert_called_once()
            call_args = mock_create_contextual.call_args
            filtered_blame = call_args[0][1]  # Second argument is the blame list

            # Only branch_commit should remain after filtering
            assert len(filtered_blame) == 1
            assert filtered_blame[0].commit_hash == "branch_commit"

    def test_contextual_mapping_confidence_levels(self, blame_analyzer):
        """Test that contextual mappings have appropriate confidence levels."""
        hunk = Mock()
        hunk.file_path = "test.c"

        # Test high confidence contextual match (but reduced to medium)
        contextual_blame = [
            BlameInfo("commit123", "author", "2024-01-01", 9, "line1"),
            BlameInfo("commit123", "author", "2024-01-01", 10, "line2"),
            BlameInfo("commit123", "author", "2024-01-01", 11, "line3"),
            BlameInfo("commit123", "author", "2024-01-01", 12, "line4"),
            BlameInfo("commit123", "author", "2024-01-01", 13, "line5"),
        ]

        with patch.object(
            blame_analyzer, "_get_commit_timestamp", return_value=1234567890
        ):
            result = blame_analyzer._create_contextual_mapping(hunk, contextual_blame)

            # Contextual matches should have reduced confidence
            assert result.confidence == "medium"  # Even 100% match is reduced
            assert result.targeting_method == TargetingMethod.CONTEXTUAL_BLAME_MATCH
            assert result.target_commit == "commit123"

    def test_fallback_to_user_selection_when_no_context(self, blame_analyzer):
        """Test fallback to user selection when contextual blame also fails."""
        hunk = DiffHunk(
            file_path="test.c",
            old_start=10,
            old_count=1,
            new_start=10,
            new_count=1,
            lines=["-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        with (
            patch.object(blame_analyzer, "_is_new_file", return_value=False),
            patch.object(blame_analyzer, "_get_blame_for_old_lines", return_value=[]),
            patch.object(
                blame_analyzer, "_get_branch_commits", return_value={"commit123"}
            ),
            patch.object(blame_analyzer, "_get_contextual_blame", return_value=[]),
            patch.object(
                blame_analyzer, "_create_fallback_mapping"
            ) as mock_create_fallback,
        ):
            expected_fallback = Mock()
            mock_create_fallback.return_value = expected_fallback

            result = blame_analyzer._analyze_single_hunk(hunk)

            # Should fall back to user selection
            # The API changed - blame_info is now optional
            mock_create_fallback.assert_called_once_with(
                hunk, TargetingMethod.FALLBACK_EXISTING_FILE
            )
            assert result == expected_fallback
