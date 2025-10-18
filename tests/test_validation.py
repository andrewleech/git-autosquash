"""Tests for ProcessingValidator class."""

import pytest
from unittest.mock import Mock, MagicMock
from git_autosquash.validation import ProcessingValidator, ValidationError
from git_autosquash.git_ops import GitOps


class TestProcessingValidator:
    """Test ProcessingValidator functionality."""

    @pytest.fixture
    def mock_git_ops(self):
        """Create mock GitOps instance."""
        mock = Mock(spec=GitOps)
        return mock

    @pytest.fixture
    def validator(self, mock_git_ops):
        """Create ProcessingValidator instance with mock GitOps."""
        return ProcessingValidator(mock_git_ops)

    # ===== Basic Validation Tests =====

    def test_validate_processing_success(self, validator, mock_git_ops):
        """Test validation passes when no differences."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git rev-parse HEAD
            MagicMock(returncode=0, stdout="abc123456\n", stderr=""),
            # git diff --exit-code (no differences)
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        result = validator.validate_processing("start123")

        assert result is True
        assert mock_git_ops.run_git_command.call_count == 2

    def test_validate_processing_corruption_detected(self, validator, mock_git_ops):
        """Test validation fails when differences found."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git rev-parse HEAD
            MagicMock(returncode=0, stdout="abc123456\n", stderr=""),
            # git diff --exit-code (differences found)
            MagicMock(
                returncode=1,
                stdout="diff --git a/file.py b/file.py\n@@ -1 +1 @@\n-old\n+new\n",
                stderr="",
            ),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        error_msg = str(exc_info.value)
        assert "Data corruption detected" in error_msg
        assert "start123" in error_msg
        assert "abc123456" in error_msg
        assert "Recovery options" in error_msg

    def test_validate_processing_git_command_failure(self, validator, mock_git_ops):
        """Test validation fails when git command fails."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git rev-parse HEAD
            MagicMock(returncode=0, stdout="abc123456\n", stderr=""),
            # git diff fails with unexpected error
            MagicMock(returncode=2, stdout="", stderr="fatal: bad object"),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        error_msg = str(exc_info.value)
        assert "Validation failed to run" in error_msg
        assert "exit code 2" in error_msg
        assert "fatal: bad object" in error_msg

    def test_validate_processing_diff_output_truncation(self, validator, mock_git_ops):
        """Test that large diffs are truncated in error messages."""
        # Create a large diff with 50 lines
        large_diff = "\n".join([f"line {i}" for i in range(50)])

        mock_git_ops.run_git_command.side_effect = [
            # git rev-parse HEAD
            MagicMock(returncode=0, stdout="abc123456\n", stderr=""),
            # git diff with large output
            MagicMock(returncode=1, stdout=large_diff, stderr=""),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        error_msg = str(exc_info.value)
        assert "truncated" in error_msg
        # Should only contain first 30 lines
        assert "line 29" in error_msg
        assert "line 40" not in error_msg

    # ===== Hunk Count Validation Tests =====

    def test_validate_hunk_count_success(self, validator, mock_git_ops):
        """Test hunk count validation passes when counts match."""
        # Mock diff output with 3 hunks
        diff_output = """diff --git a/file.py b/file.py
@@ -1,3 +1,3 @@
 content
@@ -10,5 +10,5 @@
 more content
@@ -20,2 +20,2 @@
 even more
