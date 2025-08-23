"""Tests for git_ops module."""

from pathlib import Path
from unittest.mock import Mock, patch


from git_autosquash.git_ops import GitOps


class TestGitOps:
    """Test cases for GitOps class."""

    def test_init_default_path(self) -> None:
        """Test GitOps initialization with default path."""
        git_ops = GitOps()
        assert git_ops.repo_path == Path.cwd()

    def test_init_custom_path(self) -> None:
        """Test GitOps initialization with custom path."""
        custom_path = Path("/tmp/test")
        git_ops = GitOps(custom_path)
        assert git_ops.repo_path == custom_path

    @patch("subprocess.run")
    def test_run_git_command_success(self, mock_run: Mock) -> None:
        """Test successful git command execution."""
        mock_run.return_value = Mock(returncode=0, stdout="output", stderr="")

        git_ops = GitOps()
        success, output = git_ops._run_git_command("status")

        assert success is True
        assert output == "output"
        mock_run.assert_called_once_with(
            ["git", "status"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=False,
        )

    @patch("subprocess.run")
    def test_run_git_command_failure(self, mock_run: Mock) -> None:
        """Test failed git command execution."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="error message")

        git_ops = GitOps()
        success, output = git_ops._run_git_command("invalid-command")

        assert success is False
        assert output == "error message"

    @patch("subprocess.run")
    def test_run_git_command_exception(self, mock_run: Mock) -> None:
        """Test git command execution with exception."""
        mock_run.side_effect = FileNotFoundError("git not found")

        git_ops = GitOps()
        success, output = git_ops._run_git_command("status")

        assert success is False
        assert "Git command failed" in output

    @patch.object(GitOps, "_run_git_command")
    def test_is_git_repo_true(self, mock_git_cmd: Mock) -> None:
        """Test is_git_repo returns True for valid repo."""
        mock_git_cmd.return_value = (True, ".git")

        git_ops = GitOps()
        assert git_ops.is_git_repo() is True
        mock_git_cmd.assert_called_once_with("rev-parse", "--git-dir")

    @patch.object(GitOps, "_run_git_command")
    def test_is_git_repo_false(self, mock_git_cmd: Mock) -> None:
        """Test is_git_repo returns False for non-repo."""
        mock_git_cmd.return_value = (False, "not a git repo")

        git_ops = GitOps()
        assert git_ops.is_git_repo() is False

    @patch.object(GitOps, "_run_git_command")
    def test_get_current_branch_success(self, mock_git_cmd: Mock) -> None:
        """Test get_current_branch returns branch name."""
        mock_git_cmd.return_value = (True, "feature-branch")

        git_ops = GitOps()
        branch = git_ops.get_current_branch()

        assert branch == "feature-branch"
        mock_git_cmd.assert_called_once_with("symbolic-ref", "--short", "HEAD")

    @patch.object(GitOps, "_run_git_command")
    def test_get_current_branch_detached_head(self, mock_git_cmd: Mock) -> None:
        """Test get_current_branch returns None for detached HEAD."""
        mock_git_cmd.return_value = (False, "not a branch")

        git_ops = GitOps()
        branch = git_ops.get_current_branch()

        assert branch is None

    @patch.object(GitOps, "_run_git_command")
    def test_get_merge_base_with_main_success(self, mock_git_cmd: Mock) -> None:
        """Test get_merge_base_with_main finds merge base."""
        # Mock merge-base command succeeding on first try (main)
        mock_git_cmd.return_value = (True, "abc123")

        git_ops = GitOps()
        merge_base = git_ops.get_merge_base_with_main("feature")

        assert merge_base == "abc123"
        mock_git_cmd.assert_called_once_with("merge-base", "main", "feature")

    @patch.object(GitOps, "_run_git_command")
    def test_get_merge_base_with_main_fallback_to_master(
        self, mock_git_cmd: Mock
    ) -> None:
        """Test get_merge_base_with_main falls back to master."""
        # Mock: main merge-base fails, master succeeds
        mock_git_cmd.side_effect = [
            (False, ""),  # main merge-base fails
            (True, "def456"),  # master merge-base succeeds
        ]

        git_ops = GitOps()
        merge_base = git_ops.get_merge_base_with_main("feature")

        assert merge_base == "def456"
        assert mock_git_cmd.call_count == 2

    @patch.object(GitOps, "_run_git_command")
    def test_get_merge_base_with_main_no_base_found(self, mock_git_cmd: Mock) -> None:
        """Test get_merge_base_with_main returns None when no base found."""
        # Mock: both main and master merge-base fail
        mock_git_cmd.side_effect = [
            (False, ""),  # main merge-base fails
            (False, ""),  # master merge-base fails
        ]

        git_ops = GitOps()
        merge_base = git_ops.get_merge_base_with_main("feature")

        assert merge_base is None

    @patch.object(GitOps, "_run_git_command")
    def test_get_merge_base_with_main_same_branch(self, mock_git_cmd: Mock) -> None:
        """Test get_merge_base_with_main skips when on main branch."""
        # Should try master after skipping main
        mock_git_cmd.return_value = (True, "xyz789")

        git_ops = GitOps()
        merge_base = git_ops.get_merge_base_with_main("main")

        assert merge_base == "xyz789"
        mock_git_cmd.assert_called_once_with("merge-base", "master", "main")

    @patch.object(GitOps, "_run_git_command")
    def test_get_working_tree_status_clean(self, mock_git_cmd: Mock) -> None:
        """Test get_working_tree_status for clean working tree."""
        mock_git_cmd.return_value = (True, "")

        git_ops = GitOps()
        status = git_ops.get_working_tree_status()

        expected = {"has_staged": False, "has_unstaged": False, "is_clean": True}
        assert status == expected

    @patch.object(GitOps, "_run_git_command")
    def test_get_working_tree_status_staged_changes(self, mock_git_cmd: Mock) -> None:
        """Test get_working_tree_status with staged changes."""
        mock_git_cmd.return_value = (True, "M  file1.py\nA  file2.py")

        git_ops = GitOps()
        status = git_ops.get_working_tree_status()

        expected = {"has_staged": True, "has_unstaged": False, "is_clean": False}
        assert status == expected

    @patch.object(GitOps, "_run_git_command")
    def test_get_working_tree_status_unstaged_changes(self, mock_git_cmd: Mock) -> None:
        """Test get_working_tree_status with unstaged changes."""
        mock_git_cmd.return_value = (True, " M file1.py\n?? file2.py")

        git_ops = GitOps()
        status = git_ops.get_working_tree_status()

        expected = {"has_staged": False, "has_unstaged": True, "is_clean": False}
        assert status == expected

    @patch.object(GitOps, "_run_git_command")
    def test_get_working_tree_status_mixed_changes(self, mock_git_cmd: Mock) -> None:
        """Test get_working_tree_status with both staged and unstaged changes."""
        mock_git_cmd.return_value = (True, "MM file1.py\nA  file2.py\n?? file3.py")

        git_ops = GitOps()
        status = git_ops.get_working_tree_status()

        expected = {"has_staged": True, "has_unstaged": True, "is_clean": False}
        assert status == expected

    @patch.object(GitOps, "_run_git_command")
    def test_get_working_tree_status_command_failure(self, mock_git_cmd: Mock) -> None:
        """Test get_working_tree_status handles command failure."""
        mock_git_cmd.return_value = (False, "error")

        git_ops = GitOps()
        status = git_ops.get_working_tree_status()

        expected = {"has_staged": False, "has_unstaged": False, "is_clean": True}
        assert status == expected

    @patch.object(GitOps, "_run_git_command")
    def test_has_commits_since_merge_base_true(self, mock_git_cmd: Mock) -> None:
        """Test has_commits_since_merge_base returns True when commits exist."""
        mock_git_cmd.return_value = (True, "3")

        git_ops = GitOps()
        result = git_ops.has_commits_since_merge_base("abc123")

        assert result is True
        mock_git_cmd.assert_called_once_with("rev-list", "--count", "abc123..HEAD")

    @patch.object(GitOps, "_run_git_command")
    def test_has_commits_since_merge_base_false(self, mock_git_cmd: Mock) -> None:
        """Test has_commits_since_merge_base returns False when no commits."""
        mock_git_cmd.return_value = (True, "0")

        git_ops = GitOps()
        result = git_ops.has_commits_since_merge_base("abc123")

        assert result is False

    @patch.object(GitOps, "_run_git_command")
    def test_has_commits_since_merge_base_command_failure(
        self, mock_git_cmd: Mock
    ) -> None:
        """Test has_commits_since_merge_base handles command failure."""
        mock_git_cmd.return_value = (False, "error")

        git_ops = GitOps()
        result = git_ops.has_commits_since_merge_base("abc123")

        assert result is False

    @patch.object(GitOps, "_run_git_command")
    def test_has_commits_since_merge_base_invalid_count(
        self, mock_git_cmd: Mock
    ) -> None:
        """Test has_commits_since_merge_base handles invalid count."""
        mock_git_cmd.return_value = (True, "invalid")

        git_ops = GitOps()
        result = git_ops.has_commits_since_merge_base("abc123")

        assert result is False
