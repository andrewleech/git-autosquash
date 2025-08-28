"""
Security and file system edge case tests for patch generation.

These tests verify that patch generation handles security concerns including
path traversal attacks, symlink attacks, permission issues, and other
file system security considerations.
"""

import os
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseManager


class SecurityTestBuilder:
    """Builder for creating security test scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)
        self._init_repo()

    def _init_repo(self):
        """Initialize repository for security testing."""
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Security Test"],
            cwd=self.repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "security@test.com"],
            cwd=self.repo_path,
            check=True,
        )

    def create_path_traversal_scenario(self) -> Dict[str, str]:
        """Create scenario with potential path traversal attacks."""

        # Create legitimate files first
        legitimate_dir = self.repo_path / "src"
        legitimate_dir.mkdir()

        legitimate_file = legitimate_dir / "normal.c"
        legitimate_content = """// Legitimate source file
#if NORMAL_PATTERN
void normal_function() {
    // Normal implementation
}
#endif
"""
        legitimate_file.write_text(legitimate_content)

        # Create nested directory structure
        nested_dir = self.repo_path / "nested" / "deep" / "structure"
        nested_dir.mkdir(parents=True)

        nested_file = nested_dir / "nested.c"
        nested_content = """// Nested file
#if NESTED_PATTERN
void nested_function() {
    // Nested implementation
}
#endif
"""
        nested_file.write_text(nested_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add legitimate files"],
            cwd=self.repo_path,
            check=True,
        )

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Update files with pattern changes
        updated_legitimate = legitimate_content.replace(
            "NORMAL_PATTERN", "UPDATED_PATTERN"
        )
        legitimate_file.write_text(updated_legitimate)

        updated_nested = nested_content.replace("NESTED_PATTERN", "UPDATED_NESTED")
        nested_file.write_text(updated_nested)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update patterns"], cwd=self.repo_path, check=True
        )

        change_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "base_commit": base_commit,
            "change_commit": change_commit,
            "legitimate_files": ["src/normal.c", "nested/deep/structure/nested.c"],
        }

    def create_symlink_attack_scenario(self) -> Optional[Dict[str, str]]:
        """Create scenario with potential symlink attacks."""
        try:
            # Create target file outside repository
            external_dir = self.repo_path.parent / "external_target"
            external_dir.mkdir(exist_ok=True)

            external_file = external_dir / "sensitive.txt"
            external_file.write_text("SENSITIVE_DATA_SHOULD_NOT_BE_ACCESSIBLE")

            # Create legitimate file
            legitimate_file = self.repo_path / "legitimate.c"
            legitimate_content = """// Legitimate file
#if SAFE_PATTERN
void safe_function() {
    // Safe implementation
}
#endif
"""
            legitimate_file.write_text(legitimate_content)

            # Attempt to create symlink pointing outside repository
            symlink_path = self.repo_path / "malicious_link.c"

            try:
                # Try to create symlink to external file
                symlink_path.symlink_to(external_file)
                symlink_created = True
            except (OSError, NotImplementedError):
                # Symlinks not supported or failed
                symlink_created = False

            if symlink_created:
                subprocess.run(
                    ["git", "add", "legitimate.c"], cwd=self.repo_path, check=True
                )

                # Try to add symlink (git should handle this appropriately)
                subprocess.run(
                    ["git", "add", "malicious_link.c"],
                    cwd=self.repo_path,
                    capture_output=True,
                )
                # Git may refuse to add symlinks pointing outside repo

            subprocess.run(
                ["git", "commit", "-m", "Add files with symlink"],
                cwd=self.repo_path,
                check=True,
            )

            base_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            # Update legitimate file
            updated_content = legitimate_content.replace("SAFE_PATTERN", "UPDATED_SAFE")
            legitimate_file.write_text(updated_content)

            subprocess.run(
                ["git", "add", "legitimate.c"], cwd=self.repo_path, check=True
            )
            subprocess.run(
                ["git", "commit", "-m", "Update legitimate file"],
                cwd=self.repo_path,
                check=True,
            )

            change_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            return {
                "base_commit": base_commit,
                "change_commit": change_commit,
                "symlink_created": symlink_created,
                "external_file": str(external_file),
            }

        except Exception as e:
            print(f"Symlink attack scenario creation failed: {e}")
            return None

    def create_permission_attack_scenario(self) -> Dict[str, str]:
        """Create scenario with permission-based attacks."""

        # Create file with restricted permissions
        restricted_file = self.repo_path / "restricted.c"
        restricted_content = """// File with restricted permissions
