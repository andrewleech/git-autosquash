"""
Shared pytest fixtures for all tests.

This file provides common fixtures that are automatically discovered by pytest
across the entire test suite.
"""

import tempfile
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import Mock, patch
import pytest

from tests.base_test_repository import BaseTestRepository, temporary_test_repository
from git_autosquash.hunk_parser import DiffHunk


@pytest.fixture(scope="function")
def git_repo_builder():
    """Enhanced git repository builder for complex scenarios."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "test_repo"
        repo_path.mkdir()

        class GitRepoBuilder(BaseTestRepository):
            def __init__(self, path: Path):
                super().__init__(path)

            def add_commit(self, files_content: Dict[str, str], message: str) -> str:
                """Add files and create commit, return commit hash."""
                return super().add_commit(files_content, message)

        yield GitRepoBuilder(repo_path)


@pytest.fixture(scope="function")
def performance_test_config():
    """Configuration for performance tests."""
    return {
        "max_patch_generation_time": 5.0,
        "max_hunk_parsing_time": 2.0,
        "max_memory_increase_mb": 100,
        "large_file_lines": 5000,
        "many_hunks_count": 50,
        "stress_test_files": 20,
    }


@pytest.fixture(scope="function")
def operation_name():
    """Provide operation name for error handling tests."""
    return "test_operation"


@pytest.fixture(scope="function")
def temp_repo():
    """Create a basic temporary git repository."""
    with temporary_test_repository("test_repo") as repo:
        yield repo


@pytest.fixture(scope="function")
def mock_git_ops():
    """Provide a properly configured mock GitOps instance."""
    mock = Mock()
    # Setup common return values for run_git_command (subprocess-style)
    mock_result = Mock()
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_result.returncode = 0
    mock.run_git_command.return_value = mock_result

    # Setup common return values for _run_git_command (tuple-style)
    mock._run_git_command.return_value = (True, "")  # (success, output)

    # Setup _run_git_command_with_input (tuple-style)
    mock._run_git_command_with_input.return_value = (True, "")

    # Setup common GitOps attributes
    mock.repo_path = "/test/repo"

    return mock


@pytest.fixture
def blame_analyzer(mock_git_ops):
    """Properly configured BlameAnalyzer for testing."""
    try:
        from git_autosquash.blame_analyzer import BlameAnalyzer

        with patch("git_autosquash.blame_analyzer.BatchGitOperations") as mock_batch:
            # Setup default blame responses
            mock_batch.return_value.run_git_batch.return_value = [
                (True, "abc123 test.py 10 test content", "")
            ]
            # Setup batch_expand_hashes to return input hashes unchanged for testing
            mock_batch.return_value.batch_expand_hashes.return_value = {}

            # Setup batch_load_commit_info for commit timestamp/summary tests
            from unittest.mock import Mock

            mock_commit_info = Mock()
            mock_commit_info.timestamp = 1640995200
            mock_commit_info.short_hash = "abc1234"
            mock_commit_info.subject = "Add new feature"
            mock_batch.return_value.batch_load_commit_info.return_value = {
                "abc123": mock_commit_info,
                "abc123456": mock_commit_info,
            }
            analyzer = BlameAnalyzer(mock_git_ops, "test_merge_base")
            yield analyzer
    except ImportError:
        # Fallback if BlameAnalyzer doesn't exist or has different import path
        mock = Mock()
        mock.git_ops = mock_git_ops
        mock.merge_base = "test_merge_base"
        yield mock


@pytest.fixture
def setup_git_ops_chain(mock_git_ops):
    """Helper for complex GitOps mock chains."""

    def chain(*outputs):
        results = []
        for output in outputs:
            mock_result = Mock()
            mock_result.stdout = output
            mock_result.stderr = ""
            mock_result.returncode = 0
            results.append(mock_result)
        mock_git_ops.run_git_command.side_effect = results
        return mock_git_ops

    return chain


def create_test_hunk(
    file_path: str = "test.py",
    old_start: int = 1,
    new_start: int = 1,
    additions: Optional[List[str]] = None,
    deletions: Optional[List[str]] = None,
    context_lines: Optional[List[str]] = None,
) -> DiffHunk:
    """Create DiffHunk for testing with proper constructor."""
    diff_lines = []

    # Add context lines first
    if context_lines:
        diff_lines.extend([f" {line}" for line in context_lines[:2]])

    # Add deletions
    if deletions:
        diff_lines.extend([f"-{line}" for line in deletions])

    # Add additions
    if additions:
        diff_lines.extend([f"+{line}" for line in additions])

    # Add trailing context
    if context_lines and len(context_lines) > 2:
        diff_lines.extend([f" {line}" for line in context_lines[2:]])

    old_count = len(deletions or []) + len(context_lines or [])
    new_count = len(additions or []) + len(context_lines or [])

    return DiffHunk(
        file_path=file_path,
        old_start=old_start,
        old_count=old_count if old_count > 0 else 1,
        new_start=new_start,
        new_count=new_count if new_count > 0 else 1,
        lines=diff_lines,
        context_before=[],
        context_after=[],
    )
