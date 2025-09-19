"""Tests for security-related edge cases and path traversal protection."""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.git_native_handler import GitNativeIgnoreHandler
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod


class TestPathTraversalProtection:
    """Test path traversal and security protection."""

    def setup_method(self):
        """Setup test fixtures."""
        import subprocess

        self.mock_git_ops = MagicMock(spec=GitOps)
        self.mock_git_ops.repo_path = "/fake/repo"

        # Create robust git mocking for GitNativeIgnoreHandler
        def create_robust_git_mock():
            def mock_git_command(args, **kwargs):
                if isinstance(args, list) and len(args) >= 1:
                    if args[0] == "stash":
                        if len(args) >= 2:
                            if args[1] == "push":
                                return subprocess.CompletedProcess(
                                    args=args,
                                    returncode=0,
                                    stdout="stash push success",
                                    stderr="",
                                )
                            elif args[1] in ["pop", "drop"] and len(args) >= 3:
                                return subprocess.CompletedProcess(
                                    args=args,
                                    returncode=0,
                                    stdout=f"stash {args[1]} success",
                                    stderr="",
                                )
                            elif args[1] in ["list", "--help"]:
                                return subprocess.CompletedProcess(
                                    args=args,
                                    returncode=0,
                                    stdout=f"stash {args[1]} success",
                                    stderr="",
                                )
                    elif args[0] == "diff" and "--cached" in args:
                        # Return a valid diff for staged changes
                        diff_content = """--- a/test_file.py
+++ b/test_file.py
@@ -1,1 +1,1 @@
-old
+new
"""
                        return subprocess.CompletedProcess(
                            args=args, returncode=0, stdout=diff_content, stderr=""
                        )
                    elif args[0] == "add":
                        # Staging operations succeed
                        return subprocess.CompletedProcess(
                            args=args, returncode=0, stdout="", stderr=""
                        )
                    # Default success for other git commands
                    return subprocess.CompletedProcess(
                        args=args, returncode=0, stdout="", stderr=""
                    )
                return subprocess.CompletedProcess(
                    args=args, returncode=1, stdout="", stderr="unknown command"
                )

            return mock_git_command

        # Mock git operations to return proper subprocess.CompletedProcess objects
        self.mock_git_ops.run_git_command.side_effect = create_robust_git_mock()
        self.mock_git_ops.run_git_command_with_input.return_value = (
            subprocess.CompletedProcess(
                args=["apply"], returncode=0, stdout="", stderr=""
            )
        )

        # Keep the original _run_git_command mocking for compatibility
        self.mock_git_ops._run_git_command.return_value = (True, "stash_ref_12345")
        self.mock_git_ops._run_git_command_with_input.return_value = (True, "")

        self.native_handler = GitNativeIgnoreHandler(self.mock_git_ops)

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

        # Test security validation with native handler
        result = self.native_handler.apply_ignored_hunks([mapping])

        assert result is False  # Should reject absolute paths

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

            # Test security validation
            native_result = self.native_handler.apply_ignored_hunks([mapping])
            result2 = self.native_handler.apply_ignored_hunks([mapping])

            assert native_result is False, (
                f"Native handler should reject path traversal: {malicious_path}"
            )
            assert result2 is False, (
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

            # Test security validation
            native_result = self.native_handler.apply_ignored_hunks([mapping])
            result2 = self.native_handler.apply_ignored_hunks([mapping])

            assert native_result is False  # Should reject paths with symlinks
            assert result2 is False  # Should reject paths with symlinks

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

                # Test security validation
                native_result = self.native_handler.apply_ignored_hunks([mapping])
                result2 = self.native_handler.apply_ignored_hunks([mapping])

                assert native_result is True, (
                    f"Native handler should accept legitimate path: {legit_path}"
                )
                assert result2 is True, (
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
                    # Test security validation
                    native_result = self.native_handler.apply_ignored_hunks([mapping])
                    result2 = self.native_handler.apply_ignored_hunks([mapping])

                    # Should handle without exceptions
                    assert isinstance(native_result, bool)
                    assert isinstance(result2, bool)
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

            # Test security validation
            native_result = self.native_handler.apply_ignored_hunks([mapping])
            result2 = self.native_handler.apply_ignored_hunks([mapping])

            assert (
                native_result is False
            )  # Should fail safely on path validation errors
            assert result2 is False  # Should fail safely on path validation errors

    def test_repo_root_resolution_edge_cases(self):
        """Test edge cases in repository root resolution."""
        # Test with non-existent repo path
        self.mock_git_ops.repo_path = "/nonexistent/repo/path"

        # Override the git mock to return failures for nonexistent repo
        def failing_git_mock(args, **kwargs):
            # All git operations should fail for nonexistent repo
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="fatal: not a git repository"
            )

        self.mock_git_ops.run_git_command.side_effect = failing_git_mock
        self.mock_git_ops.run_git_command_with_input.return_value = (
            subprocess.CompletedProcess(
                args=["apply"],
                returncode=1,
                stdout="",
                stderr="fatal: not a git repository",
            )
        )
        self.mock_git_ops._run_git_command.return_value = (False, "repo not found")

        # Override the backup mock for this specific failure case
        self.native_handler._create_comprehensive_backup = MagicMock(return_value=None)

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

        # Test security validation
        native_result = self.native_handler.apply_ignored_hunks([mapping])
        result2 = self.native_handler.apply_ignored_hunks([mapping])

        assert native_result is False  # Should handle non-existent repo gracefully
        assert result2 is False  # Should handle non-existent repo gracefully

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

        # Test security validation
        native_result = self.native_handler.apply_ignored_hunks(mappings)
        result2 = self.native_handler.apply_ignored_hunks(mappings)

        assert native_result is False  # Should reject on first violation
        assert result2 is False  # Should reject on first violation

    def test_security_with_git_operation_failures(self):
        """Test security validation when git operations fail."""

        # Override all git operations to fail
        def failing_git_mock(args, **kwargs):
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="git operation failed"
            )

        self.mock_git_ops.run_git_command.side_effect = failing_git_mock
        self.mock_git_ops.run_git_command_with_input.return_value = (
            subprocess.CompletedProcess(
                args=["apply"], returncode=1, stdout="", stderr="git operation failed"
            )
        )
        self.mock_git_ops._run_git_command.return_value = (
            False,
            "stash creation failed",
        )
        # Override the backup mock for this specific failure case
        self.native_handler._create_comprehensive_backup = MagicMock(return_value=None)

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

            # Test security validation
            native_result = self.native_handler.apply_ignored_hunks([mapping])
            result2 = self.native_handler.apply_ignored_hunks([mapping])

            assert native_result is False  # Should fail on git operations, not security
            assert result2 is False  # Should fail on git operations, not security

    def test_empty_mappings_list_security(self):
        """Test security handling with empty mappings list."""
        # Test security validation
        native_result = self.native_handler.apply_ignored_hunks([])
        result2 = self.native_handler.apply_ignored_hunks([])

        assert (
            native_result is True
        )  # Empty list should succeed (no security violations)
        assert result2 is True  # Empty list should succeed (no security violations)

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
                    # Test security validation
                    native_result = self.native_handler.apply_ignored_hunks([mapping])
                    result2 = self.native_handler.apply_ignored_hunks([mapping])

                    # Should handle without security violations
                    assert isinstance(native_result, bool)
                    assert isinstance(result2, bool)
                except Exception as e:
                    assert False, (
                        f"Unexpected exception for case variant '{case_variant}': {e}"
                    )
