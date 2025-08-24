"""Custom exceptions for git-autosquash with consistent error handling."""

from typing import List, Optional


class GitAutoSquashError(Exception):
    """Base exception for all git-autosquash errors.
    
    This provides a common base for all custom exceptions with
    consistent error reporting and recovery guidance.
    """
    
    def __init__(self, message: str, recovery_suggestion: Optional[str] = None) -> None:
        """Initialize the exception.
        
        Args:
            message: Human-readable error description
            recovery_suggestion: Optional guidance for user to recover
        """
        super().__init__(message)
        self.recovery_suggestion = recovery_suggestion
        
    def get_user_message(self) -> str:
        """Get formatted error message for user display.
        
        Returns:
            Formatted error message with recovery suggestion if available
        """
        if self.recovery_suggestion:
            return f"Error: {self.args[0]}\nSuggestion: {self.recovery_suggestion}"
        return f"Error: {self.args[0]}"


class GitOperationError(GitAutoSquashError):
    """Error executing git commands."""
    
    def __init__(self, command: str, exit_code: int, stderr: str, 
                 recovery_suggestion: Optional[str] = None) -> None:
        """Initialize git operation error.
        
        Args:
            command: Git command that failed
            exit_code: Process exit code
            stderr: Error output from git
            recovery_suggestion: Optional recovery guidance
        """
        message = f"Git command failed: {command} (exit code {exit_code})"
        if stderr.strip():
            message += f"\nGit error: {stderr.strip()}"
        super().__init__(message, recovery_suggestion)
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr


class RepositoryStateError(GitAutoSquashError):
    """Error with repository state (not a git repo, wrong branch, etc)."""
    
    def __init__(self, message: str, current_state: Optional[str] = None,
                 recovery_suggestion: Optional[str] = None) -> None:
        """Initialize repository state error.
        
        Args:
            message: Error description
            current_state: Description of current repository state
            recovery_suggestion: How to fix the state issue
        """
        full_message = message
        if current_state:
            full_message += f" (current state: {current_state})"
        super().__init__(full_message, recovery_suggestion)
        self.current_state = current_state


class HunkProcessingError(GitAutoSquashError):
    """Error processing hunks (parsing, applying, etc)."""
    
    def __init__(self, message: str, file_path: Optional[str] = None,
                 hunk_info: Optional[str] = None,
                 recovery_suggestion: Optional[str] = None) -> None:
        """Initialize hunk processing error.
        
        Args:
            message: Error description
            file_path: File being processed when error occurred
            hunk_info: Details about the hunk that failed
            recovery_suggestion: How to resolve the issue
        """
        full_message = message
        if file_path:
            full_message += f" (file: {file_path})"
        if hunk_info:
            full_message += f" (hunk: {hunk_info})"
        super().__init__(full_message, recovery_suggestion)
        self.file_path = file_path
        self.hunk_info = hunk_info


class RebaseConflictError(GitAutoSquashError):
    """Error during rebase with conflicts that need resolution."""
    
    def __init__(self, conflicted_files: List[str], 
                 recovery_suggestion: Optional[str] = None) -> None:
        """Initialize rebase conflict error.
        
        Args:
            conflicted_files: List of files with conflicts
            recovery_suggestion: How to resolve conflicts
        """
        file_list = ", ".join(conflicted_files)
        message = f"Rebase conflicts in files: {file_list}"
        
        if not recovery_suggestion:
            recovery_suggestion = (
                "Resolve conflicts manually, then run 'git add <files>' and "
                "'git rebase --continue', or 'git rebase --abort' to cancel"
            )
        
        super().__init__(message, recovery_suggestion)
        self.conflicted_files = conflicted_files


class UserCancelledError(GitAutoSquashError):
    """User cancelled the operation."""
    
    def __init__(self, operation: str = "operation") -> None:
        """Initialize user cancellation error.
        
        Args:
            operation: Description of what was cancelled
        """
        super().__init__(f"User cancelled {operation}")
        self.operation = operation


