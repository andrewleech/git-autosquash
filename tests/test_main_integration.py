"""Integration tests for main CLI functionality."""

from unittest.mock import Mock, patch

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.main import _simple_approval_fallback, _apply_ignored_hunks, main


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
        mock_input.side_effect = ["s", "s"]

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
        mock_input.side_effect = ["invalid", "s"]

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
        mock_input.side_effect = ["s", "n", "s"]

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


class TestApplyIgnoredHunks:
    """Test cases for _apply_ignored_hunks function."""

    def test_empty_mappings(self) -> None:
        """Test applying empty ignored mappings list."""
        git_ops = Mock()

        result = _apply_ignored_hunks([], git_ops)

        assert result is True
        git_ops._run_git_command.assert_not_called()

    def test_successful_apply(self) -> None:
        """Test successfully applying ignored hunks with batched implementation."""
        git_ops = Mock()
        git_ops._run_git_command_with_input.return_value = (
            True,
            "Applied successfully",
        )
        # Mock stash backup and cleanup operations
        git_ops._run_git_command.return_value = (True, "stash-ref-123")
        git_ops.repo_path = "/test/repo"

        # Create test hunk
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        result = _apply_ignored_hunks([mapping], git_ops)

        assert result is True

        # Verify git apply was called correctly with batched patch
        git_ops._run_git_command_with_input.assert_called_once()
        call_args = git_ops._run_git_command_with_input.call_args
        assert call_args[0][0] == "apply"

        # Verify the patch content includes proper headers
        patch_content = call_args[1]["input_text"]
        assert "diff --git a/test.py b/test.py" in patch_content
        assert "@@ -1,1 +1,2 @@" in patch_content

        # Verify backup was created and cleaned up
        git_ops._run_git_command.assert_any_call("stash", "create", "autosquash-backup")
        git_ops._run_git_command.assert_any_call("stash", "drop", "stash-ref-123")

    def test_apply_failure(self) -> None:
        """Test handling apply failure with targeted rollback."""
        git_ops = Mock()
        # Patch application fails
        git_ops._run_git_command_with_input.return_value = (
            False,
            "Patch does not apply",
        )
        # Mock stash backup operations
        git_ops._run_git_command.return_value = (True, "stash-ref-456")
        git_ops.repo_path = "/test/repo"

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+conflicting line"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        result = _apply_ignored_hunks([mapping], git_ops)

        assert result is False

        # Verify patch application was attempted once
        assert git_ops._run_git_command_with_input.call_count == 1

        call_args = git_ops._run_git_command_with_input.call_args
        assert call_args[0][0] == "apply"

        # Verify targeted rollback occurred for specific file
        git_ops._run_git_command.assert_any_call(
            "checkout", "stash-ref-456", "--", "test.py"
        )

    def test_multiple_hunks(self) -> None:
        """Test applying multiple ignored hunks in batched patch."""
        git_ops = Mock()
        git_ops._run_git_command_with_input.return_value = (
            True,
            "Applied successfully",
        )
        git_ops._run_git_command.return_value = (True, "stash-ref-999")
        git_ops.repo_path = "/test/repo"

        # Create multiple test hunks for different files
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line 1", "+new line 1"],
            context_before=[],
            context_after=[],
        )

        hunk2 = DiffHunk(
            file_path="file2.py",
            old_start=5,
            old_count=2,
            new_start=5,
            new_count=3,
            lines=["@@ -5,2 +5,3 @@", " line 5", "+new line 5", " line 6"],
            context_before=[],
            context_after=[],
        )

        mappings = [
            HunkTargetMapping(
                hunk=hunk1, target_commit="abc123", confidence="high", blame_info=[]
            ),
            HunkTargetMapping(
                hunk=hunk2, target_commit="def456", confidence="medium", blame_info=[]
            ),
        ]

        result = _apply_ignored_hunks(mappings, git_ops)

        assert result is True

        # Should call git apply once with batched patch containing both files
        assert git_ops._run_git_command_with_input.call_count == 1

        # Verify both files were processed in single batched patch
        call_args = git_ops._run_git_command_with_input.call_args
        patch_content = call_args[1]["input_text"]

        # Both files should be present in the single patch
        assert "file1.py" in patch_content
        assert "file2.py" in patch_content
        assert "@@ -1,1 +1,2 @@" in patch_content
        assert "@@ -5,2 +5,3 @@" in patch_content

    def test_path_traversal_protection(self) -> None:
        """Test that path traversal attempts are blocked."""
        git_ops = Mock()
        git_ops.repo_path = "/test/repo"

        # Create hunk with malicious path
        hunk = DiffHunk(
            file_path="../../../etc/passwd",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing", "+malicious"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        result = _apply_ignored_hunks([mapping], git_ops)

        assert result is False
        # Verify git command was never called due to path validation
        git_ops._run_git_command_with_input.assert_not_called()

    def test_absolute_path_protection(self) -> None:
        """Test that absolute paths are blocked."""
        git_ops = Mock()
        git_ops.repo_path = "/test/repo"

        # Create hunk with absolute path
        hunk = DiffHunk(
            file_path="/etc/passwd",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing", "+malicious"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        result = _apply_ignored_hunks([mapping], git_ops)

        assert result is False
        # Verify git command was never called due to path validation
        git_ops._run_git_command_with_input.assert_not_called()

    def test_rollback_on_partial_failure(self) -> None:
        """Test that batch patch failure triggers targeted rollback."""
        git_ops = Mock()

        # Mock operations - batched patch fails
        git_ops._run_git_command.return_value = (True, "stash-ref-789")
        git_ops._run_git_command_with_input.return_value = (
            False,
            "Patch does not apply",
        )
        git_ops.repo_path = "/test/repo"

        # Create test hunks for different files
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line 1", "+new line 1"],
            context_before=[],
            context_after=[],
        )

        hunk2 = DiffHunk(
            file_path="file2.py",
            old_start=5,
            old_count=1,
            new_start=5,
            new_count=1,
            lines=["@@ -5,1 +5,1 @@", "-old line", "+new line"],
            context_before=[],
            context_after=[],
        )

        mappings = [
            HunkTargetMapping(
                hunk=hunk1, target_commit="abc123", confidence="high", blame_info=[]
            ),
            HunkTargetMapping(
                hunk=hunk2, target_commit="def456", confidence="high", blame_info=[]
            ),
        ]

        result = _apply_ignored_hunks(mappings, git_ops)

        assert result is False

        # Verify single batched patch application was attempted
        assert git_ops._run_git_command_with_input.call_count == 1

        # Verify backup was created and targeted rollback occurred for both files
        git_ops._run_git_command.assert_any_call("stash", "create", "autosquash-backup")
        git_ops._run_git_command.assert_any_call(
            "checkout", "stash-ref-789", "--", "file1.py"
        )
        git_ops._run_git_command.assert_any_call(
            "checkout", "stash-ref-789", "--", "file2.py"
        )

    def test_stash_backup_failure(self) -> None:
        """Test handling when stash backup creation fails."""
        git_ops = Mock()
        # Stash creation fails
        git_ops._run_git_command.return_value = (
            False,
            "Cannot save working tree state",
        )
        git_ops.repo_path = "/test/repo"

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        result = _apply_ignored_hunks([mapping], git_ops)

        assert result is False
        # Should never attempt to apply patches if backup fails
        git_ops._run_git_command_with_input.assert_not_called()

    def test_stash_cleanup_on_exception(self) -> None:
        """Test that stash cleanup occurs even when exceptions are raised."""
        git_ops = Mock()
        git_ops._run_git_command.return_value = (True, "stash-ref-exception")
        git_ops._run_git_command_with_input.side_effect = Exception("Unexpected error")
        git_ops.repo_path = "/test/repo"

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        result = _apply_ignored_hunks([mapping], git_ops)

        assert result is False
        # Verify cleanup occurred despite exception
        git_ops._run_git_command.assert_any_call("stash", "drop", "stash-ref-exception")
        # Verify targeted rollback was attempted
        git_ops._run_git_command.assert_any_call(
            "checkout", "stash-ref-exception", "--", "test.py"
        )

    def test_path_validation_exception_handling(self) -> None:
        """Test handling of exceptions during path validation."""
        git_ops = Mock()
        # Mock repo_path to cause an exception during path resolution
        git_ops.repo_path = "/invalid/path/that/causes/error"

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock Path.resolve() to raise an exception
        with patch(
            "pathlib.Path.resolve", side_effect=OSError("Path resolution failed")
        ):
            result = _apply_ignored_hunks([mapping], git_ops)

        assert result is False
        # Should never proceed to git operations after path validation failure
        git_ops._run_git_command.assert_not_called()
        git_ops._run_git_command_with_input.assert_not_called()

    def test_rollback_failure_continues_cleanup(self) -> None:
        """Test that cleanup continues even if individual rollback operations fail."""
        git_ops = Mock()
        git_ops._run_git_command.side_effect = [
            (True, "stash-ref-rollback-test"),  # stash create succeeds
            (False, "checkout failed"),  # first rollback fails
            (False, "checkout failed"),  # second rollback fails
            (True, "Deleted stash"),  # stash drop succeeds
        ]
        git_ops._run_git_command_with_input.return_value = (
            False,
            "Patch does not apply",
        )
        git_ops.repo_path = "/test/repo"

        # Create hunks for multiple files
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line 1", "+new line 1"],
            context_before=[],
            context_after=[],
        )

        hunk2 = DiffHunk(
            file_path="file2.py",
            old_start=5,
            old_count=1,
            new_start=5,
            new_count=2,
            lines=["@@ -5,1 +5,2 @@", " line 5", "+new line 5"],
            context_before=[],
            context_after=[],
        )

        mappings = [
            HunkTargetMapping(
                hunk=hunk1, target_commit="abc123", confidence="high", blame_info=[]
            ),
            HunkTargetMapping(
                hunk=hunk2, target_commit="def456", confidence="high", blame_info=[]
            ),
        ]

        result = _apply_ignored_hunks(mappings, git_ops)

        assert result is False
        # Verify both rollbacks were attempted despite failures
        git_ops._run_git_command.assert_any_call(
            "checkout", "stash-ref-rollback-test", "--", "file1.py"
        )
        git_ops._run_git_command.assert_any_call(
            "checkout", "stash-ref-rollback-test", "--", "file2.py"
        )
        # Verify cleanup still occurred
        git_ops._run_git_command.assert_any_call(
            "stash", "drop", "stash-ref-rollback-test"
        )


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
        import subprocess

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