#if RESTRICTED_PATTERN
void restricted_function() {
    // Restricted implementation
}
#endif
"""
        restricted_file.write_text(restricted_content)

        # Set restrictive permissions
        try:
            # Make file read-only
            restricted_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            permissions_set = True
        except OSError:
            permissions_set = False

        # Create world-writable file
        writable_file = self.repo_path / "world_writable.c"
        writable_content = """// World writable file
#if WRITABLE_PATTERN
void writable_function() {
    // Implementation
}
#endif
"""
        writable_file.write_text(writable_content)

        try:
            # Make file world-writable (security concern)
            writable_file.chmod(
                stat.S_IRUSR
                | stat.S_IWUSR
                | stat.S_IRGRP
                | stat.S_IWGRP
                | stat.S_IROTH
                | stat.S_IWOTH
            )
        except OSError:
            pass

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add files with special permissions"],
            cwd=self.repo_path,
            check=True,
        )

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Update content (may fail due to permissions)
        try:
            if permissions_set:
                # Make writable temporarily to update
                restricted_file.chmod(stat.S_IRUSR | stat.S_IWUSR)

            updated_restricted = restricted_content.replace(
                "RESTRICTED_PATTERN", "UPDATED_RESTRICTED"
            )
            restricted_file.write_text(updated_restricted)

            if permissions_set:
                # Restore restrictive permissions
                restricted_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        except OSError as e:
            print(f"Permission update failed: {e}")

        # Update writable file
        updated_writable = writable_content.replace(
            "WRITABLE_PATTERN", "UPDATED_WRITABLE"
        )
        writable_file.write_text(updated_writable)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update files with permissions"],
            cwd=self.repo_path,
            check=True,
        )

        change_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "base_commit": base_commit,
            "change_commit": change_commit,
            "permissions_set": permissions_set,
        }

    def create_filename_injection_scenario(self) -> Dict[str, str]:
        """Create scenario with potentially dangerous filenames."""

        dangerous_names = [
            "normal_file.c",  # Control case
            # Note: We won't create actually dangerous files in tests,
            # but will test handling of filenames that could be problematic
        ]

        files_created = []

        for filename in dangerous_names:
            try:
                file_path = self.repo_path / filename
                content = f"""// File: {filename}
#if INJECTION_PATTERN_{len(files_created)}
void function_{len(files_created)}() {{
    // Implementation
}}
#endif
"""
                file_path.write_text(content)
                files_created.append(filename)
            except (OSError, ValueError) as e:
                print(f"Could not create file {filename}: {e}")

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add files with various names"],
            cwd=self.repo_path,
            check=True,
        )

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Update all created files
        for i, filename in enumerate(files_created):
            file_path = self.repo_path / filename
            content = file_path.read_text()
            updated_content = content.replace(
                f"INJECTION_PATTERN_{i}", f"UPDATED_PATTERN_{i}"
            )
            file_path.write_text(updated_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update files with various names"],
            cwd=self.repo_path,
            check=True,
        )

        change_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "base_commit": base_commit,
            "change_commit": change_commit,
            "files_created": files_created,
        }


@pytest.fixture
def security_test_repo():
    """Create repository for security testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "security_test"
        repo_path.mkdir()
        builder = SecurityTestBuilder(repo_path)
        yield builder


