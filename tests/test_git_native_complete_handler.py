"""Tests for the complete git-native handler with multiple strategies."""

import pytest
import os
from unittest.mock import Mock, patch

from git_autosquash.hunk_target_resolver import HunkTargetMapping
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
            "git-add - Add files to staging area",
        )

        handler = GitNativeCompleteHandler(git_ops)

        assert handler.git_ops is git_ops
        assert (
            handler.preferred_strategy == "index"
        )  # Worktree removed, always uses index
        assert handler.logger is not None

    def test_initialization_defaults_to_index(self):
        """Test initialization defaults to index strategy."""
        # Mock git command availability
        self.git_ops._run_git_command.return_value = (True, "git available")

        handler = GitNativeCompleteHandler(self.git_ops)

        assert handler.preferred_strategy == "index"

    def test_empty_mappings_success(self):
        """Test handling of empty ignored mappings."""
        result = self.handler.apply_ignored_hunks([])

        assert result is True
        # Should not call any strategy handlers
        assert not hasattr(self.handler.index_handler, "_called")

    def test_successful_index_strategy(self):
        """Test successful application using index strategy."""
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

        # Force index strategy
        self.handler.force_strategy("index")

        # Mock successful index handler
        with patch.object(
            self.handler.index_handler, "apply_ignored_hunks"
        ) as mock_index:
            mock_index.return_value = True

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is True
            mock_index.assert_called_once_with([mapping])

    def test_invalid_strategy_rejected(self):
        """Test that invalid strategies are rejected."""
        # Try to force invalid strategy
        with pytest.raises(
            ValueError, match="Invalid strategy: invalid. Valid options: index, legacy"
        ):
            self.handler.force_strategy("invalid")

    def test_index_strategy_fails(self):
        """Test handling when index strategy fails."""
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

        # Mock index strategy failing
        with patch.object(
            self.handler.index_handler, "apply_ignored_hunks"
        ) as mock_index:
            mock_index.return_value = False

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is False
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

        # Force index strategy
        self.handler.force_strategy("index")

        # Mock index raising exception
        with patch.object(
            self.handler.index_handler, "apply_ignored_hunks"
        ) as mock_index:
            mock_index.side_effect = Exception("Index failed")

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is False  # Should fail when index strategy fails
            mock_index.assert_called_once_with([mapping])

    def test_environment_strategy_override(self):
        """Test strategy override from environment variable."""
        with patch.dict(os.environ, {"GIT_AUTOSQUASH_STRATEGY": "index"}):
            # Mock git command available
            self.git_ops._run_git_command.return_value = (True, "git available")

            handler = GitNativeCompleteHandler(self.git_ops)

            # Should prefer index as the default strategy
            assert handler.preferred_strategy == "index"

    def test_invalid_environment_strategy(self):
        """Test invalid environment strategy is ignored."""
        with patch.dict(os.environ, {"GIT_AUTOSQUASH_STRATEGY": "invalid"}):
            # Create fresh GitOps mock (uses index strategy)
            git_ops = Mock(spec=GitOps)
            git_ops.repo_path = "/test/repo"
            git_ops._run_git_command.return_value = (True, "git available")

            handler = GitNativeCompleteHandler(git_ops)

            # Should default to index since invalid env var is ignored
            assert handler.preferred_strategy == "index"

    def test_force_strategy_change(self):
        """Test forcing strategy change at runtime."""
        # Change to index explicitly
        self.handler.force_strategy("index")
        assert self.handler.preferred_strategy == "index"

        # Change to legacy
        self.handler.force_strategy("legacy")
        assert self.handler.preferred_strategy == "legacy"

        # Invalid strategy should raise error
        with pytest.raises(ValueError):
            self.handler.force_strategy("invalid")

    def test_get_strategy_info(self):
        """Test strategy information reporting."""
        with patch.dict(os.environ, {"GIT_AUTOSQUASH_STRATEGY": "index"}):
            # Create fresh GitOps mock
            git_ops = Mock(spec=GitOps)
            git_ops.repo_path = "/test/repo"
            git_ops._run_git_command.return_value = (True, "git available")

            handler = GitNativeCompleteHandler(git_ops)
            info = handler.get_strategy_info()

            assert info["preferred_strategy"] == "index"
            assert "legacy" in info["strategies_available"]
            assert "index" in info["strategies_available"]
            assert info["execution_order"] == ["index"]
            assert info["environment_override"] == "index"

    def test_index_preferred_execution_order(self):
        """Test execution order when index is preferred."""
        self.handler.force_strategy("index")

        order = self.handler._get_strategy_execution_order()
        assert order == ["index"]

    def test_legacy_preferred_execution_order(self):
        """Test execution order when legacy is preferred."""
        self.handler.force_strategy("legacy")

        order = self.handler._get_strategy_execution_order()
        assert order == ["legacy"]


