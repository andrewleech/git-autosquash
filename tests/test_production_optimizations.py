"""Tests for production optimizations including Result pattern and resource managers."""

from unittest.mock import Mock, patch


from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.git_ops import GitOps
from git_autosquash.git_native_complete_handler import (
    GitNativeCompleteHandler,
    CapabilityCache,
    _global_capability_cache,
    create_git_native_handler,
)
from git_autosquash.result import Ok, Err, GitOperationError, StrategyExecutionError
from git_autosquash.resource_managers import (
    GitStateManager,
    WorktreeManager,
    git_state_context,
    temporary_directory,
    IndexStateManager,
)
from git_autosquash.git_worktree_handler import GitWorktreeIgnoreHandler


class TestCapabilityCache:
    """Test the capability caching system."""

    def test_cache_basic_operations(self) -> None:
        """Test basic cache operations."""
        cache = CapabilityCache()

        # Initially empty
        assert not cache.has("test_key")
        assert cache.get("test_key") is None

        # Set and get
        cache.set("test_key", True)
        assert cache.has("test_key")
        assert cache.get("test_key") is True

        # Overwrite
        cache.set("test_key", False)
        assert cache.get("test_key") is False

        # Clear
        cache.clear()
        assert not cache.has("test_key")
        assert cache.get("test_key") is None

    def test_cache_integration_with_handler(self) -> None:
        """Test capability cache integration with complete handler."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "add command help")

        cache = CapabilityCache()
        handler = GitNativeCompleteHandler(git_ops, capability_cache=cache)

        # First call should execute git command
        result1 = handler._check_worktree_support()
        assert result1 is True
        assert git_ops._run_git_command.call_count == 1

        # Second call should use cache
        result2 = handler._check_worktree_support()
        assert result2 is True
        assert git_ops._run_git_command.call_count == 1  # No additional call

        # Verify cache contains the result
        assert cache.has("worktree_support")
        assert cache.get("worktree_support") is True

    def test_global_cache_sharing(self) -> None:
        """Test that global cache is shared between handler instances."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "add command help")

        # Clear global cache first
        _global_capability_cache.clear()

        # Create two handlers using the factory
        handler1 = create_git_native_handler(git_ops, use_global_cache=True)
        handler2 = create_git_native_handler(git_ops, use_global_cache=True)

        # First handler performs the check
        result1 = handler1._check_worktree_support()
        assert result1 is True
        assert git_ops._run_git_command.call_count == 1

        # Second handler uses cached result
        result2 = handler2._check_worktree_support()
        assert result2 is True
        assert git_ops._run_git_command.call_count == 1  # No additional call

        # Verify both share the same cache
        assert handler1.capability_cache is handler2.capability_cache


class TestResultPattern:
    """Test the Result/Either pattern implementation."""

    def test_ok_result(self) -> None:
        """Test Ok result operations."""
        result: Ok[int] = Ok(42)

        assert result.is_ok()
        assert not result.is_err()
        assert result.unwrap() == 42
        assert result.unwrap_or(0) == 42

        # Map operations
        doubled = result.map(lambda x: x * 2)
        assert doubled.unwrap() == 84

        # Chain operations
        chained = result.and_then(lambda x: Ok(str(x)))
        assert chained.unwrap() == "42"

    def test_err_result(self) -> None:
        """Test Err result operations."""
        error = GitOperationError("test_op", "test error")
        result: Err[GitOperationError] = Err(error)

        assert not result.is_ok()
        assert result.is_err()
        assert result.unwrap_or(0) == 0
        assert result.unwrap_err() == error

        # Map operations preserve error
        mapped = result.map(lambda x: x * 2)
        assert mapped.is_err()
        assert mapped.unwrap_err() == error

        # Error mapping
        error_mapped = result.map_err(lambda e: f"Wrapped: {e.message}")
        assert error_mapped.unwrap_err() == "Wrapped: test error"

    def test_git_operation_error(self) -> None:
        """Test GitOperationError structure."""
        error = GitOperationError(
            operation="test_operation",
            message="Something went wrong",
            command="git test",
            exit_code=1,
            stderr="error output",
        )

        assert error.operation == "test_operation"
        assert error.message == "Something went wrong"
        assert error.command == "git test"
        assert error.exit_code == 1
        assert error.stderr == "error output"

        str_repr = str(error)
        assert "test_operation" in str_repr
        assert "Something went wrong" in str_repr
        assert "git test" in str_repr

    def test_strategy_execution_error(self) -> None:
        """Test StrategyExecutionError structure."""
        underlying = ValueError("underlying issue")
        error = StrategyExecutionError(
            strategy="worktree",
            operation="apply_hunks",
            message="Strategy failed",
            underlying_error=underlying,
        )

        assert error.strategy == "worktree"
        assert error.operation == "apply_hunks"
        assert error.underlying_error == underlying

        str_repr = str(error)
        assert "worktree" in str_repr
        assert "apply_hunks" in str_repr
        assert "underlying issue" in str_repr