class ValidationError(GitAutoSquashError):
    """Input validation error (bad file paths, invalid arguments, etc)."""
    
    def __init__(self, message: str, invalid_value: Optional[str] = None,
                 recovery_suggestion: Optional[str] = None) -> None:
        """Initialize validation error.
        
        Args:
            message: Validation error description
            invalid_value: The value that failed validation
            recovery_suggestion: How to provide valid input
        """
        full_message = message
        if invalid_value:
            full_message += f" (invalid value: {invalid_value})"
        super().__init__(full_message, recovery_suggestion)
        self.invalid_value = invalid_value


class FileOperationError(GitAutoSquashError):
    """Error with file system operations."""
    
    def __init__(self, operation: str, file_path: str, reason: str,
                 recovery_suggestion: Optional[str] = None) -> None:
        """Initialize file operation error.
        
        Args:
            operation: Operation that failed (read, write, delete, etc)
            file_path: Path to file that caused the error
            reason: Underlying reason for failure
            recovery_suggestion: How to resolve the file issue
        """
        message = f"Failed to {operation} file '{file_path}': {reason}"
        super().__init__(message, recovery_suggestion)
        self.operation = operation
        self.file_path = file_path
        self.reason = reason


class UIError(GitAutoSquashError):
    """Error in the user interface."""
    
    def __init__(self, message: str, component: Optional[str] = None,
                 recovery_suggestion: Optional[str] = None) -> None:
        """Initialize UI error.
        
        Args:
            message: UI error description
            component: UI component where error occurred
            recovery_suggestion: How to work around the UI issue
        """
        full_message = message
        if component:
            full_message += f" (component: {component})"
        super().__init__(full_message, recovery_suggestion)
        self.component = component


def handle_unexpected_error(error: Exception, operation: str, 
                          recovery_suggestion: Optional[str] = None) -> GitAutoSquashError:
    """Convert unexpected exceptions to GitAutoSquashError for consistent handling.
    
    Args:
        error: The unexpected exception that was caught
        operation: Description of what operation was being performed
        recovery_suggestion: Optional recovery guidance
        
    Returns:
        GitAutoSquashError wrapping the unexpected exception
    """
    message = f"Unexpected error during {operation}: {error}"
    if not recovery_suggestion:
        recovery_suggestion = (
            "This may indicate a bug. Please report this error with the "
            "operation details and error message."
        )
    
    wrapped_error = GitAutoSquashError(message, recovery_suggestion)
    wrapped_error.__cause__ = error
    return wrapped_error


class ErrorReporter:
    """Centralized error reporting with consistent formatting and logging."""
    
    @staticmethod
    def report_error(error: Exception, context: Optional[str] = None) -> None:
        """Report an error with consistent formatting.
        
        Args:
            error: The exception to report
            context: Optional context about when the error occurred
        """
        if isinstance(error, GitAutoSquashError):
            if context:
                print(f"[{context}] {error.get_user_message()}")
            else:
                print(error.get_user_message())
        else:
            # Handle unexpected exceptions
            if context:
                print(f"[{context}] Unexpected error: {error}")
            else:
                print(f"Unexpected error: {error}")
            print("This may indicate a bug. Please report this error.")
    
    @staticmethod
    def report_warning(message: str, context: Optional[str] = None) -> None:
        """Report a warning message.
        
        Args:
            message: Warning message
            context: Optional context about when the warning occurred
        """
        if context:
            print(f"[{context}] Warning: {message}")
        else:
            print(f"Warning: {message}")
    
    @staticmethod
    def report_success(message: str, context: Optional[str] = None) -> None:
        """Report a success message.
        
        Args:
            message: Success message
            context: Optional context about the successful operation
        """
        if context:
            print(f"[{context}] ✓ {message}")
        else:
            print(f"✓ {message}")