class TestGitNativeStrategyManager:
    """Test the strategy manager utility class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)

    def test_create_handler_with_default_strategy(self):
        """Test creating handler with default strategy detection."""
        # Create fresh GitOps mock (defaults to index)
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "git available")

        handler = GitNativeStrategyManager.create_handler(git_ops)

        assert isinstance(handler, GitNativeCompleteHandler)
        assert handler.preferred_strategy == "index"

    def test_create_handler_with_strategy_override(self):
        """Test creating handler with explicit strategy."""
        # Mock git command available
        self.git_ops._run_git_command.return_value = (True, "git available")

        handler = GitNativeStrategyManager.create_handler(
            self.git_ops, strategy="index"
        )

        assert handler.preferred_strategy == "index"

    def test_get_recommended_strategy_default(self):
        """Test recommended strategy defaults to index."""
        self.git_ops._run_git_command.return_value = (True, "git add available")

        strategy = GitNativeStrategyManager.get_recommended_strategy(self.git_ops)

        assert strategy == "index"  # Default recommendation

    def test_get_recommended_strategy_fallback(self):
        """Test recommended strategy fallback behavior."""
        self.git_ops._run_git_command.return_value = (False, "command not found")

        strategy = GitNativeStrategyManager.get_recommended_strategy(self.git_ops)

        assert strategy == "index"

    def test_validate_strategy_compatibility_available_strategies(self):
        """Test strategy validation for available strategies."""
        self.git_ops._run_git_command.return_value = (True, "git available")

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

    def test_validate_strategy_compatibility_git_unavailable(self):
        """Test strategy validation when git is not available."""
        self.git_ops._run_git_command.return_value = (False, "command not found")

        # All strategies should handle git unavailability gracefully
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
        git_ops._run_git_command.return_value = (True, "git available")

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
        git_ops._run_git_command.return_value = (True, "git available")

        handler = GitNativeCompleteHandler(git_ops)

        # Test with empty mappings (should not require any git operations)
        result = handler.apply_ignored_hunks([])
        assert result is True

    def test_main_integration_uses_complete_handler(self):
        """Test that the complete handler can be imported and used by main."""
        # This test validates that the main integration points work
        # The actual _apply_ignored_hunks function doesn't exist in main.py
        # since the architecture has been simplified to use RebaseManager

        # Test that we can import and create the handler
        from git_autosquash.git_native_complete_handler import create_git_native_handler

        git_ops = Mock(spec=GitOps)
        git_ops.repo_path = "/test/repo"
        git_ops._run_git_command.return_value = (True, "git available")

        handler = create_git_native_handler(git_ops)

        # Verify basic functionality
        assert handler is not None
        assert hasattr(handler, "apply_ignored_hunks")

        # Test empty mappings work (integration point)
        result = handler.apply_ignored_hunks([])
        assert result is True

    def test_environment_configuration_integration(self):
        """Test environment-based strategy configuration works end-to-end."""
        with patch.dict(os.environ, {"GIT_AUTOSQUASH_STRATEGY": "index"}):
            git_ops = Mock(spec=GitOps)
            git_ops.repo_path = "/test/repo"
            git_ops._run_git_command.return_value = (True, "git available")

            # Clear cache to ensure fresh capability check
            from git_autosquash.git_native_complete_handler import (
                _global_capability_cache,
            )

            _global_capability_cache.clear()

            handler = create_git_native_handler(git_ops)

            # Should respect environment variable
            assert handler.preferred_strategy == "index"

            # Verify strategy info
            info = handler.get_strategy_info()
            assert info["execution_order"] == ["index"]
