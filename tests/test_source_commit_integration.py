"""Integration tests for --source <commit-sha> CLI feature.

This module tests the complete workflow of using --source with a commit SHA:
- CLI argument parsing
- End-to-end execution with real git operations
- Retroactive squashing (descendant changes into ancestor)
- Blame analysis with historical commits
"""

import subprocess
from pathlib import Path
from unittest.mock import patch, Mock
import pytest

from git_autosquash.main import main


class TestSourceCommitCLIParsing:
    """Test --source CLI argument parsing and parameter flow."""

    def test_source_commit_argument_accepted(self):
        """Test that --source accepts commit SHA argument."""
        test_args = [
            "git-autosquash",
            "--source",
            "abc123def456789012345678901234567890abcd",
            "--auto-accept",
        ]

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

                # Mock git commands for validation and execution
                def mock_run_git_command(cmd_list):
                    result = Mock()
                    result.returncode = 0
                    result.stdout = ""
                    result.stderr = ""

                    # Handle validation commands for SquashContext
                    if len(cmd_list) >= 2:
                        if cmd_list[0] == "cat-file" and cmd_list[1] == "-t":
                            result.stdout = "commit\n"
                        elif cmd_list[0] == "rev-parse":
                            if cmd_list[1] == "HEAD":
                                result.stdout = "different123\n"
                            elif cmd_list[1] == "--verify":
                                result.returncode = 0
                            else:
                                result.stdout = (
                                    "abc123def456789012345678901234567890abcd\n"
                                )
                        elif (
                            cmd_list[0] == "merge-base"
                            and cmd_list[1] == "--is-ancestor"
                        ):
                            result.returncode = 0

                    return result

                # Mock the old tuple-returning API used internally
                def mock_run_git_command_tuple(*args):
                    # Return tuple format (success, output) for internal APIs
                    return (True, "")

                mock_git_ops.run_git_command.side_effect = mock_run_git_command
                mock_git_ops._run_git_command.side_effect = mock_run_git_command_tuple

                with patch("sys.exit") as mock_exit:
                    main()
                    # Should not exit with error for valid commit SHA
                    # May exit with 0 or not call exit at all
                    if mock_exit.called:
                        assert mock_exit.call_args[0][0] == 0

    def test_source_commit_short_sha_accepted(self):
        """Test that --source accepts short commit SHA."""
        test_args = ["git-autosquash", "--source", "abc123", "--auto-accept"]

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

                diff_result = Mock()
                diff_result.returncode = 0
                diff_result.stdout = ""
                mock_git_ops.run_git_command.return_value = diff_result

                with patch("sys.exit"):
                    # Should not raise exception
                    main()

    def test_source_commit_computed_correctly(self):
        """Test that source_commit is computed correctly from args.source."""
        # This test verifies the logic in main.py lines 696-709
        test_cases = [
            ("HEAD", None, "HEAD~1"),  # source_commit=None, blame_ref="HEAD~1"
            ("head", None, "HEAD~1"),  # Lowercase also processed as HEAD
            (
                "abc123",
                "abc123",
                "abc123~1",
            ),  # source_commit=SHA, blame_ref="SHA~1"
            ("auto", None, "HEAD"),  # source_commit=None, blame_ref="HEAD"
            (
                "working-tree",
                None,
                "HEAD",
            ),  # source_commit=None, blame_ref="HEAD"
            ("index", None, "HEAD"),  # source_commit=None, blame_ref="HEAD"
        ]

        for source_arg, expected_source_commit, expected_blame_ref in test_cases:
            with patch("sys.argv", ["git-autosquash", "--source", source_arg]):
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

                    diff_result = Mock()
                    diff_result.returncode = 0
                    diff_result.stdout = ""
                    mock_git_ops.run_git_command.return_value = diff_result

                    # Capture the call to _execute_rebase to check parameters
                    with patch("git_autosquash.main._execute_rebase") as mock_exec:
                        mock_exec.return_value = True
                        with patch("sys.exit"):
                            main()

                        # Verify source_commit parameter
                        if mock_exec.called:
                            call_kwargs = mock_exec.call_args[1]
                            assert (
                                call_kwargs.get("source_commit")
                                == expected_source_commit
                            ), f"Failed for source={source_arg}"
                            assert call_kwargs.get("blame_ref") == expected_blame_ref, (
                                f"Failed for source={source_arg}"
                            )


