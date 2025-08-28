"""
Regression tests for patch generation functionality.

This module ensures that the context-aware patch generation fix doesn't break
existing functionality and properly handles edge cases and error conditions.
"""

import tempfile
import subprocess
from pathlib import Path
from typing import Dict
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseManager


class TestPatchGenerationRegression:
    """Regression tests to ensure existing functionality remains intact."""

    def test_single_hunk_unchanged(self, temp_repo_single):
        """Verify single hunk scenarios work exactly as before."""

        commits = temp_repo_single.create_single_hunk_scenario()

        git_ops = temp_repo_single.git_ops
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get diff from source commit
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )
        assert diff_result.returncode == 0

        # Parse hunks
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)
        file_hunks = [h for h in hunks if h.file_path == "simple.txt"]

        assert len(file_hunks) == 1, f"Should have exactly 1 hunk: {len(file_hunks)}"

        # Generate patch
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            file_hunks, commits["target_commit"]
        )

        assert patch_content is not None

        # Should have exactly 1 hunk header
        hunk_headers = [
            line for line in patch_content.split("\n") if line.startswith("@@")
        ]
        assert len(hunk_headers) == 1, f"Should have 1 hunk header: {len(hunk_headers)}"

        # Patch should apply cleanly
        git_ops.run_git_command(["checkout", commits["target_commit"]])

        patch_file = temp_repo_single.repo_path / "test.patch"
        patch_file.write_text(patch_content)

        apply_result = git_ops.run_git_command(["apply", str(patch_file)])
        assert apply_result.returncode == 0, (
            f"Single hunk patch failed: {apply_result.stderr}"
        )

    def test_different_files_work(self, temp_repo_multifile):
        """Test that hunks in different files work correctly."""

        commits = temp_repo_multifile.create_multifile_scenario()

        git_ops = temp_repo_multifile.git_ops
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get diff from source commit
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Should have hunks for multiple files
        file_paths = {h.file_path for h in hunks}
        assert len(file_paths) >= 2, f"Should modify multiple files: {file_paths}"

        # Each file should be processed independently
        for file_path in file_paths:
            file_hunks = [h for h in hunks if h.file_path == file_path]

            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                file_hunks, commits["target_commit"]
            )

            assert patch_content is not None, f"Should generate patch for {file_path}"

    def test_api_compatibility(self, temp_repo_single):
        """Ensure all existing RebaseManager methods still work."""

        commits = temp_repo_single.create_single_hunk_scenario()
        git_ops = temp_repo_single.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Test that old methods still exist and work
        assert hasattr(rebase_manager, "_create_corrected_hunk")
        assert hasattr(rebase_manager, "_create_corrected_patch_for_hunks")
        assert hasattr(rebase_manager, "_consolidate_hunks_by_file")
        assert hasattr(rebase_manager, "_extract_hunk_changes")
        assert hasattr(rebase_manager, "_find_target_with_context")

        # Test method signatures are compatible
        hunk_parser = HunkParser(git_ops)
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        if hunks:
            # Test old single hunk method still works
            old_patch = rebase_manager._create_corrected_hunk(
                hunks[0], commits["target_commit"]
            )
            assert old_patch is not None or len(hunks[0].old_lines) == 0

            # Test new multi-hunk method works
            new_patch = rebase_manager._create_corrected_patch_for_hunks(
                [hunks[0]], commits["target_commit"]
            )
            assert new_patch is not None or len(hunks[0].old_lines) == 0

    def test_backwards_compatible_hunk_format(self, temp_repo_single):
        """Test that existing hunk formats are still supported."""

        commits = temp_repo_single.create_single_hunk_scenario()
        git_ops = temp_repo_single.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get a real hunk
        hunk_parser = HunkParser(git_ops)
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        if hunks:
            hunk = hunks[0]

            # Test that hunk has expected attributes
            assert hasattr(hunk, "file_path")
            assert hasattr(hunk, "old_lines")
            assert hasattr(hunk, "new_lines")
            assert hasattr(hunk, "old_start")
            assert hasattr(hunk, "new_start")

            # Test change extraction works with real hunk
            changes = rebase_manager._extract_hunk_changes(hunk)
            assert isinstance(changes, list)

    def test_no_regression_in_performance(self, temp_repo_performance):
        """Test that performance hasn't regressed for normal cases."""

        import time

        commits = temp_repo_performance.create_large_file_scenario()

        git_ops = temp_repo_performance.git_ops
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get hunks
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        file_hunks = [h for h in hunks if h.file_path == "large_file.txt"]

        # Time the patch generation
        start_time = time.time()
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            file_hunks, commits["target_commit"]
        )
        end_time = time.time()

        # Should complete in reasonable time (< 2 seconds for large file)
        elapsed = end_time - start_time
        assert elapsed < 2.0, f"Patch generation too slow: {elapsed:.3f}s"

        # Should still generate valid patch
        if file_hunks:
            assert patch_content is not None, "Should generate patch for large file"


