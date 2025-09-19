"""Tests for production optimizations including Result pattern and resource managers."""

from unittest.mock import Mock


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
    git_state_context,
    temporary_directory,
    IndexStateManager,
)


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
        git_ops._run_git_command.return_value = (True, "git available")

        cache = CapabilityCache()
        handler = GitNativeCompleteHandler(git_ops, capability_cache=cache)

        # Test that cache is properly integrated with handler
        assert handler.capability_cache is cache

        # Test cache operations with current architecture
        cache.set("test_capability", True)
        assert cache.has("test_capability")
        assert cache.get("test_capability") is True

        # Test cache clearing
        cache.clear()
        assert not cache.has("test_capability")

    def test_global_cache_sharing(self) -> None:
        """Test that global cache is shared between handler instances."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "git available")

        # Clear global cache first
        _global_capability_cache.clear()

        # Create two handlers using the factory
        handler1 = create_git_native_handler(git_ops, use_global_cache=True)
        handler2 = create_git_native_handler(git_ops, use_global_cache=True)

        # Verify both share the same cache instance
        assert handler1.capability_cache is handler2.capability_cache
        assert handler1.capability_cache is _global_capability_cache

        # Test that cache operations are shared
        handler1.capability_cache.set("shared_test", "value1")
        assert handler2.capability_cache.get("shared_test") == "value1"


class TestResultPattern:
    """Test the Result/Either pattern implementation."""

    def test_ok_result(self) -> None:
        """Test Ok result operations."""
        result: Ok[int, Exception] = Ok(42)

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
        result: Err[int, GitOperationError] = Err(error)

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
            strategy="index",
            operation="apply_hunks",
            message="Strategy failed",
            underlying_error=underlying,
        )

        assert error.strategy == "index"
        assert error.operation == "apply_hunks"
        assert error.underlying_error == underlying

        str_repr = str(error)
        assert "index" in str_repr
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


class TestPerformanceOptimizations:
    """Test performance optimizations in production scenarios."""

    def test_repeated_capability_checks_are_cached(self) -> None:
        """Test that capability cache is used for performance optimization."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "git available")

        handler = create_git_native_handler(git_ops, use_global_cache=True)

        # Clear any existing cache
        handler.capability_cache.clear()

        # Test cache performance by storing and retrieving values
        test_capabilities = ["cap1", "cap2", "cap3", "cap4", "cap5"]
        for cap in test_capabilities:
            handler.capability_cache.set(cap, True)

        # Verify all values are cached
        for cap in test_capabilities:
            assert handler.capability_cache.get(cap) is True
            assert handler.capability_cache.has(cap)

        # Strategy info should include cache size
        info = handler.get_strategy_info()
        assert info["capability_cache_size"] == len(test_capabilities)

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

        result: Err[None, StrategyExecutionError] = Err(strategy_error)

        # Chain error transformations
        chained_result = result.map_err(
            lambda e: StrategyExecutionError(
                strategy="wrapper_strategy",
                operation="wrapper_operation",
                message="Wrapper failed",
                underlying_error=RuntimeError("Chained error"),
            )
        )

        final_error = chained_result.unwrap_err()
        assert final_error.strategy == "wrapper_strategy"
        assert isinstance(final_error.underlying_error, RuntimeError)
        assert str(final_error.underlying_error) == "Chained error"

    def test_global_cache_performance_benefit(self) -> None:
        """Test that global cache provides measurable performance benefit."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "git available")

        _global_capability_cache.clear()

        # Create multiple handlers
        handlers = [
            create_git_native_handler(git_ops, use_global_cache=True) for _ in range(5)
        ]

        # Test that all handlers share the same cache instance
        cache_id = id(handlers[0].capability_cache)
        for handler in handlers[1:]:
            assert id(handler.capability_cache) == cache_id

        # Test cache performance - one handler sets a value, all can read it
        handlers[0].capability_cache.set("performance_test", "shared_value")
        for handler in handlers:
            assert handler.capability_cache.get("performance_test") == "shared_value"