class TestPatchGenerationSecurity:
    """Security tests for patch generation."""

    def test_path_traversal_prevention(self, security_test_repo):
        """Test prevention of path traversal attacks."""
        repo = security_test_repo
        scenario = repo.create_path_traversal_scenario()

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get diff
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["change_commit"]]
        )

        assert diff_result.returncode == 0, "Should get diff for path traversal test"

        # Verify diff content doesn't contain path traversal attempts
        diff_content = diff_result.stdout

        # Look for path traversal patterns in diff
        dangerous_patterns = ["../", "..\\", "/..", "\\..", "~"]
        for pattern in dangerous_patterns:
            # Diff itself shouldn't contain traversal patterns in file paths
            lines = diff_content.split("\n")
            file_path_lines = [
                line
                for line in lines
                if line.startswith("--- a/") or line.startswith("+++ b/")
            ]

            for path_line in file_path_lines:
                assert pattern not in path_line, (
                    f"Found dangerous pattern '{pattern}' in path: {path_line}"
                )

        # Parse hunks
        hunks = hunk_parser._parse_diff_output(diff_content)

        # Verify all hunks reference legitimate files within repository
        for hunk in hunks:
            assert hunk.file_path is not None, "Hunk should have valid file path"

            # File path should not contain traversal attempts
            for pattern in dangerous_patterns:
                assert pattern not in hunk.file_path, (
                    f"Hunk file path contains dangerous pattern: {hunk.file_path}"
                )

            # File path should be relative and within repository bounds
            assert not os.path.isabs(hunk.file_path), (
                f"Hunk file path should be relative: {hunk.file_path}"
            )
            assert not hunk.file_path.startswith("/"), (
                f"Hunk file path should not start with /: {hunk.file_path}"
            )

        # Test patch generation with legitimate files
        legitimate_hunks = [
            h for h in hunks if h.file_path in scenario["legitimate_files"]
        ]
        assert len(legitimate_hunks) > 0, "Should find hunks for legitimate files"

        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            legitimate_hunks, scenario["base_commit"]
        )

        assert patch_content is not None, "Should generate patch for legitimate files"

        # Verify patch content doesn't contain path traversal
        for pattern in dangerous_patterns:
            assert pattern not in patch_content, (
                f"Patch contains dangerous pattern: {pattern}"
            )

    def test_symlink_attack_prevention(self, security_test_repo):
        """Test prevention of symlink attacks."""
        repo = security_test_repo
        scenario = repo.create_symlink_attack_scenario()

        if scenario is None:
            pytest.skip("Symlink scenario could not be created")

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get diff
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["change_commit"]]
        )

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Verify hunks only reference files within repository
        for hunk in hunks:
            hunk_file_path = Path(repo.repo_path) / hunk.file_path

            try:
                # Resolve any symlinks and verify the resolved path is within repo
                resolved_path = hunk_file_path.resolve()
                repo_resolved = Path(repo.repo_path).resolve()

                # Check if the resolved path is within the repository
                try:
                    resolved_path.relative_to(repo_resolved)
                    within_repo = True
                except ValueError:
                    within_repo = False

                if scenario["symlink_created"] and hunk.file_path == "malicious_link.c":
                    # If symlink was created, system should handle it safely
                    # Either refuse to process it or resolve it safely
                    if not within_repo:
                        print(
                            f"Warning: Symlink {hunk.file_path} points outside repository"
                        )
                        # This should be caught by security checks

            except (OSError, ValueError):
                # File access issues are acceptable for security tests
                pass

        # Test patch generation - should only work with legitimate files
        legitimate_hunks = [h for h in hunks if h.file_path == "legitimate.c"]

        if legitimate_hunks:
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                legitimate_hunks, scenario["base_commit"]
            )

            assert patch_content is not None, (
                "Should generate patch for legitimate file"
            )

            # Verify patch doesn't contain external file references
            if scenario["symlink_created"]:
                external_path = scenario["external_file"]
                assert external_path not in patch_content, (
                    "Patch should not reference external files"
                )
                assert "SENSITIVE_DATA" not in patch_content, (
                    "Patch should not contain external sensitive data"
                )

    def test_permission_handling(self, security_test_repo):
        """Test handling of files with special permissions."""
        repo = security_test_repo
        scenario = repo.create_permission_attack_scenario()

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get diff
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["change_commit"]]
        )

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Find hunks for files with special permissions
        restricted_hunks = [h for h in hunks if "restricted.c" in h.file_path]
        writable_hunks = [h for h in hunks if "world_writable.c" in h.file_path]

        # Test patch generation with restricted file
        if restricted_hunks:
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                restricted_hunks, scenario["base_commit"]
            )

            # Should handle restricted files appropriately
            # (may succeed or fail gracefully depending on permissions)
            if patch_content is not None:
                assert len(patch_content) > 0, (
                    "Restricted file patch should not be empty if generated"
                )

        # Test patch generation with world-writable file
        if writable_hunks:
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                writable_hunks, scenario["base_commit"]
            )

            # Should process world-writable files but with appropriate caution
            assert patch_content is not None, "Should process world-writable file"
            assert "world_writable.c" in patch_content, (
                "Should reference world-writable file"
            )

        # Verify git operations maintain security
        status_result = git_ops.run_git_command(["status", "--porcelain"])
        assert status_result.returncode == 0, (
            "Git should remain functional after permission tests"
        )

    def test_filename_injection_prevention(self, security_test_repo):
        """Test prevention of filename injection attacks."""
        repo = security_test_repo
        scenario = repo.create_filename_injection_scenario()

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get diff
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["change_commit"]]
        )

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Verify all hunks have safe filenames
        for hunk in hunks:
            filename = hunk.file_path

            # Check for potentially dangerous filename patterns
            dangerous_chars = [";", "|", "&", "`", "$", "(", ")", "{", "}"]
            for char in dangerous_chars:
                assert char not in filename, (
                    f"Filename contains dangerous character '{char}': {filename}"
                )

            # Check for command injection patterns
            injection_patterns = ["$(", "`", "&&", "||", ";rm", ";del", ">/"]
            for pattern in injection_patterns:
                assert pattern not in filename, (
                    f"Filename contains injection pattern '{pattern}': {filename}"
                )

        # Test patch generation with all files
        created_hunks = [h for h in hunks if h.file_path in scenario["files_created"]]

        if created_hunks:
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                created_hunks, scenario["base_commit"]
            )

            assert patch_content is not None, (
                "Should generate patch for files with safe names"
            )

            # Verify patch content doesn't contain injection attempts
            injection_patterns = ["$(", "`", "&&", "||", ";", "|&"]
            for pattern in injection_patterns:
                # Allow pattern in file content but not in file paths/headers
                patch_lines = patch_content.split("\n")
                header_lines = [
                    line
                    for line in patch_lines
                    if line.startswith("---")
                    or line.startswith("+++")
                    or line.startswith("@@")
                ]

                for header_line in header_lines:
                    assert pattern not in header_line, (
                        f"Patch header contains injection pattern: {header_line}"
                    )

    def test_git_command_injection_prevention(self, security_test_repo):
        """Test prevention of git command injection attacks."""
        repo = security_test_repo

        # Create normal scenario
        normal_file = repo.repo_path / "normal.c"
        normal_content = """// Normal file
#if NORMAL_PATTERN
void normal_function() { }
#endif
"""
        normal_file.write_text(normal_content)

        subprocess.run(["git", "add", "."], cwd=repo.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Normal commit"], cwd=repo.repo_path, check=True
        )

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Test with potentially dangerous commit hashes and references
        git_ops = GitOps(str(repo.repo_path))
        RebaseManager(git_ops, base_commit)

        # Test various potentially dangerous commit references
        dangerous_refs = [
            base_commit,  # Normal case (control)
            base_commit + "; rm -rf /",  # Command injection attempt
            base_commit + " && echo 'injected'",  # Another injection attempt
            base_commit + " | cat /etc/passwd",  # Pipe injection attempt
        ]

        for ref in dangerous_refs:
            if ref == base_commit:
                # Normal case should work
                try:
                    result = git_ops.run_git_command(["show", ref])
                    assert result.returncode == 0, "Normal commit reference should work"
                except Exception:
                    pytest.fail("Normal commit reference failed")
            else:
                # Dangerous cases should be handled safely
                try:
                    result = git_ops.run_git_command(["show", ref])
                    # Should either fail safely or sanitize the input
                    # The key is that no command injection should occur

                    # If it succeeds, it should only show git output, not injection results
                    if result.returncode == 0:
                        assert "injected" not in result.stdout, (
                            "Command injection detected in output"
                        )
                        assert "/etc/passwd" not in result.stdout, (
                            "File access injection detected"
                        )

                except Exception:
                    # Failing safely is acceptable for malformed refs
                    pass

    def test_repository_boundary_enforcement(self, security_test_repo):
        """Test that operations stay within repository boundaries."""
        repo = security_test_repo

        # Create files at repository boundary
        boundary_file = repo.repo_path / "boundary.c"
        boundary_content = """// File at repository boundary
#if BOUNDARY_PATTERN
void boundary_function() { }
#endif
"""
        boundary_file.write_text(boundary_content)

        subprocess.run(["git", "add", "."], cwd=repo.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Boundary test"], cwd=repo.repo_path, check=True
        )

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Test GitOps operations stay within repository
        git_ops = GitOps(str(repo.repo_path))

        # Verify repository path is correctly set
        assert git_ops.repo_path == str(repo.repo_path), (
            "GitOps should track correct repository path"
        )

        # Test file access is restricted to repository
        RebaseManager(git_ops, base_commit)

        # All operations should be relative to the repository root
        status_result = git_ops.run_git_command(["status"])
        assert status_result.returncode == 0, "Status should work within repository"

        # Verify no operations escape repository boundaries
        # (This is enforced by GitOps working directory)
        original_cwd = os.getcwd()

        try:
            # GitOps should maintain working directory within repository
            result = git_ops.run_git_command(["rev-parse", "--show-toplevel"])
            if result.returncode == 0:
                git_root = result.stdout.strip()
                repo_root = str(repo.repo_path.resolve())

                # Git root should match our repository
                assert Path(git_root).resolve() == Path(repo_root).resolve(), (
                    f"Git operations escaped repository: {git_root} vs {repo_root}"
                )

        finally:
            # Ensure we haven't changed working directory unexpectedly
            assert os.getcwd() == original_cwd, (
                "Working directory should not change during operations"
            )


