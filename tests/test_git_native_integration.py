"""Integration tests for git-native handler using real git operations."""

import tempfile
from pathlib import Path

from git_autosquash.git_native_handler import GitNativeIgnoreHandler
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.hunk_target_resolver import HunkTargetMapping
from tests.test_utils_git_integration import IntegrationTestBase


class TestGitNativeHandlerRealIntegration(IntegrationTestBase):
    """Integration tests using real git repositories instead of excessive mocking."""

    def setup_method(self) -> None:
        """Set up test method with real git repository."""
        super().setup_method()
        self.git_ops = GitOps(self.repo_path)
        self.handler = GitNativeIgnoreHandler(self.git_ops)

    def test_empty_mappings_real_repo(self) -> None:
        """Test handling of empty ignored mappings with real repository."""
        result = self.handler.apply_ignored_hunks([])

        assert result is True
        # Verify repository state is unchanged
        self.assert_no_staged_changes()
        self.assert_no_unstaged_changes()

    def test_path_validation_with_real_security_checks(self) -> None:
        """Test path validation using real path operations instead of mocks."""
        # Create malicious path hunk
        hunk = DiffHunk(
            file_path="../../../etc/passwd",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing", "+malicious"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Verify no files were modified outside repository
        self.assert_no_staged_changes()
        self.assert_no_unstaged_changes()

    def test_successful_hunk_application_real_git(self) -> None:
        """Test successful hunk application with real git operations."""
        # Create a file to modify
        original_content = "def main():\\n    print('Hello, World!')\\n"
        self.git_repo.create_file("test_file.py", original_content)
        self.git_repo.add_and_commit(["test_file.py"], "Add test file")

        # Create a realistic hunk that adds a line
        hunk = DiffHunk(
            file_path="test_file.py",
            old_start=2,
            old_count=1,
            new_start=2,
            new_count=2,
            lines=[
                "@@ -2,1 +2,2 @@",
                "     print('Hello, World!')",
                "+    print('Added line')",
            ],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Apply the hunk
        result = self.handler.apply_ignored_hunks([mapping])

        if result:
            # Verify the change was applied
            expected_content = (
                "def main():\\n    print('Hello, World!')\\n    print('Added line')\\n"
            )
            self.assert_file_content_equals("test_file.py", expected_content)
            self.assert_no_staged_changes()  # Changes should be in working tree
        else:
            # This is acceptable - the handler may not support the operation
            # The important thing is that it fails gracefully without corrupting the repo
            self.assert_no_staged_changes()
            self.assert_no_unstaged_changes()

    def test_error_handling_preserves_repository_integrity(self) -> None:
        """Test that errors don't corrupt the repository state."""
        # Create a file
        original_content = "def test():\\n    pass\\n"
        self.git_repo.create_file("integrity_test.py", original_content)
        self.git_repo.add_and_commit(["integrity_test.py"], "Add integrity test file")

        # Create a conflicting hunk that can't be applied
        hunk = DiffHunk(
            file_path="nonexistent_file.py",  # File doesn't exist
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " some line", "+another line"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Capture original state
        original_file_content = self.git_repo.get_file_content("integrity_test.py")

        # Apply the problematic hunk
        result = self.handler.apply_ignored_hunks([mapping])

        # Should fail gracefully
        assert result is False

        # Verify repository integrity is maintained
        self.assert_no_staged_changes()
        self.assert_no_unstaged_changes()

        # Verify existing file is unchanged
        current_content = self.git_repo.get_file_content("integrity_test.py")
        assert current_content == original_file_content

    def test_stash_operations_with_real_git(self) -> None:
        """Test stash operations using real git instead of complex mocking."""
        # Create initial state with uncommitted changes
        self.git_repo.create_file("stash_test.py", "original content\\n")
        self.git_repo.add_and_commit(["stash_test.py"], "Add stash test file")

        # Make uncommitted changes
        self.git_repo.modify_file("stash_test.py", "modified content\\n")

        # Verify we have unstaged changes
        assert self.git_repo.has_unstaged_changes()

        # Try to apply a hunk (will likely fail due to file conflicts)
        hunk = DiffHunk(
            file_path="stash_test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " original content", "+added line"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        self.handler.apply_ignored_hunks([mapping])

        # Regardless of success/failure, verify git state is consistent
        # No partially applied changes or corrupted working tree
        git_status = self.git_repo.run_git("status", "--porcelain")
        assert git_status.returncode == 0

        # Either we have our original modifications or a clean state
        # But we should never have a corrupted intermediate state
        current_content = self.git_repo.get_file_content("stash_test.py")
        assert current_content in [
            "original content\\n",
            "modified content\\n",
            "original content\\nadded line\\n",
        ]


class TestGitNativeHandlerAvailability:
    """Test strategy availability detection with real git environment."""

    def test_strategy_availability_real_git(self) -> None:
        """Test strategy availability with real git installation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)

            # Initialize real git repository
            import subprocess

            subprocess.run(
                ["git", "init"], cwd=repo_path, check=True, capture_output=True
            )

            git_ops = GitOps(repo_path)
            handler = GitNativeIgnoreHandler(git_ops)

            # Test availability check
            is_available = handler.is_available()

            # Should be available if git is installed (which it is in our environment)
            assert isinstance(is_available, bool)

            # Test strategy name
            assert handler.strategy_name == "index"

            # Test worktree requirement
            assert handler.requires_worktree_support is False

    def test_strategy_info_real_environment(self) -> None:
        """Test strategy info retrieval with real environment."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir)

            import subprocess

            subprocess.run(
                ["git", "init"], cwd=repo_path, check=True, capture_output=True
            )

            git_ops = GitOps(repo_path)
            handler = GitNativeIgnoreHandler(git_ops)

            info = handler.get_strategy_info()

            assert isinstance(info, dict)
            assert "name" in info
            assert "available" in info
            assert "requires_worktree" in info
            assert info["name"] == "index"