class TestPatchGenerationErrorHandling:
    """Test error conditions and edge cases."""

    def test_handles_binary_files_gracefully(self, temp_repo_binary):
        """Test that binary files don't crash the system."""

        commits = temp_repo_binary.create_binary_file_scenario()

        git_ops = temp_repo_binary.git_ops
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get diff (may include binary file marker)
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )

        # Should not crash when parsing
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Should handle gracefully (may return empty hunks for binary)
        binary_hunks = [h for h in hunks if h.file_path.endswith(".bin")]

        # If binary hunks found, patch generation should handle gracefully
        for hunk in binary_hunks:
            try:
                patch = rebase_manager._create_corrected_patch_for_hunks(
                    [hunk], commits["target_commit"]
                )
                # Should either succeed or return None, but not crash
                assert patch is None or isinstance(patch, str)
            except Exception as e:
                pytest.fail(f"Binary file handling crashed: {e}")

    def test_handles_file_permissions_gracefully(self, temp_repo_single):
        """Test behavior when file permissions prevent reading."""

        commits = temp_repo_single.create_single_hunk_scenario()
        git_ops = temp_repo_single.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Checkout target commit
        git_ops.run_git_command(["checkout", commits["target_commit"]])

        # Test with simulated permission error (empty file_lines)
        change = {"old_line": "test", "new_line": "changed"}
        result = rebase_manager._find_target_with_context(change, [], set())

        # Should handle gracefully
        assert result is None, "Should return None for inaccessible file"

    def test_handles_corrupted_hunks(self, temp_repo_single):
        """Test behavior with malformed hunk data."""

        commits = temp_repo_single.create_single_hunk_scenario()
        git_ops = temp_repo_single.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Create mock hunk with missing data
        from git_autosquash.diff_hunk import DiffHunk

        corrupted_hunk = DiffHunk(
            file_path="test.txt",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            old_lines=[],  # Empty - corrupted
            new_lines=[],  # Empty - corrupted
        )

        # Should handle gracefully
        try:
            patch = rebase_manager._create_corrected_patch_for_hunks(
                [corrupted_hunk], commits["target_commit"]
            )
            # Should either succeed or return None, but not crash
            assert patch is None or isinstance(patch, str)
        except Exception as e:
            pytest.fail(f"Corrupted hunk handling crashed: {e}")

    def test_handles_missing_target_commit(self, temp_repo_single):
        """Test behavior when target commit doesn't exist."""

        commits = temp_repo_single.create_single_hunk_scenario()

        git_ops = temp_repo_single.git_ops
        HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Create a hunk
        diff_result = git_ops.run_git_command(["log", "--oneline", "-1"])
        if diff_result.returncode == 0:
            fake_commit = "nonexistent123456789abcdef"

            # Create minimal hunk
            from git_autosquash.diff_hunk import DiffHunk

            test_hunk = DiffHunk(
                file_path="test.txt",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                old_lines=["old content"],
                new_lines=["new content"],
            )

            # Should handle missing commit gracefully
            patch = rebase_manager._create_corrected_patch_for_hunks(
                [test_hunk], fake_commit
            )
            # May return None or raise exception, but shouldn't crash the process
            assert patch is None or isinstance(patch, str)


@pytest.fixture
def temp_repo_single():
    """Create a temporary git repository for single hunk testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "single_repo"
        repo_path.mkdir()
        yield TestSingleHunkRepository(repo_path)


@pytest.fixture
def temp_repo_multifile():
    """Create a temporary git repository for multi-file testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "multi_repo"
        repo_path.mkdir()
        yield TestMultiFileRepository(repo_path)


@pytest.fixture
def temp_repo_performance():
    """Create a temporary git repository for performance testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "perf_repo"
        repo_path.mkdir()
        yield TestPerformanceRepository(repo_path)


@pytest.fixture
def temp_repo_binary():
    """Create a temporary git repository for binary file testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "binary_repo"
        repo_path.mkdir()
        yield TestBinaryRepository(repo_path)


