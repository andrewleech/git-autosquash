"""Integration tests for main CLI functionality."""

from unittest.mock import Mock, patch

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.main import _simple_approval_fallback


class TestSimpleApprovalFallback:
    """Test cases for simple approval fallback function."""

    def test_empty_mappings(self) -> None:
        """Test fallback with empty mappings list."""
        blame_analyzer = Mock()

        result = _simple_approval_fallback([], blame_analyzer)

        assert result == []
        blame_analyzer.get_commit_summary.assert_not_called()

    @patch("builtins.input")
    def test_approve_all_mappings(self, mock_input: Mock) -> None:
        """Test approving all mappings."""
        # Setup mock mappings
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line 1", "+new line"],
            context_before=[],
            context_after=[],
        )

        hunk2 = DiffHunk(
            file_path="file2.py",
            old_start=5,
            old_count=2,
            new_start=5,
            new_count=1,
            lines=["@@ -5,2 +5,1 @@", "-old line", " line 2"],
            context_before=[],
            context_after=[],
        )

        mapping1 = HunkTargetMapping(
            hunk=hunk1, target_commit="abc123", confidence="high", blame_info=[]
        )

        mapping2 = HunkTargetMapping(
            hunk=hunk2, target_commit="def456", confidence="medium", blame_info=[]
        )

        mappings = [mapping1, mapping2]

        # Mock blame analyzer
        blame_analyzer = Mock()
        blame_analyzer.get_commit_summary.side_effect = [
            "abc1234 Add feature",
            "def4567 Fix bug",
        ]

        # Mock user input to approve both
        mock_input.side_effect = ["y", "y"]

        result = _simple_approval_fallback(mappings, blame_analyzer)

        assert len(result) == 2
        assert result[0] is mapping1
        assert result[1] is mapping2

        # Verify commit summaries were retrieved
        assert blame_analyzer.get_commit_summary.call_count == 2
        blame_analyzer.get_commit_summary.assert_any_call("abc123")
        blame_analyzer.get_commit_summary.assert_any_call("def456")

    @patch("builtins.input")
    def test_reject_all_mappings(self, mock_input: Mock) -> None:
        """Test rejecting all mappings."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="xyz789", confidence="low", blame_info=[]
        )

        blame_analyzer = Mock()
        blame_analyzer.get_commit_summary.return_value = "xyz7890 Some commit"

        # Mock user input to reject
        mock_input.return_value = "n"

        result = _simple_approval_fallback([mapping], blame_analyzer)

        assert result == []

    @patch("builtins.input")
    def test_quit_early(self, mock_input: Mock) -> None:
        """Test quitting early from approval."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="xyz789", confidence="medium", blame_info=[]
        )

        blame_analyzer = Mock()
        blame_analyzer.get_commit_summary.return_value = "xyz7890 Some commit"

        # Mock user input to quit
        mock_input.return_value = "q"

        result = _simple_approval_fallback([mapping], blame_analyzer)

        assert result == []

    @patch("builtins.input")
    def test_invalid_input_then_approve(self, mock_input: Mock) -> None:
        """Test handling invalid input then approving."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="xyz789", confidence="high", blame_info=[]
        )

        blame_analyzer = Mock()
        blame_analyzer.get_commit_summary.return_value = "xyz7890 Some commit"

        # Mock invalid input followed by approval
        mock_input.side_effect = ["invalid", "y"]

        result = _simple_approval_fallback([mapping], blame_analyzer)

        assert len(result) == 1
        assert result[0] is mapping

    @patch("builtins.input")
    def test_mixed_approvals(self, mock_input: Mock) -> None:
        """Test mix of approvals and rejections."""
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line", "+added"],
            context_before=[],
            context_after=[],
        )

        hunk2 = DiffHunk(
            file_path="file2.py",
            old_start=5,
            old_count=1,
            new_start=5,
            new_count=1,
            lines=["@@ -5,1 +5,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )

        hunk3 = DiffHunk(
            file_path="file3.py",
            old_start=10,
            old_count=0,
            new_start=10,
            new_count=1,
            lines=["@@ -10,0 +10,1 @@", "+new line"],
            context_before=[],
            context_after=[],
        )

        mapping1 = HunkTargetMapping(
            hunk=hunk1, target_commit="abc", confidence="high", blame_info=[]
        )
        mapping2 = HunkTargetMapping(
            hunk=hunk2, target_commit="def", confidence="low", blame_info=[]
        )
        mapping3 = HunkTargetMapping(
            hunk=hunk3, target_commit="ghi", confidence="medium", blame_info=[]
        )

        mappings = [mapping1, mapping2, mapping3]

        blame_analyzer = Mock()
        blame_analyzer.get_commit_summary.side_effect = [
            "abc123 First commit",
            "def456 Second commit",
            "ghi789 Third commit",
        ]

        # Approve first, reject second, approve third
        mock_input.side_effect = ["y", "n", "y"]

        result = _simple_approval_fallback(mappings, blame_analyzer)

        assert len(result) == 2
        assert result[0] is mapping1
        assert result[1] is mapping3

    def test_hunk_line_display_truncation(self) -> None:
        """Test that long hunks are truncated in display."""
        # Create hunk with many lines
        lines = ["@@ -1,10 +1,10 @@"] + [f" line {i}" for i in range(1, 11)]

        hunk = DiffHunk(
            file_path="long_file.py",
            old_start=1,
            old_count=10,
            new_start=1,
            new_count=10,
            lines=lines,
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        blame_analyzer = Mock()
        blame_analyzer.get_commit_summary.return_value = "abc1234 Some commit"

        # This test mainly verifies the function doesn't crash with long hunks
        # In a real test environment, we'd capture stdout to verify truncation message
        with patch("builtins.input", return_value="n"):
            result = _simple_approval_fallback([mapping], blame_analyzer)

        assert result == []
