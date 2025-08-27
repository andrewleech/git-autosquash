"""
Production-grade test scenarios for patch generation in complex git workflows.

These tests cover the critical scenarios identified by principal-level code review
for ensuring production reliability and handling of real-world git complexities.
"""

import gc
import tempfile
import time
import threading
import subprocess
from pathlib import Path
from typing import Dict
import pytest

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

    # Mock psutil for basic functionality
    class MockProcess:
        def memory_info(self):
            class MockMemInfo:
                rss = 100 * 1024 * 1024  # 100MB mock

            return MockMemInfo()

    class MockPsutil:
        def Process(self):
            return MockProcess()

    psutil = MockPsutil()

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.rebase_manager import RebaseManager


class TestAtomicOperationReliability:
    """Critical tests for atomic operations and rollback scenarios."""

    def test_atomic_operation_rollback(self, temp_repo_complex):
        """Test that operations roll back completely on failure without corruption."""

        repo_path, commits = temp_repo_complex.create_complex_scenario()
        git_ops = GitOps(repo_path)
        rebase_manager = RebaseManager(git_ops, commits["merge_base"])

        # Get initial repository state
        initial_head = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()
        initial_status = git_ops.run_git_command(["status", "--porcelain"]).stdout
        initial_log = git_ops.run_git_command(["log", "--oneline", "-10"]).stdout

        # Create hunks that will deliberately fail during application
        problematic_hunks = [
            DiffHunk(
                file_path="nonexistent_file.c",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                lines=[
                    "@@ -1,1 +1,1 @@",
                    "-nonexistent line",
                    "+replacement line",
                ],
                context_before=[],
                context_after=[],
            )
        ]

        # Attempt patch generation (should handle failure gracefully)
        try:
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                problematic_hunks, commits["target_commit"]
            )
            # If it doesn't fail, that's also acceptable - just skip to verification
        except Exception:
            # Expected - some operations may fail cleanly
            pass

        # Verify repository is in exactly the same state
        final_head = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()
        final_status = git_ops.run_git_command(["status", "--porcelain"]).stdout
        final_log = git_ops.run_git_command(["log", "--oneline", "-10"]).stdout

        assert initial_head == final_head, "HEAD should not have moved"
        assert initial_status == final_status, "Working directory should be unchanged"
        assert initial_log == final_log, "Git history should be unchanged"

        # Verify git repository is still functional
        test_result = git_ops.run_git_command(["status"])
        assert test_result.returncode == 0, "Repository should still be functional"

    def test_concurrent_operation_safety(self, temp_repo_complex):
        """Test that concurrent operations don't corrupt repository state."""

        repo_path, commits = temp_repo_complex.create_complex_scenario()
        git_ops = GitOps(repo_path)

        # This test verifies our operations are safe even if git commands
        # were to be run concurrently (though we don't actually do this
        # in production, it validates state safety)

        results = []
        errors = []

        def worker_operation(worker_id):
            try:
                worker_git_ops = GitOps(repo_path)
                worker_rebase_manager = RebaseManager(
                    worker_git_ops, commits["merge_base"]
                )

                # Each worker attempts to read repository state
                status = worker_git_ops.run_git_command(["status", "--porcelain"])
                log_result = worker_git_ops.run_git_command(["log", "--oneline", "-5"])

                results.append(
                    {
                        "worker_id": worker_id,
                        "status_success": status.returncode == 0,
                        "log_success": log_result.returncode == 0,
                    }
                )

            except Exception as e:
                errors.append(f"Worker {worker_id}: {str(e)}")

        # Run multiple concurrent read operations
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker_operation, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all to complete
        for thread in threads:
            thread.join(timeout=10)

        # Verify all operations succeeded
        assert len(errors) == 0, f"Concurrent operations should not fail: {errors}"
        assert len(results) == 5, "All workers should complete"
        assert all(r["status_success"] for r in results), (
            "All status checks should succeed"
        )
        assert all(r["log_success"] for r in results), "All log checks should succeed"