"""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout=diff_output, stderr=""
        )

        # Create 3 mock hunks
        mock_hunks = [Mock(), Mock(), Mock()]

        result = validator.validate_hunk_count("commit123", mock_hunks)

        assert result is True
        mock_git_ops.run_git_command.assert_called_once_with(
            ["show", "--format=", "commit123"]
        )

    def test_validate_hunk_count_mismatch(self, validator, mock_git_ops):
        """Test hunk count validation fails when counts don't match."""
        # Mock diff output with 3 hunks
        diff_output = """diff --git a/file.py b/file.py
@@ -1,3 +1,3 @@
 content
@@ -10,5 +10,5 @@
 more
@@ -20,2 +20,2 @@
 even more
"""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout=diff_output, stderr=""
        )

        # Only 2 hunks to process (mismatch!)
        mock_hunks = [Mock(), Mock()]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_hunk_count("commit123", mock_hunks)

        error_msg = str(exc_info.value)
        assert "Hunk count mismatch" in error_msg
        assert "3 hunks in commit" in error_msg
        assert "2 hunks to process" in error_msg

    def test_validate_hunk_count_git_failure(self, validator, mock_git_ops):
        """Test hunk count validation fails when git command fails."""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=1, stdout="", stderr="fatal: bad revision 'badcommit'"
        )

        mock_hunks = [Mock()]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_hunk_count("badcommit", mock_hunks)

        error_msg = str(exc_info.value)
        assert "Failed to get diff" in error_msg
        assert "fatal: bad revision" in error_msg

    # ===== Error Message Tests =====

    def test_error_message_includes_commit_hashes(self, validator, mock_git_ops):
        """Test error messages include both start and end commit hashes."""
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="endcommit123\n", stderr=""),
            MagicMock(returncode=1, stdout="diff output", stderr=""),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("startcommit456")

        error_msg = str(exc_info.value)
        assert "startcommit456" in error_msg
        assert "endcommit123" in error_msg

    def test_error_message_includes_diff_sample(self, validator, mock_git_ops):
        """Test error messages include sample of diff output."""
        diff_sample = "diff --git a/file.py b/file.py\n@@ -1 +1 @@\n-old\n+new"

        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="abc123\n", stderr=""),
            MagicMock(returncode=1, stdout=diff_sample, stderr=""),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        error_msg = str(exc_info.value)
        assert "-old" in error_msg
        assert "+new" in error_msg

    def test_error_message_includes_recovery_command(self, validator, mock_git_ops):
        """Test error messages include user-facing recovery commands."""
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="current123\n", stderr=""),
            MagicMock(returncode=1, stdout="diff", stderr=""),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        error_msg = str(exc_info.value)
        assert "git diff start123" in error_msg or "git diff start" in error_msg
        assert "git reset --hard" in error_msg
        assert "Recovery options" in error_msg

    # ===== Edge Case Tests =====

    def test_validate_processing_head_resolution_failure(self, validator, mock_git_ops):
        """Test validate_processing fails gracefully when HEAD can't be resolved."""
        # HEAD resolution fails (e.g., not a git repository)
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=1, stdout="", stderr="fatal: not a git repository"
        )

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        error_msg = str(exc_info.value)
        assert "Failed to get HEAD hash" in error_msg
        assert "not a git repository" in error_msg

    def test_validation_detached_head(self, validator, mock_git_ops):
        """Test validation works in detached HEAD state."""
        # In detached HEAD, rev-parse HEAD still returns the commit hash
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="detached123\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        result = validator.validate_processing("start123")

        assert result is True

    def test_validation_same_commit(self, validator, mock_git_ops):
        """Test validation when starting commit equals HEAD (trivial case)."""
        # Same commit hash for both - git diff same123 same123 returns no diff
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="same123\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),  # No diff
        ]

        result = validator.validate_processing("same123")

        assert result is True
        # Verify diff was called with same commit twice
        diff_call = mock_git_ops.run_git_command.call_args_list[1]
        assert diff_call[0][0] == ["diff", "--exit-code", "same123", "same123"]

    def test_validation_empty_diff(self, validator, mock_git_ops):
        """Test validation with no changes (valid success case)."""
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="abc123\n", stderr=""),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        result = validator.validate_processing("start123", description="test operation")

        assert result is True

    def test_validation_binary_files(self, validator, mock_git_ops):
        """Test validation handles binary file changes."""
        binary_diff = "Binary files a/image.png and b/image.png differ\n"

        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="abc123\n", stderr=""),
            MagicMock(returncode=1, stdout=binary_diff, stderr=""),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        error_msg = str(exc_info.value)
        assert "Data corruption detected" in error_msg
        assert "Binary files" in error_msg

    def test_validation_very_large_diff(self, validator, mock_git_ops):
        """Test validation performance with large diffs."""
        # Create a 100-line diff
        large_diff_lines = [f"diff line {i}" for i in range(100)]
        large_diff = "\n".join(large_diff_lines)

        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="abc123\n", stderr=""),
            MagicMock(returncode=1, stdout=large_diff, stderr=""),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        error_msg = str(exc_info.value)
        # Should be truncated at 30 lines
        assert "truncated" in error_msg
        assert "diff line 0" in error_msg
        assert "diff line 29" in error_msg
        # Lines after 30 should not be present
        assert "diff line 50" not in error_msg

    # ===== Integration Scenario Tests =====

    def test_validation_with_custom_description(self, validator, mock_git_ops):
        """Test validation with custom operation description."""
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="abc123\n", stderr=""),
            MagicMock(returncode=1, stdout="diff", stderr=""),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123", description="squash operation")

        error_msg = str(exc_info.value)
        assert "squash operation" in error_msg

    def test_get_head_hash_success(self, validator, mock_git_ops):
        """Test _get_head_hash helper method."""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="abc123def456\n", stderr=""
        )

        head_hash = validator._get_head_hash()

        assert head_hash == "abc123def456"
        mock_git_ops.run_git_command.assert_called_once_with(["rev-parse", "HEAD"])

    def test_get_head_hash_failure(self, validator, mock_git_ops):
        """Test _get_head_hash fails gracefully."""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=1, stdout="", stderr="fatal: not a git repository"
        )

        with pytest.raises(ValidationError) as exc_info:
            validator._get_head_hash()

        error_msg = str(exc_info.value)
        assert "Failed to get HEAD hash" in error_msg
        assert "not a git repository" in error_msg

    def test_hunk_count_with_no_hunks(self, validator, mock_git_ops):
        """Test hunk count validation with empty diff."""
        # Diff with no hunks
        empty_diff = "diff --git a/file.py b/file.py\n"

        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout=empty_diff, stderr=""
        )

        empty_hunks = []

        result = validator.validate_hunk_count("commit123", empty_hunks)

        assert result is True

    def test_validation_unicode_content(self, validator, mock_git_ops):
        """Test validation handles unicode content in diffs."""
        unicode_diff = (
            "diff --git a/file.py b/file.py\n@@ -1 +1 @@\n-old 🎉\n+new 文字\n"
        )

        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="abc123\n", stderr=""),
            MagicMock(returncode=1, stdout=unicode_diff, stderr=""),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        error_msg = str(exc_info.value)
        assert "Data corruption detected" in error_msg
        # Unicode should be preserved in error message
        assert "🎉" in error_msg or "文字" in error_msg

    def test_validation_whitespace_only_diff(self, validator, mock_git_ops):
        """Test validation detects whitespace-only changes."""
        whitespace_diff = (
            "diff --git a/file.py b/file.py\n"
            "@@ -1 +1 @@\n"
            "-line without trailing space\n"
            "+line with trailing space \n"
        )

        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="abc123\n", stderr=""),
            MagicMock(returncode=1, stdout=whitespace_diff, stderr=""),
        ]

        with pytest.raises(ValidationError) as exc_info:
            validator.validate_processing("start123")

        # Whitespace changes are still corruption
        assert "Data corruption detected" in str(exc_info.value)