class TestResourceManagers:
    """Test resource management context managers."""

    def test_git_state_manager_basic(self) -> None:
        """Test basic GitStateManager operations."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.side_effect = [
            (True, "main"),  # branch --show-current
            (True, "Saved working directory and index state WIP"),  # stash push
        ]

        manager = GitStateManager(git_ops)
        result = manager.save_current_state()

        assert result.is_ok()
        assert result.unwrap() == "stash@{0}"
        assert len(manager._stash_refs) == 1

    def test_git_state_context_manager(self) -> None:
        """Test git state context manager."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "success")

        with git_state_context(git_ops) as state_mgr:
            assert isinstance(state_mgr, GitStateManager)
            # Context should handle cleanup automatically

    def test_worktree_manager_basic(self) -> None:
        """Test basic WorktreeManager operations."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "Preparing worktree")

        with patch("tempfile.mkdtemp") as mock_mkdtemp:
            mock_mkdtemp.return_value = "/tmp/test-worktree"

            manager = WorktreeManager(git_ops)
            result = manager.create_worktree("HEAD")

            assert result.is_ok()
            worktree_path = result.unwrap()
            assert str(worktree_path) == "/tmp/test-worktree"

    def test_temporary_directory_context(self) -> None:
        """Test temporary directory context manager."""
        with temporary_directory(prefix="test-") as temp_dir:
            assert temp_dir.exists()
            assert temp_dir.is_dir()

            # Create a file in the directory
            test_file = temp_dir / "test.txt"
            test_file.write_text("test content")
            assert test_file.exists()

        # Directory should be cleaned up
        assert not temp_dir.exists()

    def test_index_state_manager(self) -> None:
        """Test IndexStateManager operations."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.side_effect = [
            (True, "abc123tree"),  # write-tree
            (True, ""),  # read-tree
        ]

        manager = IndexStateManager(git_ops)

        # Save state
        save_result = manager.save_index_state()
        assert save_result.is_ok()
        assert save_result.unwrap() == "abc123tree"

        # Restore state
        restore_result = manager.restore_index_state()
        assert restore_result.is_ok()