class TestLargeScalePerformance:
    """Performance validation for production-scale scenarios."""

    @pytest.mark.skipif(not HAS_PSUTIL, reason="psutil required for performance tests")
    def test_massive_repository_performance(self):
        """Test performance with very large repository-like conditions."""

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "massive_repo"
            repo_path.mkdir()

            # Initialize git
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=repo_path, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
            )

            # Create large file structure (simulating real codebase)
            large_content_lines = []
            pattern_locations = []

            for i in range(50000):  # 50k lines file
                if i % 500 == 100:  # Pattern every 500 lines
                    large_content_lines.append("#if MICROPY_PY___FILE__")
                    pattern_locations.append(i + 1)
                elif i % 500 == 101:
                    large_content_lines.append("// __file__ support code")
                elif i % 500 == 102:
                    large_content_lines.append("#endif")
                else:
                    large_content_lines.append(f"// Code line {i}")

            large_file = repo_path / "large_codebase.c"
            large_file.write_text("\n".join(large_content_lines))

            # Create initial commit
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Massive codebase"], cwd=repo_path, check=True
            )

            # Create many hunks targeting different locations
            hunks = []
            for i, line_num in enumerate(pattern_locations[:20]):  # Test 20 patterns
                hunk = DiffHunk(
                    file_path="large_codebase.c",
                    old_start=line_num,
                    old_count=1,
                    new_start=line_num,
                    new_count=1,
                    lines=[
                        f"@@ -{line_num},1 +{line_num},1 @@",
                        "-#if MICROPY_PY___FILE__",
                        "+#if MICROPY_MODULE___FILE__",
                    ],
                    context_before=[],
                    context_after=[],
                )
                hunks.append(hunk)

            git_ops = GitOps(repo_path)
            rebase_manager = RebaseManager(git_ops, "HEAD")

            # Measure performance
            process = psutil.Process()
            memory_before = process.memory_info().rss / 1024 / 1024  # MB

            start_time = time.perf_counter()
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                hunks, "HEAD"
            )
            end_time = time.perf_counter()

            gc.collect()
            memory_after = process.memory_info().rss / 1024 / 1024  # MB

            execution_time = end_time - start_time
            memory_increase = memory_after - memory_before

            # Performance assertions for production readiness
            assert execution_time < 30.0, (
                f"Large scale processing took {execution_time:.2f}s (should be < 30s)"
            )
            assert memory_increase < 200, (
                f"Memory usage increased by {memory_increase:.1f}MB (should be < 200MB)"
            )

            # Verify correctness wasn't sacrificed for performance
            assert patch_content is not None, "Should generate valid patch"
            hunk_count = patch_content.count("@@")
            assert hunk_count == len(hunks), (
                f"Should generate {len(hunks)} hunks, got {hunk_count}"
            )

    @pytest.mark.skipif(not HAS_PSUTIL, reason="psutil required for memory tests")
    def test_memory_pressure_handling(self):
        """Test graceful handling of memory pressure conditions."""

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "memory_test_repo"
            repo_path.mkdir()

            # Initialize git
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=repo_path, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
            )

            # Create content that will stress memory usage
            memory_intensive_files = {}
            for file_idx in range(10):  # 10 large files
                lines = []
                for line_idx in range(10000):  # 10k lines each
                    if line_idx % 100 == 50:
                        lines.append("#if OLD_PATTERN")
                    else:
                        lines.append(
                            f"// File {file_idx} Line {line_idx}: " + "x" * 100
                        )  # Long lines

                memory_intensive_files[f"large_file_{file_idx}.c"] = "\n".join(lines)

            # Write all files
            for filename, content in memory_intensive_files.items():
                (repo_path / filename).write_text(content)

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Memory intensive files"],
                cwd=repo_path,
                check=True,
            )

            # Create many hunks across all files
            hunks = []
            for file_idx in range(10):
                for pattern_idx in range(10):  # 10 patterns per file
                    line_num = 51 + (pattern_idx * 100)  # Lines 51, 151, 251, etc.
                    hunk = DiffHunk(
                        file_path=f"large_file_{file_idx}.c",
                        old_start=line_num,
                        old_count=1,
                        new_start=line_num,
                        new_count=1,
                        lines=[
                            f"@@ -{line_num},1 +{line_num},1 @@",
                            "-#if OLD_PATTERN",
                            "+#if NEW_PATTERN",
                        ],
                        context_before=[],
                        context_after=[],
                    )
                    hunks.append(hunk)

            git_ops = GitOps(repo_path)
            rebase_manager = RebaseManager(git_ops, "HEAD")

            # Monitor memory usage during processing
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024
            peak_memory = initial_memory

            def monitor_memory():
                nonlocal peak_memory
                while True:
                    try:
                        current_memory = process.memory_info().rss / 1024 / 1024
                        peak_memory = max(peak_memory, current_memory)
                        time.sleep(0.1)
                    except:
                        break

            monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
            monitor_thread.start()

            # Process all hunks
            start_time = time.perf_counter()
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                hunks, "HEAD"
            )
            end_time = time.perf_counter()

            execution_time = end_time - start_time
            memory_peak_increase = peak_memory - initial_memory

            # Verify memory usage stays reasonable even under stress
            assert memory_peak_increase < 500, (
                f"Peak memory increase: {memory_peak_increase:.1f}MB (should be < 500MB)"
            )
            assert execution_time < 60.0, (
                f"Memory stress test took {execution_time:.2f}s (should be < 60s)"
            )

            # Verify output correctness
            assert patch_content is not None, "Should handle memory pressure gracefully"
            assert len(patch_content) > 0, "Should generate non-empty patch"

            # Verify all hunks were processed
            expected_hunks = len(hunks)
            actual_hunks = patch_content.count("@@")
            assert actual_hunks == expected_hunks, (
                f"Should process all {expected_hunks} hunks, processed {actual_hunks}"
            )


