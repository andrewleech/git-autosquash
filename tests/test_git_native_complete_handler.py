"""Tests for the complete git-native handler with multiple strategies."""

import pytest
import os
from unittest.mock import Mock, patch

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.git_native_complete_handler import (
    GitNativeCompleteHandler,
    GitNativeStrategyManager,
    create_git_native_handler,
)
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk


class TestGitNativeCompleteHandler:
    """Test complete git-native handler functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.git_ops.repo_path = "/test/repo"
        self.handler = GitNativeCompleteHandler(self.git_ops)

    def test_initialization_with_auto_detect(self):
        """Test handler initialization with auto-detected strategy."""
        # Create a fresh GitOps mock and set up the response before creating handler
        git_ops = Mock(spec=GitOps)
        git_ops.repo_path = "/test/repo"
        git_ops._run_git_command.return_value = (
            True,
            "git-worktree - Manage multiple working trees add",
        )

        handler = GitNativeCompleteHandler(git_ops)

        assert handler.git_ops is git_ops
        assert handler.preferred_strategy == "worktree"
        assert handler.logger is not None

    def test_initialization_without_worktree_support(self):
        """Test initialization falls back to index when worktree unavailable."""
        # Mock worktree support failure
        self.git_ops._run_git_command.return_value = (False, "command not found")

        handler = GitNativeCompleteHandler(self.git_ops)

        assert handler.preferred_strategy == "index"

    def test_empty_mappings_success(self):
        """Test handling of empty ignored mappings."""
        result = self.handler.apply_ignored_hunks([])

        assert result is True
        # Should not call any strategy handlers
        assert not hasattr(self.handler.worktree_handler, "_called")

    def test_successful_worktree_strategy(self):
        """Test successful application using worktree strategy."""
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

        # Force worktree strategy
        self.handler.force_strategy("worktree")

        # Mock successful worktree handler
        with patch.object(
            self.handler.worktree_handler, "apply_ignored_hunks"
        ) as mock_worktree:
            mock_worktree.return_value = True

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is True
            mock_worktree.assert_called_once_with([mapping])

    def test_worktree_failure_fallback_to_index(self):
        """Test fallback to index strategy when worktree fails."""
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

        # Force worktree strategy as preferred
        self.handler.force_strategy("worktree")

        # Mock worktree failure and index success
        with (
            patch.object(
                self.handler.worktree_handler, "apply_ignored_hunks"
            ) as mock_worktree,
            patch.object(
                self.handler.index_handler, "apply_ignored_hunks"
            ) as mock_index,
        ):
            mock_worktree.return_value = False  # Worktree fails
            mock_index.return_value = True  # Index succeeds

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is True
            mock_worktree.assert_called_once_with([mapping])
            mock_index.assert_called_once_with([mapping])

    def test_all_strategies_fail(self):
        """Test handling when all strategies fail."""
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

        # Mock both strategies failing
        with (
            patch.object(
                self.handler.worktree_handler, "apply_ignored_hunks"
            ) as mock_worktree,
            patch.object(
                self.handler.index_handler, "apply_ignored_hunks"
            ) as mock_index,
        ):
            mock_worktree.return_value = False
            mock_index.return_value = False

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is False
            mock_worktree.assert_called_once_with([mapping])
            mock_index.assert_called_once_with([mapping])

    def test_strategy_exception_handling(self):
        """Test handling when strategy raises exception."""
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

        # Force worktree strategy
        self.handler.force_strategy("worktree")

        # Mock worktree raising exception and index succeeding
        with (
            patch.object(
                self.handler.worktree_handler, "apply_ignored_hunks"
            ) as mock_worktree,
            patch.object(
                self.handler.index_handler, "apply_ignored_hunks"
            ) as mock_index,
        ):
            mock_worktree.side_effect = Exception("Worktree failed")
            mock_index.return_value = True

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is True
            mock_worktree.assert_called_once_with([mapping])
            mock_index.assert_called_once_with([mapping])

    def test_environment_strategy_override(self):
        """Test strategy override from environment variable."""
        with patch.dict(os.environ, {"GIT_AUTOSQUASH_STRATEGY": "index"}):
            # Mock worktree support available
            self.git_ops._run_git_command.return_value = (True, "worktree available")

            handler = GitNativeCompleteHandler(self.git_ops)

            # Should prefer index despite worktree being available
            assert handler.preferred_strategy == "index"

    def test_invalid_environment_strategy(self):
        """Test invalid environment strategy is ignored."""
        with patch.dict(os.environ, {"GIT_AUTOSQUASH_STRATEGY": "invalid"}):
            # Create fresh GitOps mock with worktree support
            git_ops = Mock(spec=GitOps)
            git_ops.repo_path = "/test/repo"
            git_ops._run_git_command.return_value = (True, "worktree available add")

            handler = GitNativeCompleteHandler(git_ops)

            # Should auto-detect (worktree) since invalid env var is ignored
            assert handler.preferred_strategy == "worktree"

    def test_force_strategy_change(self):
        """Test forcing strategy change at runtime."""
        # Initially prefer worktree
        self.handler.force_strategy("worktree")
        assert self.handler.preferred_strategy == "worktree"

        # Change to index
        self.handler.force_strategy("index")
        assert self.handler.preferred_strategy == "index"

        # Invalid strategy should raise error
        with pytest.raises(ValueError):
            self.handler.force_strategy("invalid")

    def test_get_strategy_info(self):
        """Test strategy information reporting."""
        with patch.dict(os.environ, {"GIT_AUTOSQUASH_STRATEGY": "index"}):
            # Create fresh GitOps mock with worktree support
            git_ops = Mock(spec=GitOps)
            git_ops.repo_path = "/test/repo"
            git_ops._run_git_command.return_value = (True, "worktree available add")

            handler = GitNativeCompleteHandler(git_ops)
            info = handler.get_strategy_info()

            assert info["preferred_strategy"] == "index"
            assert info["worktree_available"] is True
            assert "worktree" in info["strategies_available"]
            assert "index" in info["strategies_available"]
            assert info["execution_order"] == ["index", "worktree"]
            assert info["environment_override"] == "index"

    def test_index_preferred_execution_order(self):
        """Test execution order when index is preferred."""
        self.handler.force_strategy("index")

        order = self.handler._get_strategy_execution_order()
        assert order == ["index", "worktree"]

    def test_worktree_preferred_execution_order(self):
        """Test execution order when worktree is preferred."""
        self.handler.force_strategy("worktree")

        order = self.handler._get_strategy_execution_order()
        assert order == ["worktree", "index"]


class TestGitNativeStrategyManager:
    """Test the strategy manager utility class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)

    def test_create_handler_with_default_strategy(self):
        """Test creating handler with default strategy detection."""
        # Create fresh GitOps mock with worktree support
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "worktree available add")

        handler = GitNativeStrategyManager.create_handler(git_ops)

        assert isinstance(handler, GitNativeCompleteHandler)
        assert handler.preferred_strategy == "worktree"

    def test_create_handler_with_strategy_override(self):
        """Test creating handler with explicit strategy."""
        # Mock worktree support available
        self.git_ops._run_git_command.return_value = (True, "worktree available")

        handler = GitNativeStrategyManager.create_handler(
            self.git_ops, strategy="index"
        )

        assert handler.preferred_strategy == "index"

    def test_get_recommended_strategy_with_worktree(self):
        """Test recommended strategy when worktree is available."""
        self.git_ops._run_git_command.return_value = (True, "worktree add available")

        strategy = GitNativeStrategyManager.get_recommended_strategy(self.git_ops)

        assert strategy == "worktree"

    def test_get_recommended_strategy_without_worktree(self):
        """Test recommended strategy when worktree is not available."""
        self.git_ops._run_git_command.return_value = (False, "command not found")

        strategy = GitNativeStrategyManager.get_recommended_strategy(self.git_ops)

        assert strategy == "index"

    def test_validate_strategy_compatibility_worktree_available(self):
        """Test strategy validation when worktree is available."""
        self.git_ops._run_git_command.return_value = (True, "worktree add available")

        assert (
            GitNativeStrategyManager.validate_strategy_compatibility(
                self.git_ops, "worktree"
            )
            is True
        )
        assert (
            GitNativeStrategyManager.validate_strategy_compatibility(
                self.git_ops, "index"
            )
            is True
        )
        assert (
            GitNativeStrategyManager.validate_strategy_compatibility(
                self.git_ops, "legacy"
            )
            is True
        )

    def test_validate_strategy_compatibility_worktree_unavailable(self):
        """Test strategy validation when worktree is not available."""
        self.git_ops._run_git_command.return_value = (False, "command not found")

        assert (
            GitNativeStrategyManager.validate_strategy_compatibility(
                self.git_ops, "worktree"
            )
            is False
        )
        assert (
            GitNativeStrategyManager.validate_strategy_compatibility(
                self.git_ops, "index"
            )
            is True
        )
        assert (
            GitNativeStrategyManager.validate_strategy_compatibility(
                self.git_ops, "legacy"
            )
            is True
        )

    def test_validate_invalid_strategy(self):
        """Test validation of invalid strategy."""
        assert (
            GitNativeStrategyManager.validate_strategy_compatibility(
                self.git_ops, "invalid"
            )
            is False
        )