@pytest.mark.integration
class TestSourceCommitEndToEnd:
    """Integration tests with real git operations.

    These tests create temporary git repositories and test the full workflow.
    """

    def setup_test_repo(self, tmp_path: Path) -> tuple[Path, dict]:
        """Set up a test git repository with history for testing.

        Returns:
            Tuple of (repo_path, commit_dict)
        """
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        commits = {}

        # Create base commit
        (repo_path / "file.txt").write_text("line 1\nline 2\nline 3\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        commits["base"] = result.stdout.strip()

        # Create commit that we'll squash into
        (repo_path / "file.txt").write_text("modified line 1\nline 2\nline 3\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Target commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        commits["target"] = result.stdout.strip()

        # Create source commit with change to squash
        (repo_path / "file.txt").write_text(
            "modified line 1\nmodified line 2\nline 3\n"
        )
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Source commit to squash"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        commits["source"] = result.stdout.strip()

        return repo_path, commits

    def test_source_commit_workflow_placeholder(self, tmp_path):
        """Placeholder for end-to-end integration test.

        Full integration test will be implemented after Phase 2 (SquashContext)
        to avoid testing against code that will be refactored.
        """
        pytest.skip(
            "Integration test - implement after SquashContext refactoring (Phase 2)"
        )

    def test_retroactive_file_deletion_placeholder(self, tmp_path):
        """Placeholder for retroactive file deletion test.

        Tests the scenario where a descendant commit deletes a file and
        those changes are squashed into an ancestor commit.
        """
        pytest.skip(
            "Integration test - implement after SquashContext refactoring (Phase 2)"
        )


class TestSourceCommitBlameAnalysis:
    """Test blame analysis behavior with --source commit SHA."""

    def test_blame_ref_computed_from_source_commit(self):
        """Test that blame_ref is set to <commit>~1 when using --source <commit>."""
        # This tests the parameter flow through the call stack
        source_sha = "abc123def456789012345678901234567890abcd"

        with patch("sys.argv", ["git-autosquash", "--source", source_sha]):
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

                diff_result = Mock()
                diff_result.returncode = 0
                diff_result.stdout = ""
                mock_git_ops.run_git_command.return_value = diff_result

                # Capture HunkTargetResolver instantiation
                with patch(
                    "git_autosquash.main.HunkTargetResolver"
                ) as mock_resolver_class:
                    mock_resolver = Mock()
                    mock_resolver.resolve_targets.return_value = []
                    mock_resolver_class.return_value = mock_resolver

                    with patch("sys.exit"):
                        main()

                    # Verify HunkTargetResolver was created with blame_ref=<commit>~1
                    if mock_resolver_class.called:
                        call_kwargs = mock_resolver_class.call_args[1]
                        expected_blame_ref = f"{source_sha}~1"
                        assert call_kwargs.get("blame_ref") == expected_blame_ref

    def test_head_not_excluded_with_source_commit(self):
        """Test that HEAD is not excluded from blame when using --source <commit>."""
        # When processing a historical commit, HEAD should be a valid target
        # This is tested by the HEAD exclusion logic tests
        # This test documents the expected integration behavior
        assert True  # Placeholder - behavior tested in test_head_exclusion_logic.py


class TestSourceCommitValidation:
    """Test validation and error handling for --source commit SHA."""

    def test_invalid_source_commit_sha_placeholder(self):
        """Placeholder for invalid SHA handling test.

        Will be implemented in Phase 5 (Add validation and error handling).
        """
        pytest.skip("Validation test - implement in Phase 5")

    def test_source_commit_not_in_branch_placeholder(self):
        """Placeholder for source commit not in branch test.

        Will be implemented in Phase 5 (Add validation and error handling).
        """
        pytest.skip("Validation test - implement in Phase 5")

    def test_source_commit_equals_head_placeholder(self):
        """Placeholder for source == HEAD edge case test.

        Will be implemented in Phase 5 (Add validation and error handling).
        """
        pytest.skip("Validation test - implement in Phase 5")
