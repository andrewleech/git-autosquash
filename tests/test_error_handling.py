"""Tests for comprehensive error handling system."""

import pytest
from unittest.mock import patch, MagicMock

from git_autosquash.exceptions import (
    GitAutoSquashError, GitOperationError, RepositoryStateError,
    HunkProcessingError, ValidationError, UserCancelledError,
    FileOperationError, UIError, ErrorReporter, handle_unexpected_error
)


class TestGitAutoSquashError:
    """Test the base exception class."""
    
    def test_basic_error(self) -> None:
        """Test basic error creation and message."""
        error = GitAutoSquashError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.get_user_message() == "Error: Something went wrong"
    
    def test_error_with_recovery_suggestion(self) -> None:
        """Test error with recovery suggestion."""
        error = GitAutoSquashError("Something failed", "Try again with --force")
        expected = "Error: Something failed\nSuggestion: Try again with --force"
        assert error.get_user_message() == expected


class TestGitOperationError:
    """Test git operation specific errors."""
    
    def test_git_operation_error(self) -> None:
        """Test git operation error with details."""
        error = GitOperationError(
            command="git status",
            exit_code=128,
            stderr="fatal: not a git repository"
        )
        
        assert "git status" in str(error)
        assert "128" in str(error)
        assert "fatal: not a git repository" in str(error)
        assert error.command == "git status"
        assert error.exit_code == 128
        assert error.stderr == "fatal: not a git repository"
    
    def test_git_operation_error_with_recovery(self) -> None:
        """Test git operation error with recovery suggestion."""
        error = GitOperationError(
            command="git rebase",
            exit_code=1,
            stderr="Cannot rebase: You have uncommitted changes.",
            recovery_suggestion="Commit or stash your changes first"
        )
        
        user_msg = error.get_user_message()
        assert "Commit or stash your changes first" in user_msg


class TestRepositoryStateError:
    """Test repository state specific errors."""
    
    def test_repository_state_error(self) -> None:
        """Test repository state error."""
        error = RepositoryStateError(
            "Not on a branch",
            current_state="detached HEAD at abc123",
            recovery_suggestion="Switch to a branch"
        )
        
        assert "Not on a branch" in str(error)
        assert "detached HEAD at abc123" in str(error)
        assert "Switch to a branch" in error.get_user_message()


class TestValidationError:
    """Test input validation errors."""
    
    def test_validation_error(self) -> None:
        """Test validation error with invalid value."""
        error = ValidationError(
            "Invalid file path",
            invalid_value="../../../etc/passwd",
            recovery_suggestion="Use relative paths only"
        )
        
        assert "Invalid file path" in str(error)
        assert "../../../etc/passwd" in str(error)
        assert "Use relative paths only" in error.get_user_message()


class TestHunkProcessingError:
    """Test hunk processing specific errors."""
    
    def test_hunk_processing_error(self) -> None:
        """Test hunk processing error with file and hunk info."""
        error = HunkProcessingError(
            "Failed to apply hunk",
            file_path="src/main.py",
            hunk_info="lines 10-15",
            recovery_suggestion="Check for conflicts"
        )
        
        message = str(error)
        assert "Failed to apply hunk" in message
        assert "src/main.py" in message
        assert "lines 10-15" in message
        assert error.file_path == "src/main.py"
        assert error.hunk_info == "lines 10-15"


class TestRebaseConflictError:
    """Test rebase conflict specific errors."""
    
    def test_rebase_conflict_error(self) -> None:
        """Test rebase conflict error with file list."""
        from git_autosquash.exceptions import RebaseConflictError
        
        conflicted_files = ["src/main.py", "src/utils.py"]
        error = RebaseConflictError(conflicted_files)
        
        message = str(error)
        assert "src/main.py" in message
        assert "src/utils.py" in message
        assert error.conflicted_files == conflicted_files
        
        user_msg = error.get_user_message()
        assert "git add" in user_msg
        assert "git rebase --continue" in user_msg


class TestUserCancelledError:
    """Test user cancellation errors."""
    
    def test_user_cancelled_error(self) -> None:
        """Test user cancellation error."""
        error = UserCancelledError("rebase operation")
        assert "User cancelled rebase operation" in str(error)
        assert error.operation == "rebase operation"


class TestFileOperationError:
    """Test file operation specific errors."""
    
    def test_file_operation_error(self) -> None:
        """Test file operation error with details."""
        error = FileOperationError(
            operation="read",
            file_path="/tmp/patch.diff",
            reason="Permission denied",
            recovery_suggestion="Check file permissions"
        )
        
        message = str(error)
        assert "Failed to read file" in message
        assert "/tmp/patch.diff" in message
        assert "Permission denied" in message
        assert error.operation == "read"
        assert error.file_path == "/tmp/patch.diff"


