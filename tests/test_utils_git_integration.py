"""Test utilities for real git repository setup and integration testing."""

import subprocess
import tempfile
from pathlib import Path
from typing import Iterator, List

import pytest

from git_autosquash.git_ops import GitOps


class GitTestRepo:
    """Helper class for creating and managing test git repositories."""

    def __init__(self, repo_path: Path) -> None:
        """Initialize git test repository.

        Args:
            repo_path: Path to the test repository directory
        """
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)

    def run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run git command in test repository.

        Args:
            *args: Git command arguments

        Returns:
            CompletedProcess result
        """
        return subprocess.run(
            ["git"] + list(args),
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=False,
        )

    def create_file(self, filepath: str, content: str) -> None:
        """Create a file with content in the repository.

        Args:
            filepath: Relative path to file
            content: File content
        """
        full_path = self.repo_path / filepath
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    def modify_file(self, filepath: str, new_content: str) -> None:
        """Modify existing file content.

        Args:
            filepath: Relative path to file
            new_content: New file content
        """
        full_path = self.repo_path / filepath
        full_path.write_text(new_content)

    def add_and_commit(self, files: List[str], message: str) -> str:
        """Add files and create commit.

        Args:
            files: List of file paths to add
            message: Commit message

        Returns:
            Commit hash
        """
        for file in files:
            self.run_git("add", file)
        result = self.run_git("commit", "-m", message)
        if result.returncode != 0:
            raise RuntimeError(f"Commit failed: {result.stderr}")

        # Get commit hash
        hash_result = self.run_git("rev-parse", "HEAD")
        return hash_result.stdout.strip()

    def create_branch(self, branch_name: str, from_ref: str = "HEAD") -> None:
        """Create and switch to new branch.

        Args:
            branch_name: Name of new branch
            from_ref: Reference to create branch from
        """
        self.run_git("checkout", "-b", branch_name, from_ref)

    def switch_branch(self, branch_name: str) -> None:
        """Switch to existing branch.

        Args:
            branch_name: Name of branch to switch to
        """
        self.run_git("checkout", branch_name)

    def has_staged_changes(self) -> bool:
        """Check if there are staged changes.

        Returns:
            True if there are staged changes
        """
        result = self.run_git("diff", "--cached", "--quiet")
        return result.returncode != 0

    def has_unstaged_changes(self) -> bool:
        """Check if there are unstaged changes.

        Returns:
            True if there are unstaged changes
        """
        result = self.run_git("diff", "--quiet")
        return result.returncode != 0

    def get_file_content(self, filepath: str) -> str:
        """Get current content of file.

        Args:
            filepath: Relative path to file

        Returns:
            File content
        """
        full_path = self.repo_path / filepath
        return full_path.read_text()

    def create_conflicting_state(self, filepath: str) -> None:
        """Create a conflicting file state that would cause patch failures.

        Args:
            filepath: Path to file to make conflicting
        """
        # Modify file in working directory
        current_content = self.get_file_content(filepath)
        conflicting_content = current_content.replace("original", "conflicting")
        self.modify_file(filepath, conflicting_content)


@pytest.fixture
def git_test_repo() -> Iterator[GitTestRepo]:
    """Create temporary git repository for testing.

    Yields:
        GitTestRepo instance with initialized repository
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        repo = GitTestRepo(repo_path)

        # Create initial commit to avoid empty repository issues
        repo.create_file("README.md", "# Test Repository\n")
        repo.add_and_commit(["README.md"], "Initial commit")

        yield repo


def create_test_git_repo_with_history(temp_path: Path) -> GitTestRepo:
    """Create a test git repository with realistic commit history.

    Args:
        temp_path: Path where to create the repository

    Returns:
        GitTestRepo instance with commit history
    """
    repo = GitTestRepo(temp_path)

    # Initialize repository
    subprocess.run(["git", "init"], cwd=temp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=temp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=temp_path,
        check=True,
        capture_output=True,
    )

    # Create main branch history
    repo.create_file("src/main.py", "def main():\n    print('Hello, World!')\n")
    repo.add_and_commit(["src/main.py"], "Add main function")

    repo.create_file("src/utils.py", "def helper():\n    return 42\n")
    repo.add_and_commit(["src/utils.py"], "Add utility functions")

    repo.modify_file(
        "src/main.py",
        "def main():\n    print('Hello, World!')\n    print('Version 2.0')\n",
    )
    repo.add_and_commit(["src/main.py"], "Update main with version info")

    # Create feature branch
    repo.create_branch("feature-branch")

    repo.create_file("src/feature.py", "def new_feature():\n    return 'feature'\n")
    repo.add_and_commit(["src/feature.py"], "Add new feature")

    repo.modify_file(
        "src/main.py",
        "def main():\n    print('Hello, World!')\n    print('Version 2.0')\n    new_feature()\n",
    )
    repo.add_and_commit(["src/main.py"], "Integrate new feature")

    return repo


class IntegrationTestBase:
    """Base class for integration tests using real git repositories."""

    def setup_method(self) -> None:
        """Set up test method with fresh repository."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.temp_dir)
        self.git_repo = create_test_git_repo_with_history(self.repo_path)

    def teardown_method(self) -> None:
        """Clean up test repository."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def assert_file_content_equals(self, filepath: str, expected_content: str) -> None:
        """Assert that file has expected content.

        Args:
            filepath: Relative path to file
            expected_content: Expected file content
        """
        actual_content = self.git_repo.get_file_content(filepath)
        assert actual_content == expected_content, f"File {filepath} content mismatch"

    def assert_no_staged_changes(self) -> None:
        """Assert that there are no staged changes."""
        assert not self.git_repo.has_staged_changes(), "Unexpected staged changes found"

    def assert_no_unstaged_changes(self) -> None:
        """Assert that there are no unstaged changes."""
        assert not self.git_repo.has_unstaged_changes(), (
            "Unexpected unstaged changes found"
        )


# Example usage in tests
class TestGitIntegrationExample(IntegrationTestBase):
    """Example of how to use integration test utilities."""

    def test_real_git_operations(self) -> None:
        """Example test using real git operations."""
        # Create changes
        self.git_repo.modify_file(
            "src/main.py", "def main():\n    print('Modified!')\n"
        )

        # Verify changes exist
        assert self.git_repo.has_unstaged_changes()

        # Test git operations
        result = self.git_repo.git_ops.run_git_command(["status", "--porcelain"])
        assert result.returncode == 0
        assert "src/main.py" in result.stdout

        # Clean up
        self.git_repo.run_git("checkout", ".")
        self.assert_no_unstaged_changes()