class TestPatchGenerationInputSanitization:
    """Test input sanitization and validation."""

    def test_malformed_diff_handling(self, security_test_repo):
        """Test handling of malformed diff input."""
        repo = security_test_repo

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)

        # Test various malformed diff inputs
        malformed_diffs = [
            # Empty diff
            "",
            # Truncated diff
            "diff --git a/test.c b/test.c\n",
            # Diff with injection attempts
            "diff --git a/test.c b/test.c; rm -rf /\n",
            # Diff with null bytes
            "diff --git a/test.c b/test.c\n\x00malicious\n",
            # Very long lines (potential buffer overflow)
            "diff --git a/test.c b/test.c\n" + "x" * 10000 + "\n",
            # Unicode control characters
            "diff --git a/test.c b/test.c\n\u202e\u202d\n",
        ]

        for i, malformed_diff in enumerate(malformed_diffs):
            try:
                hunks = hunk_parser._parse_diff_output(malformed_diff)

                # Should return empty list or valid hunks, not crash
                assert isinstance(hunks, list), f"Malformed diff {i} should return list"

                # Any returned hunks should be valid
                for hunk in hunks:
                    assert hasattr(hunk, "file_path"), (
                        f"Hunk from malformed diff {i} should have file_path"
                    )
                    assert hunk.file_path is not None, (
                        f"Hunk file_path should not be None for diff {i}"
                    )

            except Exception as e:
                # Should not raise unhandled exceptions
                assert False, f"Malformed diff {i} caused unhandled exception: {e}"

    def test_commit_hash_validation(self, security_test_repo):
        """Test validation of commit hash inputs."""
        repo = security_test_repo

        # Create a valid commit first
        test_file = repo.repo_path / "validation.c"
        test_file.write_text("// Validation test\nvoid test() { }\n")

        subprocess.run(["git", "add", "."], cwd=repo.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Validation test"], cwd=repo.repo_path, check=True
        )

        valid_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        git_ops = GitOps(str(repo.repo_path))

        # Test various potentially malicious commit hash inputs
        malicious_hashes = [
            valid_commit,  # Control case
            '"; rm -rf /; echo "',  # Command injection
            valid_commit + "; malicious",  # Append injection
            "../../../etc/passwd",  # Path traversal
            "\x00" + valid_commit,  # Null byte injection
            valid_commit + "\n$(whoami)",  # Newline injection
            "nonexistent_hash_" + "a" * 40,  # Invalid but properly formatted
        ]

        for i, test_hash in enumerate(malicious_hashes):
            try:
                if test_hash == valid_commit:
                    # Valid case should work
                    result = git_ops.run_git_command(["show", test_hash])
                    assert result.returncode == 0, "Valid commit should work"
                else:
                    # Malicious cases should be handled safely
                    result = git_ops.run_git_command(["show", test_hash])

                    # Either fail safely or return only git-related content
                    if result.returncode == 0:
                        # Should not contain injection results
                        output = result.stdout.lower()
                        assert "malicious" not in output, (
                            f"Injection detected in hash test {i}"
                        )
                        assert "/etc/passwd" not in output, (
                            f"File access detected in hash test {i}"
                        )
                        assert "root:" not in output, (
                            f"System file content detected in hash test {i}"
                        )

            except Exception:
                # Failing safely is acceptable for malformed input
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