class TestUIError:
    """Test UI specific errors."""
    
    def test_ui_error(self) -> None:
        """Test UI error with component info."""
        error = UIError(
            "Widget failed to render",
            component="DiffViewer",
            recovery_suggestion="Try resizing the terminal"
        )
        
        message = str(error)
        assert "Widget failed to render" in message
        assert "DiffViewer" in message
        assert error.component == "DiffViewer"


class TestHandleUnexpectedError:
    """Test unexpected error handling."""
    
    def test_handle_unexpected_error(self) -> None:
        """Test wrapping unexpected errors."""
        original_error = ValueError("Invalid value")
        wrapped = handle_unexpected_error(original_error, "processing data")
        
        assert isinstance(wrapped, GitAutoSquashError)
        assert "Unexpected error during processing data" in str(wrapped)
        assert wrapped.__cause__ is original_error
    
    def test_handle_unexpected_error_with_suggestion(self) -> None:
        """Test wrapping with custom recovery suggestion."""
        original_error = RuntimeError("Memory error")
        wrapped = handle_unexpected_error(
            original_error, 
            "large repository processing", 
            "Try with a smaller batch size"
        )
        
        user_msg = wrapped.get_user_message()
        assert "Try with a smaller batch size" in user_msg


class TestErrorReporter:
    """Test centralized error reporting."""
    
    def test_report_git_autosquash_error(self, capsys) -> None:
        """Test reporting custom errors."""
        error = GitAutoSquashError("Test error", "Try again")
        ErrorReporter.report_error(error)
        
        captured = capsys.readouterr()
        assert "Error: Test error" in captured.out
        assert "Suggestion: Try again" in captured.out
    
    def test_report_git_autosquash_error_with_context(self, capsys) -> None:
        """Test reporting with context."""
        error = GitAutoSquashError("Test error")
        ErrorReporter.report_error(error, "Testing")
        
        captured = capsys.readouterr()
        assert "[Testing]" in captured.out
        assert "Error: Test error" in captured.out
    
    def test_report_unexpected_error(self, capsys) -> None:
        """Test reporting unexpected errors."""
        error = ValueError("Unexpected issue")
        ErrorReporter.report_error(error)
        
        captured = capsys.readouterr()
        assert "Unexpected error: Unexpected issue" in captured.out
        assert "This may indicate a bug" in captured.out
    
    def test_report_warning(self, capsys) -> None:
        """Test warning reporting."""
        ErrorReporter.report_warning("This is a warning")
        
        captured = capsys.readouterr()
        assert "Warning: This is a warning" in captured.out
    
    def test_report_warning_with_context(self, capsys) -> None:
        """Test warning reporting with context."""
        ErrorReporter.report_warning("File not found", "Cleanup")
        
        captured = capsys.readouterr()
        assert "[Cleanup] Warning: File not found" in captured.out
    
    def test_report_success(self, capsys) -> None:
        """Test success reporting."""
        ErrorReporter.report_success("Operation completed")
        
        captured = capsys.readouterr()
        assert "✓ Operation completed" in captured.out
    
    def test_report_success_with_context(self, capsys) -> None:
        """Test success reporting with context."""
        ErrorReporter.report_success("Hunks applied", "Ignore processing")
        
        captured = capsys.readouterr()
        assert "[Ignore processing] ✓ Hunks applied" in captured.out


class TestErrorHandlingIntegration:
    """Test error handling integration with main functionality."""
    
    @patch('sys.argv', ['git-autosquash'])
    @patch('git_autosquash.main.GitOps')
    def test_repository_validation_errors(self, mock_git_ops, capsys) -> None:
        """Test that repository validation uses proper error types."""
        from git_autosquash.main import main
        
        # Mock git operations to simulate not being in a git repo
        mock_instance = MagicMock()
        mock_instance.is_git_repo.return_value = False
        mock_git_ops.return_value = mock_instance
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: Not in a git repository" in captured.out
        assert "Suggestion: Run this command from within a git repository" in captured.out
    
    @patch('sys.argv', ['git-autosquash'])
    @patch('git_autosquash.main.GitOps')
    def test_detached_head_error(self, mock_git_ops, capsys) -> None:
        """Test detached HEAD error handling."""
        from git_autosquash.main import main
        
        mock_instance = MagicMock()
        mock_instance.is_git_repo.return_value = True
        mock_instance.get_current_branch.return_value = None  # Detached HEAD
        mock_git_ops.return_value = mock_instance
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: Not on a branch (detached HEAD)" in captured.out
        assert "Switch to a branch" in captured.out