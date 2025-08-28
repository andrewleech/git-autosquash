"""
Error handling framework for git-autosquash tests.

This module provides comprehensive error boundaries, specific exception handling,
and recovery mechanisms for test scenarios.
"""

import functools
import logging
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type
import weakref

from git_autosquash.exceptions import GitAutoSquashError


class TestErrorCategory(Enum):
    """Categories of errors that can occur in tests."""

    GIT_OPERATION = "git_operation"
    FILE_SYSTEM = "file_system"
    MEMORY_LIMIT = "memory_limit"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    PERMISSION = "permission"
    UNEXPECTED = "unexpected"


class TestError(GitAutoSquashError):
    """Base exception for test-specific errors."""

    def __init__(
        self,
        message: str,
        category: TestErrorCategory,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.category = category
        self.context = context or {}
        self.original_exception = original_exception
        self.recovery_suggestions: List[str] = []

    def add_recovery_suggestion(self, suggestion: str) -> None:
        """Add a recovery suggestion for this error."""
        self.recovery_suggestions.append(suggestion)

    def get_full_context(self) -> Dict[str, Any]:
        """Get complete error context including suggestions."""
        full_context = self.context.copy()
        full_context.update(
            {
                "category": self.category.value,
                "recovery_suggestions": self.recovery_suggestions,
                "has_original_exception": self.original_exception is not None,
            }
        )

        if self.original_exception:
            full_context["original_exception_type"] = type(
                self.original_exception
            ).__name__
            full_context["original_exception_message"] = str(self.original_exception)

        return full_context


class GitOperationTestError(TestError):
    """Git operation failed during testing."""

    def __init__(
        self,
        operation: str,
        return_code: int,
        stderr: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        message = f"Git operation '{operation}' failed with return code {return_code}: {stderr}"
        super().__init__(message, TestErrorCategory.GIT_OPERATION, context)
        self.operation = operation
        self.return_code = return_code
        self.stderr = stderr

        # Add recovery suggestions based on common git errors
        if "not a git repository" in stderr.lower():
            self.add_recovery_suggestion(
                "Ensure the repository is properly initialized"
            )
        elif "permission denied" in stderr.lower():
            self.add_recovery_suggestion("Check file permissions and ownership")
        elif "index.lock" in stderr.lower():
            self.add_recovery_suggestion(
                "Another git process may be running; wait and retry"
            )


class FileSystemTestError(TestError):
    """File system operation failed during testing."""

    def __init__(self, operation: str, path: Path, original_exception: Exception):
        message = f"File system operation '{operation}' failed for path {path}: {original_exception}"
        super().__init__(
            message,
            TestErrorCategory.FILE_SYSTEM,
            {"operation": operation, "path": str(path)},
            original_exception,
        )
        self.operation = operation
        self.path = path


class MemoryLimitTestError(TestError):
    """Memory limit exceeded during testing."""

    def __init__(self, current_usage_mb: float, limit_mb: float, operation: str):
        message = f"Memory limit exceeded during '{operation}': {current_usage_mb:.1f}MB > {limit_mb:.1f}MB"
        super().__init__(
            message,
            TestErrorCategory.MEMORY_LIMIT,
            {
                "current_usage_mb": current_usage_mb,
                "limit_mb": limit_mb,
                "operation": operation,
            },
        )
        self.add_recovery_suggestion("Reduce test data size or increase memory limit")
        self.add_recovery_suggestion("Force garbage collection before retrying")


class TimeoutTestError(TestError):
    """Operation timed out during testing."""

    def __init__(self, operation: str, timeout_seconds: float, elapsed_seconds: float):
        message = f"Operation '{operation}' timed out after {elapsed_seconds:.1f}s (limit: {timeout_seconds:.1f}s)"
        super().__init__(
            message,
            TestErrorCategory.TIMEOUT,
            {
                "operation": operation,
                "timeout_seconds": timeout_seconds,
                "elapsed_seconds": elapsed_seconds,
            },
        )
        self.add_recovery_suggestion("Increase timeout limit or optimize the operation")


class ErrorBoundary:
    """
    Error boundary for test operations with recovery capabilities.

    This class provides structured error handling, categorization,
    and recovery mechanisms for test operations.
    """

    def __init__(
        self,
        operation_name: str,
        expected_exceptions: Optional[List[Type[Exception]]] = None,
        recovery_strategies: Optional[Dict[TestErrorCategory, Callable]] = None,
        max_retries: int = 3,
        backoff_multiplier: float = 1.5,
    ):
        self.operation_name = operation_name
        self.expected_exceptions = expected_exceptions or []
        self.recovery_strategies = recovery_strategies or {}
        self.max_retries = max_retries
        self.backoff_multiplier = backoff_multiplier
        self.error_history: List[TestError] = []
        self.logger = logging.getLogger(f"test_error_boundary.{operation_name}")

    def categorize_exception(self, exception: Exception) -> TestErrorCategory:
        """Categorize an exception into a test error category."""
        type(exception)
        exception_message = str(exception).lower()

        # Git-specific errors
        if (
            hasattr(exception, "returncode")
            or "git" in exception_message
            or isinstance(exception, GitAutoSquashError)
        ):
            return TestErrorCategory.GIT_OPERATION

        # File system errors
        if (
            isinstance(
                exception, (OSError, IOError, FileNotFoundError, PermissionError)
            )
            or "no such file" in exception_message
            or "permission denied" in exception_message
        ):
            return TestErrorCategory.FILE_SYSTEM

        # Memory errors
        if (
            isinstance(exception, MemoryError)
            or "memory" in exception_message
            or "out of memory" in exception_message
        ):
            return TestErrorCategory.MEMORY_LIMIT

        # Timeout errors
        if (
            "timeout" in exception_message
            or "timed out" in exception_message
            or hasattr(exception, "timeout")
        ):
            return TestErrorCategory.TIMEOUT

        # Resource exhaustion
        if (
            "resource" in exception_message
            or "limit" in exception_message
            or "quota" in exception_message
        ):
            return TestErrorCategory.RESOURCE_EXHAUSTION

        return TestErrorCategory.UNEXPECTED

    def wrap_exception(
        self, exception: Exception, context: Optional[Dict[str, Any]] = None
    ) -> TestError:
        """Wrap a raw exception in a TestError with categorization."""
        category = self.categorize_exception(exception)

        # Create specific error types based on category
        if category == TestErrorCategory.GIT_OPERATION and hasattr(
            exception, "returncode"
        ):
            return GitOperationTestError(
                operation=self.operation_name,
                return_code=getattr(exception, "returncode", -1),
                stderr=str(exception),
                context=context,
            )
        elif category == TestErrorCategory.FILE_SYSTEM and isinstance(
            exception, (OSError, IOError)
        ):
            path = context.get("path", Path(".")) if context else Path(".")
            return FileSystemTestError(self.operation_name, path, exception)
        else:
            error = TestError(
                message=f"Error in {self.operation_name}: {exception}",
                category=category,
                context=context,
                original_exception=exception,
            )
            return error

    def attempt_recovery(self, error: TestError) -> bool:
        """Attempt to recover from an error using registered strategies."""
        if error.category in self.recovery_strategies:
            try:
                recovery_func = self.recovery_strategies[error.category]
                return recovery_func(error)
            except Exception as recovery_exception:
                self.logger.warning(
                    f"Recovery strategy failed for {error.category}: {recovery_exception}"
                )
                return False
        return False

    @contextmanager
    def protect(self, context: Optional[Dict[str, Any]] = None):
        """Context manager for error boundary protection."""
        try:
            yield self
        except Exception as e:
            # Wrap the exception
            test_error = self.wrap_exception(e, context)
            self.error_history.append(test_error)

            # Log the error
            self.logger.error(
                f"Error in {self.operation_name}: {test_error.message}",
                extra={"error_context": test_error.get_full_context()},
            )

            # Attempt recovery if configured
            if self.attempt_recovery(test_error):
                self.logger.info(f"Successfully recovered from {test_error.category}")
                return

            # Re-raise as TestError
            raise test_error

    def execute_with_retries(
        self,
        operation: Callable[..., Any],
        *args,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        """Execute an operation with retry logic and error boundaries."""
        import time

        last_error = None
        backoff_seconds = 1.0

        for attempt in range(self.max_retries + 1):
            try:
                with self.protect(context):
                    return operation(*args, **kwargs)
            except TestError as e:
                last_error = e

                if attempt < self.max_retries:
                    # Attempt recovery
                    if self.attempt_recovery(e):
                        continue  # Try again immediately after successful recovery

                    # Wait before retrying
                    self.logger.info(
                        f"Retrying {self.operation_name} (attempt {attempt + 2}/{self.max_retries + 1}) "
                        f"after {backoff_seconds:.1f}s"
                    )
                    time.sleep(backoff_seconds)
                    backoff_seconds *= self.backoff_multiplier
                else:
                    # Final attempt failed
                    break

        # All retries exhausted
        if last_error:
            last_error.add_recovery_suggestion(
                f"All {self.max_retries} retry attempts failed"
            )
            raise last_error

        raise TestError(
            f"Operation {self.operation_name} failed without specific error",
            TestErrorCategory.UNEXPECTED,
            context,
        )


class TestResourceManager:
    """Manages test resources with proper cleanup and error handling."""

    def __init__(self):
        self.active_resources: weakref.WeakSet = weakref.WeakSet()
        self.cleanup_functions: List[Callable] = []
        self.logger = logging.getLogger("test_resource_manager")

    def register_resource(self, resource: Any) -> None:
        """Register a resource for cleanup tracking."""
        self.active_resources.add(resource)

    def register_cleanup(self, cleanup_func: Callable) -> None:
        """Register a cleanup function to be called during shutdown."""
        self.cleanup_functions.append(cleanup_func)

    def cleanup_all(self) -> None:
        """Clean up all registered resources and functions."""
        # Clean up registered functions
        for cleanup_func in reversed(self.cleanup_functions):  # Reverse order
            try:
                cleanup_func()
            except Exception as e:
                self.logger.warning(f"Cleanup function failed: {e}")

        self.cleanup_functions.clear()

        # Clean up tracked resources
        resources = list(self.active_resources)
        for resource in resources:
            try:
                if hasattr(resource, "cleanup"):
                    resource.cleanup()
                elif hasattr(resource, "close"):
                    resource.close()
            except Exception as e:
                self.logger.warning(f"Resource cleanup failed: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup_all()


def error_boundary(
    operation_name: str,
    expected_exceptions: Optional[List[Type[Exception]]] = None,
    recovery_strategies: Optional[Dict[TestErrorCategory, Callable]] = None,
    max_retries: int = 3,
):
    """Decorator for creating error boundaries around test functions."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            boundary = ErrorBoundary(
                operation_name=operation_name,
                expected_exceptions=expected_exceptions,
                recovery_strategies=recovery_strategies,
                max_retries=max_retries,
            )

            return boundary.execute_with_retries(
                func, *args, context={"function_name": func.__name__}, **kwargs
            )

        return wrapper

    return decorator


def safe_test_operation(
    operation_name: str,
    max_retries: int = 1,
    expected_exceptions: Optional[List[Type[Exception]]] = None,
):
    """Simple decorator for making test operations safe with basic error handling."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if expected_exceptions and not isinstance(
                        e, tuple(expected_exceptions)
                    ):
                        # Unexpected exception - don't retry
                        raise TestError(
                            f"Unexpected error in {operation_name}: {e}",
                            TestErrorCategory.UNEXPECTED,
                            {"function_name": func.__name__, "attempt": attempt},
                            e,
                        )

                    if attempt == max_retries:
                        # Final attempt - wrap and re-raise
                        raise TestError(
                            f"Error in {operation_name} after {max_retries} retries: {e}",
                            TestErrorCategory.UNEXPECTED,
                            {"function_name": func.__name__, "final_attempt": True},
                            e,
                        )

                    # Wait briefly before retry
                    import time

                    time.sleep(0.1 * (attempt + 1))

        return wrapper

    return decorator


# Global resource manager instance
_global_resource_manager = TestResourceManager()


def get_global_resource_manager() -> TestResourceManager:
    """Get the global test resource manager."""
    return _global_resource_manager


def register_test_cleanup(cleanup_func: Callable) -> None:
    """Register a cleanup function with the global resource manager."""
    _global_resource_manager.register_cleanup(cleanup_func)


@contextmanager
def test_error_recovery(
    operation_name: str,
    recovery_strategies: Optional[Dict[TestErrorCategory, Callable]] = None,
):
    """Context manager for test operations with error recovery."""
    boundary = ErrorBoundary(
        operation_name=operation_name, recovery_strategies=recovery_strategies or {}
    )

    with boundary.protect():
        yield boundary
