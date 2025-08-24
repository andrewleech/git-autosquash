"""Result/Either pattern for enhanced error reporting and handling."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Callable, Optional, Any


T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


class Result(Generic[T, E], ABC):
    """Abstract base class for Result pattern implementation.

    Result represents either a successful value (Ok) or an error (Err).
    This pattern provides better error handling than exceptions for predictable
    failure cases and improves error context tracking.
    """

    @abstractmethod
    def is_ok(self) -> bool:
        """Check if the result represents success."""
        pass

    @abstractmethod
    def is_err(self) -> bool:
        """Check if the result represents an error."""
        pass

    @abstractmethod
    def unwrap(self) -> T:
        """Get the success value or raise an exception."""
        pass

    @abstractmethod
    def unwrap_or(self, default: T) -> T:
        """Get the success value or return default."""
        pass

    @abstractmethod
    def unwrap_err(self) -> E:
        """Get the error value or raise an exception."""
        pass

    @abstractmethod
    def map(self, func: Callable[[T], U]) -> "Result[U, E]":
        """Transform the success value if present."""
        pass

    @abstractmethod
    def map_err(self, func: Callable[[E], U]) -> "Result[T, U]":
        """Transform the error value if present."""
        pass

    @abstractmethod
    def and_then(self, func: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        """Chain operations that return Results."""
        pass


class Ok(Result[T, E]):
    """Represents a successful result."""

    def __init__(self, value: T) -> None:
        self._value = value

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self._value

    def unwrap_or(self, default: T) -> T:
        return self._value

    def unwrap_err(self) -> E:
        raise ValueError("Called unwrap_err() on an Ok result")

    def map(self, func: Callable[[T], U]) -> "Result[U, E]":
        return Ok(func(self._value))

    def map_err(self, func: Callable[[E], U]) -> "Result[T, U]":
        return Ok(self._value)

    def and_then(self, func: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        return func(self._value)

    def __repr__(self) -> str:
        return f"Ok({self._value!r})"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Ok) and self._value == other._value


class Err(Result[T, E]):
    """Represents an error result."""

    def __init__(self, error: E) -> None:
        self._error = error

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> T:
        raise ValueError(f"Called unwrap() on an Err result: {self._error}")

    def unwrap_or(self, default: T) -> T:
        return default

    def unwrap_err(self) -> E:
        return self._error

    def map(self, func: Callable[[T], U]) -> "Result[U, E]":
        return Err(self._error)

    def map_err(self, func: Callable[[E], U]) -> "Result[T, U]":
        return Err(func(self._error))

    def and_then(self, func: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        return Err(self._error)

    def __repr__(self) -> str:
        return f"Err({self._error!r})"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Err) and self._error == other._error


class GitOperationError:
    """Enhanced error type for git operations with context."""

    def __init__(
        self,
        operation: str,
        message: str,
        command: Optional[str] = None,
        exit_code: Optional[int] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        context: Optional[dict] = None,
    ) -> None:
        self.operation = operation
        self.message = message
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.context = context or {}

    def __repr__(self) -> str:
        return (
            f"GitOperationError(operation={self.operation!r}, message={self.message!r})"
        )

    def __str__(self) -> str:
        parts = [f"{self.operation}: {self.message}"]
        if self.command:
            parts.append(f"Command: {self.command}")
        if self.exit_code is not None:
            parts.append(f"Exit code: {self.exit_code}")
        if self.stderr:
            parts.append(f"Error output: {self.stderr}")
        return "\n".join(parts)


class StrategyExecutionError:
    """Error type for strategy execution failures."""

    def __init__(
        self,
        strategy: str,
        operation: str,
        message: str,
        underlying_error: Optional[Exception] = None,
        context: Optional[dict] = None,
    ) -> None:
        self.strategy = strategy
        self.operation = operation
        self.message = message
        self.underlying_error = underlying_error
        self.context = context or {}

    def __repr__(self) -> str:
        return f"StrategyExecutionError(strategy={self.strategy!r}, operation={self.operation!r})"

    def __str__(self) -> str:
        parts = [
            f"{self.strategy} strategy failed during {self.operation}: {self.message}"
        ]
        if self.underlying_error:
            parts.append(f"Caused by: {self.underlying_error}")
        return "\n".join(parts)


# Type aliases for common Result patterns
GitResult = Result[T, GitOperationError]
StrategyResult = Result[T, StrategyExecutionError]


def wrap_git_operation(
    operation: str,
    command_func: Callable[[], tuple[bool, str]],
    command: Optional[str] = None,
) -> GitResult[str]:
    """Wrap a git operation in a Result pattern.

    Args:
        operation: Description of the operation
        command_func: Function that executes the git command
        command: Optional command string for error reporting

    Returns:
        Result with command output or GitOperationError
    """
    try:
        success, output = command_func()
        if success:
            return Ok(output)
        else:
            error = GitOperationError(
                operation=operation,
                message="Git command failed",
                command=command,
                stderr=output,
            )
            return Err(error)
    except Exception as e:
        error = GitOperationError(
            operation=operation,
            message=f"Exception during git operation: {e}",
            command=command,
        )
        return Err(error)


def wrap_strategy_operation(
    strategy: str, operation: str, func: Callable[[], T]
) -> StrategyResult[T]:
    """Wrap a strategy operation in a Result pattern.

    Args:
        strategy: Name of the strategy
        operation: Description of the operation
        func: Function to execute

    Returns:
        Result with operation result or StrategyExecutionError
    """
    try:
        result = func()
        return Ok(result)
    except Exception as e:
        error = StrategyExecutionError(
            strategy=strategy, operation=operation, message=str(e), underlying_error=e
        )
        return Err(error)
