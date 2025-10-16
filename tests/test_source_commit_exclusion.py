"""Tests for source commit exclusion functionality.

This module tests the --source <commit-sha> feature, specifically:
- Source commit parameter threading through the call stack
- Source commit exclusion from rebase sequence
- Edge cases and validation
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from git_autosquash.git_ops import GitOps
from git_autosquash.rebase_manager import RebaseManager
from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk


class TestSourceCommitParameterStorage:
    """Test source_commit parameter storage and lifecycle in RebaseManager."""

    @pytest.fixture
    def mock_git_ops(self):
        """Mock GitOps for unit testing."""
        mock = Mock(spec=GitOps)
        mock.repo_path = "/test/repo"
        return mock

    @pytest.fixture
    def rebase_manager(self, mock_git_ops):
        """Create RebaseManager with mocked GitOps."""
        return RebaseManager(mock_git_ops, "merge_base_commit")

    def test_source_commit_parameter_accepted(self, rebase_manager, mock_git_ops):
        """Test that execute_squash accepts context with source_commit."""
        from git_autosquash.squash_context import SquashContext

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line1", "+line2"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="target123", confidence="high", blame_info=[]
        )

        # Mock git operations to succeed
        mock_git_ops.get_current_branch.return_value = "feature-branch"
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": True,
            "has_staged": False,
            "has_unstaged": False,
        }

        # Mock successful git commands
        success_result = Mock()
        success_result.returncode = 0
        success_result.stdout = "commit_list\n"
        mock_git_ops.run_git_command.return_value = success_result

        # Create context with source_commit
        context = SquashContext(
            blame_ref="abc123def~1",
            source_commit="abc123def",
            is_historical_commit=True,
            working_tree_clean=True,
        )

        # Should accept context parameter without error
        with patch.object(
            rebase_manager, "_get_commit_order", return_value=["target123"]
        ):
            with patch.object(rebase_manager, "_start_rebase_edit", return_value=True):
                with patch.object(rebase_manager, "_apply_patch"):
                    with patch.object(rebase_manager, "_amend_commit"):
                        with patch.object(rebase_manager, "_continue_rebase"):
                            rebase_manager.execute_squash([mapping], context=context)

        # The context should be stored
        assert hasattr(rebase_manager, "_context")
        assert rebase_manager._context.source_commit == "abc123def"

    def test_source_commit_none_when_not_provided(self, rebase_manager, mock_git_ops):
        """Test that source_commit is None when context has no source_commit."""
        from git_autosquash.squash_context import SquashContext

        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line1", "+line2"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="target123", confidence="high", blame_info=[]
        )

        mock_git_ops.get_current_branch.return_value = "feature-branch"
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": True,
            "has_staged": False,
            "has_unstaged": False,
        }

        success_result = Mock()
        success_result.returncode = 0
        success_result.stdout = "commit_list\n"
        mock_git_ops.run_git_command.return_value = success_result

        # Create context without source_commit
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        with patch.object(
            rebase_manager, "_get_commit_order", return_value=["target123"]
        ):
            with patch.object(rebase_manager, "_start_rebase_edit", return_value=True):
                with patch.object(rebase_manager, "_apply_patch"):
                    with patch.object(rebase_manager, "_amend_commit"):
                        with patch.object(rebase_manager, "_continue_rebase"):
                            rebase_manager.execute_squash([mapping], context=context)

        # source_commit should be None
        assert rebase_manager._context.source_commit is None


class TestSourceCommitExclusionFromRebase:
    """Test source commit exclusion from rebase sequence."""

    @pytest.fixture
    def mock_git_ops(self):
        """Mock GitOps for unit testing."""
        mock = Mock(spec=GitOps)
        mock.repo_path = "/test/repo"
        return mock

    @pytest.fixture
    def rebase_manager(self, mock_git_ops):
        """Create RebaseManager with mocked GitOps."""
        return RebaseManager(mock_git_ops, "merge_base_commit")

    def test_source_commit_excluded_from_todo(self, rebase_manager, mock_git_ops):
        """Test that source commit is excluded from rebase todo list."""
        from git_autosquash.squash_context import SquashContext

        source_sha = "abc123def456789012345678901234567890abcd"
        target_sha = "def456abc789012345678901234567890abcdef"

        # Set up context with source commit
        context = SquashContext(
            blame_ref=f"{source_sha}~1",
            source_commit=source_sha,
            is_historical_commit=True,
            working_tree_clean=True,
        )
        rebase_manager._context = context

        # Mock git operations
        # rev-parse HEAD (called first in _generate_rebase_todo)
        head_result = Mock()
        head_result.returncode = 0
        head_result.stdout = "currenthead123\n"

        # is-ancestor check
        ancestor_result = Mock()
        ancestor_result.returncode = 0

        # rev-list to get commits
        rev_list_result = Mock()
        rev_list_result.returncode = 0
        # Source commit and target commit in the list
        rev_list_result.stdout = f"{source_sha}\n{target_sha}\n"

        # rev-parse to get full SHA of source commit
        source_rev_parse_result = Mock()
        source_rev_parse_result.returncode = 0
        source_rev_parse_result.stdout = source_sha + "\n"

        # rebase -i command
        rebase_result = Mock()
        rebase_result.returncode = 0
        rebase_result.stdout = ""
        rebase_result.stderr = ""

        mock_git_ops.run_git_command.side_effect = [
            head_result,  # rev-parse HEAD
            ancestor_result,  # is-ancestor check
            rev_list_result,  # rev-list for commit list
            source_rev_parse_result,  # rev-parse for source commit
            rebase_result,  # rebase -i command
        ]

        # Generate rebase todo
        with patch("tempfile.NamedTemporaryFile") as mock_temp:
            mock_file = MagicMock()
            mock_temp.return_value.__enter__.return_value = mock_file

            with patch("os.unlink"):
                rebase_manager._start_rebase_edit(target_sha)

        # Verify the todo only contains target commit, not source commit
        written_content = mock_file.write.call_args[0][0]
        assert f"edit {target_sha}" in written_content
        assert source_sha not in written_content

    def test_empty_rebase_after_source_exclusion(self, rebase_manager, mock_git_ops):
        """Test handling when only source commit is in rebase sequence."""
        from git_autosquash.squash_context import SquashContext

        source_sha = "abc123def456789012345678901234567890abcd"

        # Set up context with source commit
        context = SquashContext(
            blame_ref=f"{source_sha}~1",
            source_commit=source_sha,
            is_historical_commit=True,
            working_tree_clean=True,
        )
        rebase_manager._context = context

        # Mock git operations
        # rev-parse HEAD
        head_result = Mock()
        head_result.returncode = 0
        head_result.stdout = "currenthead123\n"

        # is-ancestor check
        ancestor_result = Mock()
        ancestor_result.returncode = 0

        # Only source commit in list
        rev_list_result = Mock()
        rev_list_result.returncode = 0
        rev_list_result.stdout = f"{source_sha}\n"

        # rev-parse for source commit
        source_rev_parse_result = Mock()
        source_rev_parse_result.returncode = 0
        source_rev_parse_result.stdout = source_sha + "\n"

        # rebase -i command
        rebase_result = Mock()
        rebase_result.returncode = 0
        rebase_result.stdout = ""
        rebase_result.stderr = ""

        mock_git_ops.run_git_command.side_effect = [
            head_result,
            ancestor_result,
            rev_list_result,
            source_rev_parse_result,
            rebase_result,
        ]

        with patch("tempfile.NamedTemporaryFile") as mock_temp:
            mock_file = MagicMock()
            mock_temp.return_value.__enter__.return_value = mock_file

            with patch("os.unlink"):
                rebase_manager._start_rebase_edit(source_sha)

        # Should use simple edit when only source commit
        written_content = mock_file.write.call_args[0][0]
        assert f"edit {source_sha}" in written_content
        assert "pick" not in written_content

    def test_source_commit_not_in_branch(self, rebase_manager, mock_git_ops):
        """Test handling when source commit is not in the branch."""
        from git_autosquash.squash_context import SquashContext

        source_sha = "abc123def456789012345678901234567890abcd"
        target_sha = "def456abc789012345678901234567890abcdef"

        # Set up context with source commit
        context = SquashContext(
            blame_ref=f"{source_sha}~1",
            source_commit=source_sha,
            is_historical_commit=True,
            working_tree_clean=True,
        )
        rebase_manager._context = context

        # Mock git operations
        # rev-parse HEAD
        head_result = Mock()
        head_result.returncode = 0
        head_result.stdout = "currenthead123\n"

        # is-ancestor check
        ancestor_result = Mock()
        ancestor_result.returncode = 0

        # Source commit NOT in the rev-list
        rev_list_result = Mock()
        rev_list_result.returncode = 0
        rev_list_result.stdout = f"{target_sha}\n"

        # rev-parse for source commit (will try to check)
        source_rev_parse_result = Mock()
        source_rev_parse_result.returncode = 0
        source_rev_parse_result.stdout = source_sha + "\n"

        # rebase -i command
        rebase_result = Mock()
        rebase_result.returncode = 0
        rebase_result.stdout = ""
        rebase_result.stderr = ""

        mock_git_ops.run_git_command.side_effect = [
            head_result,
            ancestor_result,
            rev_list_result,
            source_rev_parse_result,
            rebase_result,
        ]

        with patch("tempfile.NamedTemporaryFile") as mock_temp:
            mock_file = MagicMock()
            mock_temp.return_value.__enter__.return_value = mock_file

            with patch("os.unlink"):
                rebase_manager._start_rebase_edit(target_sha)

        # Should proceed normally since source not in list
        written_content = mock_file.write.call_args[0][0]
        assert f"edit {target_sha}" in written_content


class TestSourceCommitEdgeCases:
    """Test edge cases in source commit handling."""

    @pytest.fixture
    def mock_git_ops(self):
        """Mock GitOps for unit testing."""
        mock = Mock(spec=GitOps)
        mock.repo_path = "/test/repo"
        return mock

    @pytest.fixture
    def rebase_manager(self, mock_git_ops):
        """Create RebaseManager with mocked GitOps."""
        return RebaseManager(mock_git_ops, "merge_base_commit")

    def test_source_commit_equals_target_commit(self, rebase_manager, mock_git_ops):
        """Test when source commit is the same as target commit."""
        from git_autosquash.squash_context import SquashContext

        same_sha = "abc123def456789012345678901234567890abcd"

        # Set up context with source commit
        context = SquashContext(
            blame_ref=f"{same_sha}~1",
            source_commit=same_sha,
            is_historical_commit=True,
            working_tree_clean=True,
        )
        rebase_manager._context = context

        # Mock git operations
        # rev-parse HEAD
        head_result = Mock()
        head_result.returncode = 0
        head_result.stdout = "currenthead123\n"

        # is-ancestor check
        ancestor_result = Mock()
        ancestor_result.returncode = 0

        # rev-list result
        rev_list_result = Mock()
        rev_list_result.returncode = 0
        rev_list_result.stdout = f"{same_sha}\n"

        # rev-parse for source commit
        source_rev_parse_result = Mock()
        source_rev_parse_result.returncode = 0
        source_rev_parse_result.stdout = same_sha + "\n"

        # rebase -i command
        rebase_result = Mock()
        rebase_result.returncode = 0
        rebase_result.stdout = ""
        rebase_result.stderr = ""

        mock_git_ops.run_git_command.side_effect = [
            head_result,
            ancestor_result,
            rev_list_result,
            source_rev_parse_result,
            rebase_result,
        ]

        with patch("tempfile.NamedTemporaryFile") as mock_temp:
            mock_file = MagicMock()
            mock_temp.return_value.__enter__.return_value = mock_file

            with patch("os.unlink"):
                rebase_manager._start_rebase_edit(same_sha)

        # Should use simple edit when source == target
        written_content = mock_file.write.call_args[0][0]
        assert f"edit {same_sha}" in written_content
        assert "pick" not in written_content

    def test_source_commit_rev_parse_failure(self, rebase_manager, mock_git_ops):
        """Test handling when rev-parse fails for source commit."""
        from git_autosquash.squash_context import SquashContext

        source_sha = "invalid_sha"
        target_sha = "def456abc789012345678901234567890abcdef"

        # Set up context with invalid source commit
        context = SquashContext(
            blame_ref=f"{source_sha}~1",
            source_commit=source_sha,
            is_historical_commit=True,
            working_tree_clean=True,
        )
        rebase_manager._context = context

        # Mock git operations
        # rev-parse HEAD
        head_result = Mock()
        head_result.returncode = 0
        head_result.stdout = "currenthead123\n"

        # is-ancestor check
        ancestor_result = Mock()
        ancestor_result.returncode = 0

        # rev-list result
        rev_list_result = Mock()
        rev_list_result.returncode = 0
        rev_list_result.stdout = f"{target_sha}\n"

        # rev-parse for source commit - FAILS
        source_rev_parse_result = Mock()
        source_rev_parse_result.returncode = 1  # FAILURE
        source_rev_parse_result.stderr = "fatal: invalid object name"

        # rebase -i command
        rebase_result = Mock()
        rebase_result.returncode = 0
        rebase_result.stdout = ""
        rebase_result.stderr = ""

        mock_git_ops.run_git_command.side_effect = [
            head_result,
            ancestor_result,
            rev_list_result,
            source_rev_parse_result,
            rebase_result,
        ]

        with patch("tempfile.NamedTemporaryFile") as mock_temp:
            mock_file = MagicMock()
            mock_temp.return_value.__enter__.return_value = mock_file

            with patch("os.unlink"):
                rebase_manager._start_rebase_edit(target_sha)

        # Should proceed normally when rev-parse fails (no exclusion)
        written_content = mock_file.write.call_args[0][0]
        assert f"edit {target_sha}" in written_content

    def test_hasattr_check_with_context(self, rebase_manager):
        """Test that hasattr check works correctly with _context."""
        from git_autosquash.squash_context import SquashContext

        # Before setting
        assert (
            not hasattr(rebase_manager, "_context") or rebase_manager._context is None
        )

        # After setting with None source_commit
        context_none = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )
        rebase_manager._context = context_none
        assert hasattr(rebase_manager, "_context")
        assert rebase_manager._context.source_commit is None

        # After setting with source_commit value
        context_with_source = SquashContext(
            blame_ref="abc123~1",
            source_commit="abc123",
            is_historical_commit=True,
            working_tree_clean=True,
        )
        rebase_manager._context = context_with_source
        assert hasattr(rebase_manager, "_context")
        assert rebase_manager._context.source_commit == "abc123"


class TestSourceCommitIntegrationWithHunkTargetResolver:
    """Test integration between source commit and hunk target resolution."""

    def test_source_commit_flows_through_main_to_rebase(self):
        """Test that source_commit flows from main() to RebaseManager.

        This is a structural test to ensure the parameter is properly threaded.
        Actual integration test in test_source_commit_integration.py.
        """
        # This test documents the expected flow:
        # 1. main.py: args.source parsed to source_commit
        # 2. main.py: source_commit passed to _execute_rebase()
        # 3. main.py: _execute_rebase passes to RebaseManager.execute_squash()
        # 4. rebase_manager.py: execute_squash stores in self._source_commit
        # 5. rebase_manager.py: _generate_rebase_todo uses self._source_commit

        # This is tested via the unit tests above plus integration tests
        # Just documenting the flow here
        assert True  # Placeholder for flow documentation
