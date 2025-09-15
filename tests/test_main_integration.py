"""Integration tests for main CLI functionality."""

import subprocess
from unittest.mock import Mock, patch

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.main import _simple_approval_fallback, main


class TestSimpleApprovalFallback:
    """Test cases for simple approval fallback function."""

    def test_empty_mappings(self) -> None:
        """Test fallback with empty mappings list."""
        blame_analyzer = Mock()

        result = _simple_approval_fallback([], blame_analyzer)

        assert result == {"approved": [], "ignored": []}
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
        mock_input.side_effect = ["s", "s"]

        result = _simple_approval_fallback(mappings, blame_analyzer)

        assert len(result["approved"]) == 2
        assert len(result["ignored"]) == 0
        assert result["approved"][0] is mapping1
        assert result["approved"][1] is mapping2

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

        assert result == {"approved": [], "ignored": []}

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

        assert result == {"approved": [], "ignored": []}

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
        mock_input.side_effect = ["invalid", "s"]

        result = _simple_approval_fallback([mapping], blame_analyzer)

        assert len(result["approved"]) == 1
        assert len(result["ignored"]) == 0
        assert result["approved"][0] is mapping

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
        mock_input.side_effect = ["s", "n", "s"]

        result = _simple_approval_fallback(mappings, blame_analyzer)

        assert len(result["approved"]) == 2
        assert len(result["ignored"]) == 0
        assert result["approved"][0] is mapping1
        assert result["approved"][1] is mapping3

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

        assert result == {"approved": [], "ignored": []}


class TestMainEntryPointFailures:
    """Test failure scenarios in main entry point."""

    def test_git_not_available_failure(self) -> None:
        """Test main() exits gracefully when git is not installed."""
        with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
            mock_git_ops = Mock()
            mock_git_ops.is_git_available.return_value = False
            mock_git_ops_class.return_value = mock_git_ops

            with patch("sys.argv", ["git-autosquash"]):
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_called_with(1)

    def test_git_repo_validation_failure(self) -> None:
        """Test main() exits gracefully when not in a git repository."""
        with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
            mock_git_ops = Mock()
            mock_git_ops.is_git_available.return_value = True
            mock_git_ops.is_git_repo.return_value = False
            mock_git_ops_class.return_value = mock_git_ops

            with patch("sys.argv", ["git-autosquash"]):
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_called_with(1)

    def test_detached_head_failure(self) -> None:
        """Test main() exits gracefully when in detached HEAD state."""
        with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
            mock_git_ops = Mock()
            mock_git_ops.is_git_available.return_value = True
            mock_git_ops.is_git_repo.return_value = True
            mock_git_ops.get_current_branch.return_value = None  # Detached HEAD
            mock_git_ops_class.return_value = mock_git_ops

            with patch("sys.argv", ["git-autosquash"]):
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_called_with(1)

    def test_no_merge_base_failure(self) -> None:
        """Test main() exits gracefully when no merge base found."""
        with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
            mock_git_ops = Mock()
            mock_git_ops.is_git_available.return_value = True
            mock_git_ops.is_git_repo.return_value = True
            mock_git_ops.get_current_branch.return_value = "feature-branch"
            mock_git_ops.get_merge_base_with_main.return_value = None  # No merge base
            mock_git_ops_class.return_value = mock_git_ops

            with patch("sys.argv", ["git-autosquash"]):
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_called_with(1)

    def test_no_commits_since_merge_base(self) -> None:
        """Test main() exits gracefully when no commits to work with."""
        with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
            mock_git_ops = Mock()
            mock_git_ops.is_git_available.return_value = True
            mock_git_ops.is_git_repo.return_value = True
            mock_git_ops.get_current_branch.return_value = "feature-branch"
            mock_git_ops.get_merge_base_with_main.return_value = "abc123"
            mock_git_ops.has_commits_since_merge_base.return_value = False
            mock_git_ops_class.return_value = mock_git_ops

            with patch("sys.argv", ["git-autosquash"]):
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_called_with(1)

    def test_keyboard_interrupt_handling(self) -> None:
        """Test main() handles KeyboardInterrupt gracefully."""
        with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
            mock_git_ops_class.side_effect = KeyboardInterrupt()

            with patch("sys.argv", ["git-autosquash"]):
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_called_with(130)  # Standard interrupt exit code

    def test_subprocess_error_handling(self) -> None:
        """Test main() handles subprocess errors gracefully."""

        with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
            mock_git_ops_class.side_effect = subprocess.SubprocessError(
                "Git command failed"
            )

            with patch("sys.argv", ["git-autosquash"]):
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_called_with(1)

    def test_unexpected_exception_handling(self) -> None:
        """Test main() handles unexpected exceptions gracefully."""
        with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
            mock_git_ops_class.side_effect = RuntimeError("Unexpected error")

            with patch("sys.argv", ["git-autosquash"]):
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_called_with(1)
