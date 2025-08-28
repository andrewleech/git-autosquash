"""Tests for security-related edge cases and path traversal protection."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.git_native_handler import GitNativeIgnoreHandler
from git_autosquash.git_worktree_handler import GitWorktreeIgnoreHandler
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod


class TestPathTraversalProtection:
    """Test path traversal and security protection."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_git_ops = MagicMock(spec=GitOps)
        self.mock_git_ops.repo_path = "/fake/repo"
        # Mock git operations to avoid actual git calls
        self.mock_git_ops._run_git_command.return_value = (True, "stash_ref_12345")
        self.mock_git_ops._run_git_command_with_input.return_value = (True, "")
        self.native_handler = GitNativeIgnoreHandler(self.mock_git_ops)
        self.worktree_handler = GitWorktreeIgnoreHandler(self.mock_git_ops)
        # Mock worktree-specific operations to focus on security validation
        self.worktree_handler._check_worktree_support = MagicMock(return_value=True)
        self.worktree_handler._create_comprehensive_backup = MagicMock(
            return_value="stash@{0}"
        )
        self.worktree_handler._create_temporary_worktree = MagicMock(
            return_value=Path("/tmp/fake_worktree")
        )
        self.worktree_handler._apply_hunks_in_worktree = MagicMock(return_value=True)
        self.worktree_handler._extract_changes_from_worktree = MagicMock(
            return_value=True
        )
        self.worktree_handler._cleanup_temporary_worktree = MagicMock(return_value=None)
        self.worktree_handler._restore_from_stash = MagicMock(return_value=True)
        self.worktree_handler._cleanup_stash = MagicMock(return_value=None)

    def test_absolute_path_rejection(self):
        """Test rejection of absolute file paths."""

        absolute_path_hunk = DiffHunk(
            file_path="/etc/passwd",  # Absolute path - should be rejected
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=absolute_path_hunk,
            target_commit="commit1",
            confidence="high",
            blame_info=[],
            targeting_method=TargetingMethod.BLAME_MATCH,
        )

        # Test both handlers
        native_result = self.native_handler.apply_ignored_hunks([mapping])
        worktree_result = self.worktree_handler.apply_ignored_hunks([mapping])

        assert native_result is False  # Should reject absolute paths
        assert worktree_result is False  # Should reject absolute paths

    def test_path_traversal_rejection(self):
        """Test rejection of path traversal attempts."""
        import platform

        traversal_paths = [
            "../../../etc/passwd",
            "subdir/../../../etc/passwd",
            "normal/../../../../../../etc/passwd",
            "dir/./../../etc/passwd",
            "dir/subdir/../../../../../../etc/passwd",
        ]

        # Add Windows-style paths on Windows systems
        if platform.system() == "Windows":
            traversal_paths.append("..\\..\\..\\windows\\system32\\config\\sam")

        for malicious_path in traversal_paths:
            # Mock git_ops to avoid the unpacking error
            self.mock_git_ops._run_git_command.return_value = (True, "stash_ref")

            traversal_hunk = DiffHunk(
                file_path=malicious_path,
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
                context_before=[],
                context_after=[],
            )

            mapping = HunkTargetMapping(
                hunk=traversal_hunk,
                target_commit="commit1",
                confidence="high",
                blame_info=[],
                targeting_method=TargetingMethod.BLAME_MATCH,
            )

            # Test both handlers
            native_result = self.native_handler.apply_ignored_hunks([mapping])
            worktree_result = self.worktree_handler.apply_ignored_hunks([mapping])

            assert native_result is False, (
                f"Native handler should reject path traversal: {malicious_path}"
            )
            assert worktree_result is False, (
                f"Worktree handler should reject path traversal: {malicious_path}"
            )

    def test_symlink_detection_and_rejection(self):
        """Test detection and rejection of symlinks in file paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create a structure: repo/safe_dir/malicious_link -> /etc
            repo_dir = temp_path / "repo"
            safe_dir = repo_dir / "safe_dir"
            safe_dir.mkdir(parents=True)

            # Create symlink pointing outside repo
            malicious_link = safe_dir / "malicious_link"
            etc_dir = Path("/etc") if Path("/etc").exists() else temp_path / "fake_etc"
            etc_dir.mkdir(exist_ok=True)

            try:
                malicious_link.symlink_to(etc_dir)
            except OSError:
                # Skip test if symlinks not supported on this system
                pytest.skip("Symlinks not supported on this system")

            # Mock git_ops to use our temp repo
            self.mock_git_ops.repo_path = str(repo_dir)

            symlink_hunk = DiffHunk(
                file_path="safe_dir/malicious_link/passwd",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
                context_before=[],
                context_after=[],
            )

            mapping = HunkTargetMapping(
                hunk=symlink_hunk,
                target_commit="commit1",
                confidence="high",
                blame_info=[],
                targeting_method=TargetingMethod.BLAME_MATCH,
            )

            # Test both handlers
            native_result = self.native_handler.apply_ignored_hunks([mapping])
            worktree_result = self.worktree_handler.apply_ignored_hunks([mapping])

            assert native_result is False  # Should reject paths with symlinks
            assert worktree_result is False  # Should reject paths with symlinks

    def test_legitimate_paths_acceptance(self):
        """Test that legitimate file paths are accepted."""
        legitimate_paths = [
            "src/main.py",
            "docs/README.md",
            "tests/test_file.py",
            "config/settings.yaml",
            "deep/nested/directory/file.txt",
            "file-with-dashes.py",
            "file_with_underscores.py",
            "file.with.dots.py",
            "UPPERCASE.FILE",
            "123numeric_start.py",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "repo"
            repo_path.mkdir()
            self.mock_git_ops.repo_path = str(repo_path)

            # Mock successful git operations
            self.mock_git_ops._run_git_command.return_value = (True, "stash_ref_12345")
            self.mock_git_ops._run_git_command_with_input.return_value = (True, "")

            for legit_path in legitimate_paths:
                # Create parent directories
                file_path = repo_path / legit_path
                file_path.parent.mkdir(parents=True, exist_ok=True)

                hunk = DiffHunk(
                    file_path=legit_path,
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
                    context_before=[],
                    context_after=[],
                )

                mapping = HunkTargetMapping(
                    hunk=hunk,
                    target_commit="commit1",
                    confidence="high",
                    blame_info=[],
                    targeting_method=TargetingMethod.BLAME_MATCH,
                )

                # Test both handlers
                native_result = self.native_handler.apply_ignored_hunks([mapping])
                worktree_result = self.worktree_handler.apply_ignored_hunks([mapping])

                assert native_result is True, (
                    f"Native handler should accept legitimate path: {legit_path}"
                )
                assert worktree_result is True, (
                    f"Worktree handler should accept legitimate path: {legit_path}"
                )

    def test_edge_case_path_formats(self):
        """Test edge case path formats that should be handled correctly."""
        edge_case_paths = [
            "./src/file.py",  # Current directory reference
            "src/./file.py",  # Current directory in middle
            "src/subdir/../file.py",  # Parent reference that stays within repo
            "",  # Empty path
            ".",  # Current directory only
            "file with spaces.py",  # Spaces in filename
            "filé-with-unicode.py",  # Unicode characters
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "repo"
            repo_path.mkdir()
            self.mock_git_ops.repo_path = str(repo_path)

            # Mock git operations to succeed
            self.mock_git_ops._run_git_command.return_value = (True, "stash_ref")
            self.mock_git_ops._run_git_command_with_input.return_value = (True, "")

            for edge_path in edge_case_paths:
                if not edge_path or edge_path == ".":
                    # Skip empty or current directory paths
                    continue

                hunk = DiffHunk(
                    file_path=edge_path,
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
                    context_before=[],
                    context_after=[],
                )

                mapping = HunkTargetMapping(
                    hunk=hunk,
                    target_commit="commit1",
                    confidence="high",
                    blame_info=[],
                    targeting_method=TargetingMethod.BLAME_MATCH,
                )

                try:
                    # Test both handlers
                    native_result = self.native_handler.apply_ignored_hunks([mapping])
                    worktree_result = self.worktree_handler.apply_ignored_hunks(
                        [mapping]
                    )

                    # Should handle without exceptions
                    assert isinstance(native_result, bool)
                    assert isinstance(worktree_result, bool)
                except Exception as e:
                    # Should not raise unhandled exceptions
                    assert False, f"Unexpected exception for path '{edge_path}': {e}"

    def test_path_validation_error_handling(self):
        """Test error handling in path validation."""
        # Mock path resolution to raise exception
        with patch("pathlib.Path.resolve") as mock_resolve:
            mock_resolve.side_effect = OSError("Mock filesystem error")

            hunk = DiffHunk(
                file_path="src/file.py",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
                context_before=[],
                context_after=[],
            )

            mapping = HunkTargetMapping(
                hunk=hunk,
                target_commit="commit1",
                confidence="high",
                blame_info=[],
                targeting_method=TargetingMethod.BLAME_MATCH,
            )

            # Test both handlers
            native_result = self.native_handler.apply_ignored_hunks([mapping])
            worktree_result = self.worktree_handler.apply_ignored_hunks([mapping])

            assert (
                native_result is False
            )  # Should fail safely on path validation errors
            assert (
                worktree_result is False
            )  # Should fail safely on path validation errors

    def test_repo_root_resolution_edge_cases(self):
        """Test edge cases in repository root resolution."""
        # Test with non-existent repo path
        self.mock_git_ops.repo_path = "/nonexistent/repo/path"
        # Mock git operations to avoid the unpacking error
        self.mock_git_ops._run_git_command.return_value = (False, "repo not found")
        # Override the worktree backup mock for this specific failure case
        self.worktree_handler._create_comprehensive_backup = MagicMock(
            return_value=None
        )

        hunk = DiffHunk(
            file_path="src/file.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk,
            target_commit="commit1",
            confidence="high",
            blame_info=[],
            targeting_method=TargetingMethod.BLAME_MATCH,
        )

        # Test both handlers
        native_result = self.native_handler.apply_ignored_hunks([mapping])
        worktree_result = self.worktree_handler.apply_ignored_hunks([mapping])

        assert native_result is False  # Should handle non-existent repo gracefully
        assert worktree_result is False  # Should handle non-existent repo gracefully

    def test_multiple_security_violations(self):
        """Test handling multiple security violations in a single call."""
        violations = [
            "/etc/passwd",  # Absolute path
            "../../../etc/shadow",  # Path traversal
            "normal/../../../../../../bin/sh",  # Path traversal in subdirectory
        ]

        mappings = []
        for violation_path in violations:
            hunk = DiffHunk(
                file_path=violation_path,
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
                context_before=[],
                context_after=[],
            )

            mapping = HunkTargetMapping(
                hunk=hunk,
                target_commit="commit1",
                confidence="high",
                blame_info=[],
                targeting_method=TargetingMethod.BLAME_MATCH,
            )
            mappings.append(mapping)

        # Test both handlers
        native_result = self.native_handler.apply_ignored_hunks(mappings)
        worktree_result = self.worktree_handler.apply_ignored_hunks(mappings)

        assert native_result is False  # Should reject on first violation
        assert worktree_result is False  # Should reject on first violation

    def test_security_with_git_operation_failures(self):
        """Test security validation when git operations fail."""
        # Mock git stash creation to fail
        self.mock_git_ops._run_git_command.return_value = (
            False,
            "stash creation failed",
        )
        # Override the worktree backup mock for this specific failure case
        self.worktree_handler._create_comprehensive_backup = MagicMock(
            return_value=None
        )

        # Use legitimate path - should pass security but fail on git operations
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "repo"
            repo_path.mkdir()
            self.mock_git_ops.repo_path = str(repo_path)

            hunk = DiffHunk(
                file_path="src/legitimate_file.py",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
                context_before=[],
                context_after=[],
            )

            mapping = HunkTargetMapping(
                hunk=hunk,
                target_commit="commit1",
                confidence="high",
                blame_info=[],
                targeting_method=TargetingMethod.BLAME_MATCH,
            )

            # Test both handlers
            native_result = self.native_handler.apply_ignored_hunks([mapping])
            worktree_result = self.worktree_handler.apply_ignored_hunks([mapping])

            assert native_result is False  # Should fail on git operations, not security
            assert (
                worktree_result is False
            )  # Should fail on git operations, not security

    def test_empty_mappings_list_security(self):
        """Test security handling with empty mappings list."""
        # Test both handlers
        native_result = self.native_handler.apply_ignored_hunks([])
        worktree_result = self.worktree_handler.apply_ignored_hunks([])

        assert (
            native_result is True
        )  # Empty list should succeed (no security violations)
        assert (
            worktree_result is True
        )  # Empty list should succeed (no security violations)

    def test_case_sensitivity_in_paths(self):
        """Test case sensitivity handling in path validation."""
        # This test may behave differently on case-insensitive filesystems
        case_variants = ["src/File.py", "src/FILE.py", "SRC/file.py", "Src/File.Py"]

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "repo"
            repo_path.mkdir()
            (repo_path / "src").mkdir()
            self.mock_git_ops.repo_path = str(repo_path)

            # Mock successful git operations
            self.mock_git_ops._run_git_command.return_value = (True, "stash_ref")
            self.mock_git_ops._run_git_command_with_input.return_value = (True, "")

            for case_variant in case_variants:
                hunk = DiffHunk(
                    file_path=case_variant,
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
                    context_before=[],
                    context_after=[],
                )

                mapping = HunkTargetMapping(
                    hunk=hunk,
                    target_commit="commit1",
                    confidence="high",
                    blame_info=[],
                    targeting_method=TargetingMethod.BLAME_MATCH,
                )

                try:
                    # Test both handlers
                    native_result = self.native_handler.apply_ignored_hunks([mapping])
                    worktree_result = self.worktree_handler.apply_ignored_hunks(
                        [mapping]
                    )

                    # Should handle without security violations
                    assert isinstance(native_result, bool)
                    assert isinstance(worktree_result, bool)
                except Exception as e:
                    assert False, (
                        f"Unexpected exception for case variant '{case_variant}': {e}"
                    )