class TestEnhancedWorktreeHandler:
    """Test the enhanced worktree handler with Result patterns."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line 1", "+new line"],
            context_before=[],
            context_after=[],
        )

        self.mapping = HunkTargetMapping(
            hunk=self.hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        self.git_ops = Mock(spec=GitOps)
        self.handler = GitWorktreeIgnoreHandler(self.git_ops)

    def test_enhanced_apply_hunks_success(self) -> None:
        """Test enhanced apply hunks with successful execution."""
        # Mock successful operations
        self.git_ops._run_git_command.side_effect = [
            (True, "main"),  # branch --show-current
            (True, "Saved working directory"),  # stash push
            (True, "Preparing worktree"),  # worktree add
            (True, ""),  # apply patch script
            (True, "diff content"),  # get diff script
            (True, ""),  # worktree remove
        ]

        # The enhanced method now uses shell scripts to execute commands in worktree

        self.git_ops._run_git_command_with_input.return_value = (True, "")

        with (
            patch("tempfile.mkdtemp", return_value="/tmp/test-worktree"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.unlink"),
            patch("pathlib.Path.chmod"),
            patch("shutil.rmtree"),
            patch.object(
                self.handler,
                "_create_minimal_patch_for_hunk",
                return_value="patch content",
            ),
        ):
            result = self.handler.apply_ignored_hunks_enhanced([self.mapping])

            assert result.is_ok()
            assert result.unwrap() == 1  # One hunk applied

    def test_enhanced_apply_hunks_backup_failure(self) -> None:
        """Test enhanced apply hunks with backup failure."""
        # Mock backup failure
        self.git_ops._run_git_command.side_effect = [
            (True, "main"),  # branch --show-current
            (False, "stash failed"),  # stash push failure
        ]

        result = self.handler.apply_ignored_hunks_enhanced([self.mapping])

        assert result.is_err()
        error = result.unwrap_err()
        assert error.strategy == "worktree_enhanced"
        assert error.operation == "backup_state"
        assert "Failed to create backup" in error.message

    def test_enhanced_apply_empty_list(self) -> None:
        """Test enhanced apply hunks with empty mapping list."""
        result = self.handler.apply_ignored_hunks_enhanced([])

        assert result.is_ok()
        assert result.unwrap() == 0


class TestPerformanceOptimizations:
    """Test performance optimizations in production scenarios."""

    def test_repeated_capability_checks_are_cached(self) -> None:
        """Test that repeated capability checks use cache for performance."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "add command help")

        handler = create_git_native_handler(git_ops, use_global_cache=True)

        # Clear any existing cache
        handler.capability_cache.clear()

        # Perform multiple capability checks
        for _ in range(10):
            result = handler._check_worktree_support()
            assert result is True

        # Only one actual git command should have been executed
        assert git_ops._run_git_command.call_count == 1

        # Strategy info should include cache size
        info = handler.get_strategy_info()
        assert info["capability_cache_size"] == 1
        assert info["worktree_available"] is True

    def test_resource_manager_cleanup_guarantees(self) -> None:
        """Test that resource managers guarantee cleanup even on exceptions."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "success")

        cleanup_called = False

        def cleanup_action():
            nonlocal cleanup_called
            cleanup_called = True

        try:
            with git_state_context(git_ops) as state_mgr:
                state_mgr.add_cleanup_action(cleanup_action)
                # Simulate an error
                raise ValueError("Simulated error")
        except ValueError:
            pass  # Expected

        # Cleanup should have been called despite the exception
        assert cleanup_called

    def test_error_context_preservation(self) -> None:
        """Test that error context is preserved through Result chains."""
        original_error = ValueError("Original problem")
        strategy_error = StrategyExecutionError(
            strategy="test_strategy",
            operation="test_operation",
            message="Strategy failed",
            underlying_error=original_error,
        )

        result: Err[StrategyExecutionError] = Err(strategy_error)

        # Chain error transformations
        chained_result = result.map_err(
            lambda e: StrategyExecutionError(
                strategy="wrapper_strategy",
                operation="wrapper_operation",
                message="Wrapper failed",
                underlying_error=e,
            )
        )

        final_error = chained_result.unwrap_err()
        assert final_error.strategy == "wrapper_strategy"
        assert isinstance(final_error.underlying_error, StrategyExecutionError)
        assert final_error.underlying_error.underlying_error == original_error

    def test_global_cache_performance_benefit(self) -> None:
        """Test that global cache provides measurable performance benefit."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "add command help")

        _global_capability_cache.clear()

        # Create multiple handlers
        handlers = [
            create_git_native_handler(git_ops, use_global_cache=True) for _ in range(5)
        ]

        # All handlers perform capability check
        for handler in handlers:
            handler._check_worktree_support()

        # Only one git command should have been executed across all handlers
        assert git_ops._run_git_command.call_count == 1

        # All handlers should share the same cache
        cache_id = id(handlers[0].capability_cache)
        for handler in handlers[1:]:
            assert id(handler.capability_cache) == cache_id