class TestFactoryFunction:
    """Test the factory function for creating handlers."""

    def test_create_git_native_handler(self):
        """Test the factory function creates correct handler."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "worktree available")

        handler = create_git_native_handler(git_ops)

        assert isinstance(handler, GitNativeCompleteHandler)
        assert handler.git_ops is git_ops


class TestCompleteHandlerIntegration:
    """Integration tests for the complete handler."""

    def test_handler_can_be_imported_and_used(self):
        """Test that the complete handler can be imported and used."""
        from git_autosquash.git_native_complete_handler import GitNativeCompleteHandler

        git_ops = Mock(spec=GitOps)
        git_ops.repo_path = "/test/repo"
        git_ops._run_git_command.return_value = (True, "worktree available")

        handler = GitNativeCompleteHandler(git_ops)

        # Test with empty mappings (should not require any git operations)
        result = handler.apply_ignored_hunks([])
        assert result is True

    def test_main_integration_uses_complete_handler(self):
        """Test that main module uses the complete handler."""
        from git_autosquash.main import _apply_ignored_hunks

        git_ops = Mock(spec=GitOps)
        git_ops.repo_path = "/test/repo"

        # Mock the complete handler
        with patch(
            "git_autosquash.git_native_complete_handler.GitNativeCompleteHandler"
        ) as mock_handler_class:
            mock_handler = Mock()
            mock_handler.apply_ignored_hunks.return_value = True
            mock_handler_class.return_value = mock_handler

            result = _apply_ignored_hunks([], git_ops)

            assert result is True
            # Verify handler was created with git_ops and the global cache
            assert mock_handler_class.call_count == 1
            call_args = mock_handler_class.call_args
            assert call_args[0][0] == git_ops  # First positional arg is git_ops
            assert "capability_cache" in call_args[1]  # Cache is passed as keyword arg
            mock_handler.apply_ignored_hunks.assert_called_once_with([])

    def test_environment_configuration_integration(self):
        """Test environment-based strategy configuration works end-to-end."""
        with patch.dict(os.environ, {"GIT_AUTOSQUASH_STRATEGY": "index"}):
            git_ops = Mock(spec=GitOps)
            git_ops.repo_path = "/test/repo"
            git_ops._run_git_command.return_value = (True, "worktree available add")

            # Clear cache to ensure fresh capability check
            from git_autosquash.git_native_complete_handler import (
                _global_capability_cache,
            )

            _global_capability_cache.clear()

            handler = create_git_native_handler(git_ops)

            # Should respect environment variable
            assert handler.preferred_strategy == "index"

            # Should still have worktree as fallback
            info = handler.get_strategy_info()
            assert info["worktree_available"] is True
            assert info["execution_order"] == ["index", "worktree"]