class TestSingleHunkRepository:
    """Helper for single hunk test scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)

    def create_single_hunk_scenario(self) -> Dict[str, str]:
        """Create a repository with a simple single hunk change."""

        # Initialize git repository
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=self.repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
        )

        # Create initial file
        simple_file = self.repo_path / "simple.txt"
        simple_file.write_text("Hello World\nThis is a test\nGoodbye World\n")

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=self.repo_path, check=True
        )
        initial_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Create target commit
        simple_file.write_text("Hello World\nThis is a test file\nGoodbye World\n")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update test file"], cwd=self.repo_path, check=True
        )
        target_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Create source commit with change to squash
        simple_file.write_text("Hello World\nThis is a test file\nFarewell World\n")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Change goodbye to farewell"],
            cwd=self.repo_path,
            check=True,
        )
        source_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        return {
            "initial_commit": initial_commit,
            "target_commit": target_commit,
            "source_commit": source_commit,
        }


class TestMultiFileRepository:
    """Helper for multi-file test scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)

    def create_multifile_scenario(self) -> Dict[str, str]:
        """Create a repository with changes across multiple files."""

        # Initialize git repository
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=self.repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
        )

        # Create multiple files
        file1 = self.repo_path / "file1.txt"
        file2 = self.repo_path / "file2.txt"
        file3 = self.repo_path / "subdir" / "file3.txt"

        file3.parent.mkdir(parents=True)

        file1.write_text("File 1 content\nLine 2\nLine 3\n")
        file2.write_text("File 2 content\nAnother line\nFinal line\n")
        file3.write_text("File 3 content\nSubdirectory file\nEnd\n")

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial multi-file commit"],
            cwd=self.repo_path,
            check=True,
        )
        initial_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Create target commit modifying one file
        file1.write_text("File 1 updated content\nLine 2\nLine 3\n")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update file1"], cwd=self.repo_path, check=True
        )
        target_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Create source commit modifying multiple files
        file1.write_text("File 1 updated content\nLine 2 changed\nLine 3\n")
        file2.write_text("File 2 content\nAnother changed line\nFinal line\n")

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Multi-file changes"],
            cwd=self.repo_path,
            check=True,
        )
        source_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        return {
            "initial_commit": initial_commit,
            "target_commit": target_commit,
            "source_commit": source_commit,
        }


class TestPerformanceRepository:
    """Helper for performance test scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)

    def create_large_file_scenario(self) -> Dict[str, str]:
        """Create a repository with a large file for performance testing."""

        # Initialize git repository
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=self.repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
        )

        # Create large file
        large_file = self.repo_path / "large_file.txt"
        lines = []
        for i in range(1000):
            lines.append(f"Line {i}: This is a test line with some content\n")

        large_file.write_text("".join(lines))

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial large file"],
            cwd=self.repo_path,
            check=True,
        )
        initial_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Create target commit
        lines[500] = "Line 500: This line was modified in target\n"
        large_file.write_text("".join(lines))

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify line 500"], cwd=self.repo_path, check=True
        )
        target_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Create source commit with multiple changes
        lines[500] = "Line 500: This line was modified in target and source\n"
        lines[600] = "Line 600: Additional change in source\n"
        lines[700] = "Line 700: Yet another change in source\n"
        large_file.write_text("".join(lines))

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Multiple changes to large file"],
            cwd=self.repo_path,
            check=True,
        )
        source_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        return {
            "initial_commit": initial_commit,
            "target_commit": target_commit,
            "source_commit": source_commit,
        }


class TestBinaryRepository:
    """Helper for binary file test scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)

    def create_binary_file_scenario(self) -> Dict[str, str]:
        """Create a repository with binary files."""

        # Initialize git repository
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=self.repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
        )

        # Create text file for baseline
        text_file = self.repo_path / "text.txt"
        text_file.write_text("Regular text file\n")

        # Create binary file
        binary_file = self.repo_path / "binary.bin"
        binary_data = bytes([0, 1, 2, 255, 254, 128] * 100)  # Binary data
        binary_file.write_bytes(binary_data)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial with binary"],
            cwd=self.repo_path,
            check=True,
        )
        initial_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Modify text file for target
        text_file.write_text("Regular text file modified\n")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify text file"], cwd=self.repo_path, check=True
        )
        target_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Modify both files for source
        text_file.write_text("Regular text file modified again\n")
        binary_data_new = bytes(
            [10, 11, 12, 245, 244, 138] * 100
        )  # Different binary data
        binary_file.write_bytes(binary_data_new)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify both files"], cwd=self.repo_path, check=True
        )
        source_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        return {
            "initial_commit": initial_commit,
            "target_commit": target_commit,
            "source_commit": source_commit,
        }