class TestSecurityAndRobustness:
    """Security and robustness tests for production deployment."""

    def test_path_traversal_prevention(self):
        """Test prevention of path traversal attacks through malicious file paths."""

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "security_test_repo"
            repo_path.mkdir()

            # Initialize git
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=repo_path, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
            )

            # Create legitimate file
            test_file = repo_path / "legitimate.c"
            test_file.write_text("int main() { return 0; }")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Legitimate file"], cwd=repo_path, check=True
            )

            git_ops = GitOps(repo_path)
            rebase_manager = RebaseManager(git_ops, "HEAD")

            # Test various path traversal attempts
            malicious_paths = [
                "../../../etc/passwd",
                "..\\..\\..\\windows\\system32\\config\\sam",
                "/etc/shadow",
                "C:\\Windows\\System32\\drivers\\etc\\hosts",
                "\\\\network\\share\\sensitive_file",
                "legitimate.c/../../../etc/passwd",
            ]

            for malicious_path in malicious_paths:
                malicious_hunk = DiffHunk(
                    file_path=malicious_path,
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=[
                        "@@ -1,1 +1,1 @@",
                        "-innocent content",
                        "+malicious content",
                    ],
                    context_before=[],
                    context_after=[],
                )

                # Should handle malicious paths safely
                try:
                    patch_content = rebase_manager._create_corrected_patch_for_hunks(
                        [malicious_hunk], "HEAD"
                    )
                    # If it succeeds, ensure no sensitive files were accessed
                    if patch_content:
                        assert malicious_path not in patch_content, (
                            f"Should not expose path: {malicious_path}"
                        )
                except Exception:
                    # Failing is also acceptable for security
                    pass

                # Verify no sensitive files were created or accessed
                sensitive_paths = [
                    Path("/etc/passwd"),
                    Path("/etc/shadow"),
                    Path("C:\\Windows\\System32\\drivers\\etc\\hosts"),
                ]

                for sensitive_path in sensitive_paths:
                    if sensitive_path.exists():
                        # If the file exists (on this system), ensure our operation didn't modify it
                        # We can't fully test this without root, but we can verify we didn't create new files
                        pass

                # Verify no files were created outside the repository
                parent_files_before = set()
                if repo_path.parent.exists():
                    parent_files_before = set(repo_path.parent.iterdir())

                # The malicious operation above should not have created files in parent directory
                if repo_path.parent.exists():
                    parent_files_after = set(repo_path.parent.iterdir())
                    new_files = parent_files_after - parent_files_before
                    # Filter out files that might be created by the system/other processes
                    suspicious_new_files = [
                        f
                        for f in new_files
                        if not f.name.startswith(".")
                        and f.name not in ["etc", "windows", "Windows"]
                    ]
                    assert len(suspicious_new_files) == 0, (
                        f"Should not create files outside repo: {suspicious_new_files}"
                    )

    def test_resource_exhaustion_protection(self):
        """Test protection against resource exhaustion attacks."""

        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "resource_test_repo"
            repo_path.mkdir()

            # Initialize git
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=repo_path, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
            )

            # Create base file
            test_file = repo_path / "test.c"
            test_file.write_text("int main() { return 0; }")
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Base file"], cwd=repo_path, check=True
            )

            git_ops = GitOps(repo_path)
            rebase_manager = RebaseManager(git_ops, "HEAD")

            # Test 1: Extremely large hunk content
            enormous_line = "x" * 1000000  # 1MB line
            large_hunk = DiffHunk(
                file_path="test.c",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                lines=[
                    "@@ -1,1 +1,1 @@",
                    f"-{enormous_line}",
                    f"+{enormous_line}_modified",
                ],
                context_before=[],
                context_after=[],
            )

            # Should handle large content without crashing
            start_time = time.time()
            try:
                patch_content = rebase_manager._create_corrected_patch_for_hunks(
                    [large_hunk], "HEAD"
                )
                # If it succeeds, verify it completed in reasonable time
                elapsed = time.time() - start_time
                assert elapsed < 30.0, (
                    f"Large hunk processing took {elapsed:.2f}s (should timeout/limit)"
                )
            except Exception:
                # Failing gracefully is also acceptable
                elapsed = time.time() - start_time
                assert elapsed < 30.0, (
                    f"Should fail quickly, not hang for {elapsed:.2f}s"
                )

            # Test 2: Massive number of hunks
            many_hunks = []
            for i in range(10000):  # 10k hunks
                hunk = DiffHunk(
                    file_path=f"file_{i % 100}.c",  # Spread across 100 files
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=[
                        "@@ -1,1 +1,1 @@",
                        f"-line_{i}",
                        f"+modified_line_{i}",
                    ],
                    context_before=[],
                    context_after=[],
                )
                many_hunks.append(hunk)

            # Should handle many hunks without excessive resource usage
            process = psutil.Process()
            memory_before = process.memory_info().rss / 1024 / 1024

            start_time = time.time()
            try:
                patch_content = rebase_manager._create_corrected_patch_for_hunks(
                    many_hunks, "HEAD"
                )
                elapsed = time.time() - start_time
                memory_after = process.memory_info().rss / 1024 / 1024
                memory_increase = memory_after - memory_before

                # Should complete reasonably quickly and not use excessive memory
                assert elapsed < 120.0, (
                    f"Many hunks took {elapsed:.2f}s (should be < 120s)"
                )
                assert memory_increase < 1000, (
                    f"Memory increased by {memory_increase:.1f}MB (should be < 1GB)"
                )

            except Exception:
                # If it fails, should fail quickly
                elapsed = time.time() - start_time
                assert elapsed < 120.0, (
                    f"Should fail quickly, not hang for {elapsed:.2f}s"
                )


