"""Tests for CLI flag behavior and combinations."""

import subprocess
from unittest.mock import Mock, patch


class TestCLIFlags:
    """Test CLI flags and their combinations."""

    def test_interactive_flag_short_form(self):
        """Test that -i flag works."""
        result = subprocess.run(
            ["git-autosquash", "-i", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--interactive" in result.stdout or "-i" in result.stdout

    def test_dry_run_short_form(self):
        """Test that -n flag works for dry-run."""
        result = subprocess.run(
            ["git-autosquash", "-n", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--dry-run" in result.stdout or "-n" in result.stdout

    def test_help_short_form(self):
        """Test that -h flag works for help."""
        result = subprocess.run(
            ["git-autosquash", "-h"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "git-autosquash" in result.stdout

    def test_verbose_short_form(self):
        """Test that -v flag works for verbose."""
        result = subprocess.run(
            ["git-autosquash", "-v", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--verbose" in result.stdout or "-v" in result.stdout

    def test_interactive_dry_run_combination_allowed(self):
        """Test that -i -n combination is allowed for interactive preview."""
        from git_autosquash.main import main

        test_args = ["git-autosquash", "-i", "-n"]

        with patch("sys.argv", test_args):
            with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
                mock_git_ops = Mock()
                mock_git_ops.is_git_available.return_value = True
                mock_git_ops.is_git_repo.return_value = True
                mock_git_ops.get_current_branch.return_value = "feature"
                mock_git_ops.get_merge_base_with_main.return_value = "base123"
                mock_git_ops.has_commits_since_merge_base.return_value = True
                mock_git_ops.get_working_tree_status.return_value = {
                    "is_clean": True,
                    "has_staged": False,
                    "has_unstaged": False,
                }
                mock_git_ops_class.return_value = mock_git_ops

                def mock_run_git_command(cmd_list):
                    result = Mock()
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""

                    if len(cmd_list) >= 2:
                        if cmd_list[0] == "rev-parse" and cmd_list[1] == "HEAD":
                            result.stdout = "abc123def456\n"

                    return result

                mock_git_ops.run_git_command.side_effect = mock_run_git_command

                # Mock process_hunks_and_mappings to return no hunks (trigger exit)
                with patch(
                    "git_autosquash.main.process_hunks_and_mappings"
                ) as mock_process:
                    mock_process.return_value = ([], [], "abc123", False, None)

                    with patch("sys.exit") as mock_exit:
                        main()
                        # Should exit with 0 (no hunks to process)
                        assert mock_exit.called
                        assert mock_exit.call_args[0][0] == 0

    def test_default_is_auto_accept(self):
        """Test that running with no flags defaults to auto-accept mode."""
        from git_autosquash.main import main

        test_args = ["git-autosquash"]

        with patch("sys.argv", test_args):
            with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
                mock_git_ops = Mock()
                mock_git_ops.is_git_available.return_value = True
                mock_git_ops.is_git_repo.return_value = True
                mock_git_ops.get_current_branch.return_value = "feature"
                mock_git_ops.get_merge_base_with_main.return_value = "base123"
                mock_git_ops.has_commits_since_merge_base.return_value = True
                mock_git_ops.get_working_tree_status.return_value = {
                    "is_clean": True,
                    "has_staged": False,
                    "has_unstaged": False,
                }
                mock_git_ops_class.return_value = mock_git_ops

                def mock_run_git_command(cmd_list):
                    result = Mock()
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""

                    if len(cmd_list) >= 2:
                        if cmd_list[0] == "rev-parse" and cmd_list[1] == "HEAD":
                            result.stdout = "abc123def456\n"

                    return result

                mock_git_ops.run_git_command.side_effect = mock_run_git_command

                # Mock process_hunks_and_mappings to return no hunks
                with patch(
                    "git_autosquash.main.process_hunks_and_mappings"
                ) as mock_process:
                    mock_process.return_value = ([], [], "abc123", False, None)

                    # Should not attempt to launch TUI in auto-accept mode
                    with patch("git_autosquash.main.run_interactive_ui") as mock_tui:
                        with patch("sys.exit") as mock_exit:
                            main()
                            # TUI should NOT be called in auto-accept mode
                            assert not mock_tui.called
                            # Should exit cleanly
                            assert mock_exit.called
                            assert mock_exit.call_args[0][0] == 0

    def test_interactive_flag_launches_tui(self):
        """Test that --interactive flag triggers TUI instead of auto-accept."""
        from git_autosquash.main import main

        test_args = ["git-autosquash", "--interactive"]

        with patch("sys.argv", test_args):
            with patch("git_autosquash.main.GitOps") as mock_git_ops_class:
                mock_git_ops = Mock()
                mock_git_ops.is_git_available.return_value = True
                mock_git_ops.is_git_repo.return_value = True
                mock_git_ops.get_current_branch.return_value = "feature"
                mock_git_ops.get_merge_base_with_main.return_value = "base123"
                mock_git_ops.has_commits_since_merge_base.return_value = True
                mock_git_ops.get_working_tree_status.return_value = {
                    "is_clean": True,
                    "has_staged": False,
                    "has_unstaged": False,
                }
                mock_git_ops_class.return_value = mock_git_ops

                def mock_run_git_command(cmd_list):
                    result = Mock()
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""

                    if len(cmd_list) >= 2:
                        if cmd_list[0] == "rev-parse" and cmd_list[1] == "HEAD":
                            result.stdout = "abc123def456\n"

                    return result

                mock_git_ops.run_git_command.side_effect = mock_run_git_command

                # Mock to return mappings that would trigger TUI
                with patch(
                    "git_autosquash.main.process_hunks_and_mappings"
                ) as mock_process:
                    mock_process.return_value = (
                        [Mock()],  # automatic_mappings
                        [],  # fallback_mappings
                        "abc123",  # starting_commit
                        False,  # temp_commit_created
                        Mock(),  # splitter
                    )

                    with patch("git_autosquash.main.run_interactive_ui") as mock_tui:
                        mock_tui.return_value = True
                        with patch("sys.exit"):
                            main()
                            # TUI SHOULD be called in interactive mode
                            assert mock_tui.called