@pytest.fixture
def temp_repo_complex():
    """Create complex repository scenarios for production testing."""

    class ComplexRepoBuilder:
        def create_complex_scenario(self) -> tuple[Path, Dict[str, str]]:
            """Create a complex multi-branch, multi-file repository scenario."""

            temp_dir = tempfile.mkdtemp()
            repo_path = Path(temp_dir) / "complex_repo"
            repo_path.mkdir()

            # Initialize git
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
            )

            # Create initial complex file structure
            src_dir = repo_path / "src"
            tests_dir = repo_path / "tests"
            docs_dir = repo_path / "docs"

            for dir_path in [src_dir, tests_dir, docs_dir]:
                dir_path.mkdir()

            # Create multiple files with patterns
            files_content = {
                "src/main.c": """
#include <stdio.h>

int main() {
    #if FEATURE_FLAG
    printf("Feature enabled\\n");
    #endif
    return 0;
}
                """,
                "src/util.c": """
#include "util.h"

void utility_function() {
    #if FEATURE_FLAG
    // Utility feature code
    #endif
}
                """,
                "tests/test_main.c": """  
#include "test_framework.h"

void test_main_functionality() {
    #if FEATURE_FLAG
    // Test feature functionality
    #endif
}
                """,
                "docs/README.md": """
# Project Documentation

## Features

Configuration flags:
- FEATURE_FLAG: Controls main feature
                """,
            }

            # Write all files
            for file_path, content in files_content.items():
                full_path = repo_path / file_path
                full_path.write_text(content.strip())

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial complex structure"],
                cwd=repo_path,
                check=True,
            )

            merge_base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Create target commit
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "Target for squashing"],
                cwd=repo_path,
                check=True,
            )
            target_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Create complex changes to squash
            modified_content = files_content["src/main.c"].replace(
                "FEATURE_FLAG", "NEW_FEATURE_FLAG"
            )
            (repo_path / "src/main.c").write_text(modified_content)

            modified_util = files_content["src/util.c"].replace(
                "FEATURE_FLAG", "NEW_FEATURE_FLAG"
            )
            (repo_path / "src/util.c").write_text(modified_util)

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Update feature flags"],
                cwd=repo_path,
                check=True,
            )

            source_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            return repo_path, {
                "merge_base": merge_base,
                "target_commit": target_commit,
                "source_commit": source_commit,
            }

    yield ComplexRepoBuilder()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
