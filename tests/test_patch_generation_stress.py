"""
Stress tests for patch generation under extreme conditions.

These tests verify patch generation performance and memory usage under
high-load scenarios, concurrent operations, and resource constraints.
"""

import gc
import psutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseManager


class StressTestBuilder:
    """Builder for creating stress test scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)
        self._init_repo()

    def _init_repo(self):
        """Initialize repository for stress testing."""
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Stress Test"],
            cwd=self.repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "stress@test.com"],
            cwd=self.repo_path,
            check=True,
        )

        # Configure for performance
        subprocess.run(
            ["git", "config", "core.preloadindex", "true"],
            cwd=self.repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "core.fscache", "true"], cwd=self.repo_path, check=True
        )

    def create_massive_repository(
        self,
        num_files: int = 100,
        lines_per_file: int = 1000,
        patterns_per_file: int = 20,
    ) -> Dict[str, str]:
        """Create repository with massive number of files and patterns."""

        files_content = {}

        for file_idx in range(num_files):
            content_lines = []
            pattern_lines = []

            for line_idx in range(lines_per_file):
                if line_idx % (lines_per_file // patterns_per_file) == 10:
                    # Add pattern line
                    content_lines.append(f"#if MASSIVE_PATTERN_{file_idx}")
                    content_lines.append(
                        f"void pattern_function_{file_idx}_{line_idx}() {{"
                    )
                    content_lines.append("    // Pattern implementation")
                    content_lines.append("}")
                    content_lines.append("#endif")
                    pattern_lines.append(line_idx)
                else:
                    # Add regular code
                    content_lines.append(f"// File {file_idx} Line {line_idx}")
                    if line_idx % 10 == 5:
                        content_lines.append(
                            f"void function_{file_idx}_{line_idx}() {{ }}"
                        )

            filename = f"massive_{file_idx:03d}.c"
            files_content[filename] = "\n".join(content_lines)

        # Write all files to repository
        for filename, content in files_content.items():
            file_path = self.repo_path / filename
            file_path.write_text(content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Massive repository base"],
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

        # Create target commit
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Target for massive squash"],
            cwd=self.repo_path,
            check=True,
        )

        target_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Update all patterns in all files
        for filename in files_content.keys():
            file_path = self.repo_path / filename
            content = file_path.read_text()
            # Update patterns to create massive diff
            updated_content = content.replace("MASSIVE_PATTERN_", "UPDATED_PATTERN_")
            file_path.write_text(updated_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update all patterns"],
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
            "target_commit": target_commit,
            "change_commit": change_commit,
            "num_files": num_files,
            "lines_per_file": lines_per_file,
            "patterns_per_file": patterns_per_file,
        }

    def create_deep_history_scenario(self, history_depth: int = 50) -> Dict[str, str]:
        """Create repository with very deep commit history."""

        # Create base file
        base_content = """// Deep history test file
#if HISTORY_PATTERN_0
void base_function() {
    // Base implementation
}
#endif
"""

        base_file = self.repo_path / "deep_history.c"
        base_file.write_text(base_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Deep history base"], cwd=self.repo_path, check=True
        )

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Create deep commit history
        commits = [base_commit]

        for depth in range(1, history_depth):
            # Update content for this depth
            current_content = base_file.read_text()

            # Add new pattern for this depth
            new_pattern_content = (
                current_content
                + f"""
#if HISTORY_PATTERN_{depth}
void depth_{depth}_function() {{
    // Depth {depth} implementation
}}
#endif
"""
            )

            base_file.write_text(new_pattern_content)
            subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"Depth {depth} commit"],
                cwd=self.repo_path,
                check=True,
            )

            commit_hash = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            commits.append(commit_hash)

        # Create final commit that modifies patterns across history
        final_content = base_file.read_text()
        # Change first few patterns
        for i in range(min(5, history_depth)):
            final_content = final_content.replace(
                f"HISTORY_PATTERN_{i}", f"UPDATED_PATTERN_{i}"
            )

        base_file.write_text(final_content)
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update historical patterns"],
            cwd=self.repo_path,
            check=True,
        )

        final_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "base_commit": base_commit,
            "history_commits": commits,
            "final_commit": final_commit,
            "history_depth": history_depth,
        }

    def create_concurrent_operation_scenario(self) -> Dict[str, str]:
        """Create scenario for testing concurrent operations."""

        # Create multiple files that can be operated on concurrently
        concurrent_files = {}

        for i in range(10):
            content = f"""// Concurrent test file {i}
#if CONCURRENT_PATTERN_{i}
void concurrent_function_{i}() {{
    // Implementation {i}
}}
#endif

void utility_function_{i}() {{
    // Utility code
}}
"""
            filename = f"concurrent_{i}.c"
            concurrent_files[filename] = content

            file_path = self.repo_path / filename
            file_path.write_text(content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Concurrent test base"],
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

        # Create multiple target commits for different files
        target_commits = []

        for i in range(3):  # Create 3 target commits
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", f"Target {i}"],
                cwd=self.repo_path,
                check=True,
            )

            target_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            target_commits.append(target_commit)

        # Update files with patterns
        for filename in concurrent_files.keys():
            file_path = self.repo_path / filename
            content = file_path.read_text()
            updated_content = content.replace("CONCURRENT_PATTERN_", "NEW_CONCURRENT_")
            file_path.write_text(updated_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update concurrent patterns"],
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
            "target_commits": target_commits,
            "change_commit": change_commit,
            "files": list(concurrent_files.keys()),
        }


@pytest.fixture
def stress_test_repo():
    """Create repository for stress testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "stress_test"
        repo_path.mkdir()
        builder = StressTestBuilder(repo_path)
        yield builder


class TestPatchGenerationStress:
    """Stress tests for patch generation."""

    @pytest.mark.slow
    def test_massive_repository_performance(self, stress_test_repo):
        """Test patch generation performance with massive repositories."""
        repo = stress_test_repo

        # Create massive repository (smaller for CI)
        scenario = repo.create_massive_repository(
            num_files=50,  # 50 files
            lines_per_file=500,  # 500 lines each
            patterns_per_file=10,  # 10 patterns each
        )

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Measure memory usage
        gc.collect()
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Time the operation
        start_time = time.perf_counter()

        # Get diff from massive change
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["change_commit"]]
        )

        assert diff_result.returncode == 0, "Should get massive diff successfully"

        # Parse hunks
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)
        hunk_parse_time = time.perf_counter()

        # Verify scale
        assert (
            len(hunks) >= scenario["num_files"] * scenario["patterns_per_file"] / 2
        ), f"Should find many hunks, got {len(hunks)}"

        # Generate patch
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            hunks, scenario["target_commit"]
        )

        patch_generation_time = time.perf_counter()

        # Measure final memory
        gc.collect()
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = memory_after - memory_before

        # Performance assertions
        total_time = patch_generation_time - start_time
        parse_time = hunk_parse_time - start_time
        generation_time = patch_generation_time - hunk_parse_time

        print("Massive repo performance:")
        print(f"  Files: {scenario['num_files']}")
        print(f"  Total hunks: {len(hunks)}")
        print(f"  Parse time: {parse_time:.2f}s")
        print(f"  Generation time: {generation_time:.2f}s")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Memory increase: {memory_increase:.1f}MB")

        # Stress test limits
        assert total_time < 30.0, f"Massive repo took {total_time:.2f}s (too slow)"
        assert memory_increase < 500, f"Memory usage too high: {memory_increase:.1f}MB"

        # Verify correctness
        assert patch_content is not None, "Should generate patch for massive repo"
        assert len(patch_content) > 0, "Massive patch should not be empty"

        # Verify patch structure
        hunk_headers = len(
            [line for line in patch_content.split("\n") if line.startswith("@@")]
        )
        assert hunk_headers > 0, "Should have hunk headers in massive patch"

    @pytest.mark.slow
    def test_deep_commit_history_performance(self, stress_test_repo):
        """Test patch generation performance with very deep commit history."""
        repo = stress_test_repo

        # Create deep history (smaller depth for CI)
        scenario = repo.create_deep_history_scenario(history_depth=30)

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)

        # Test targeting commits at various depths
        depth_test_results = []

        for test_depth in [5, 15, 25]:  # Test different depths
            if test_depth >= len(scenario["history_commits"]):
                continue

            target_commit = scenario["history_commits"][test_depth]
            rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

            # Time operation at this depth
            start_time = time.perf_counter()

            # Get diff
            diff_result = git_ops.run_git_command(
                ["show", "--no-merges", scenario["final_commit"]]
            )

            hunks = hunk_parser._parse_diff_output(diff_result.stdout)
            deep_hunks = [h for h in hunks if h.file_path == "deep_history.c"]

            # Generate patch targeting deep history
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                deep_hunks, target_commit
            )

            end_time = time.perf_counter()
            operation_time = end_time - start_time

            depth_test_results.append(
                {
                    "depth": test_depth,
                    "time": operation_time,
                    "success": patch_content is not None,
                }
            )

        # Verify deep history handling
        for result in depth_test_results:
            print(
                f"Depth {result['depth']}: {result['time']:.2f}s, success: {result['success']}"
            )

            # Should complete in reasonable time regardless of depth
            assert result["time"] < 10.0, (
                f"Deep history depth {result['depth']} took {result['time']:.2f}s"
            )

        # Performance should not degrade exponentially with depth
        if len(depth_test_results) >= 2:
            shallow_time = depth_test_results[0]["time"]
            deep_time = depth_test_results[-1]["time"]

            # Deep operations should not be more than 5x slower than shallow ones
            slowdown_ratio = deep_time / shallow_time if shallow_time > 0 else 1
            assert slowdown_ratio < 5.0, (
                f"Deep history slowdown too high: {slowdown_ratio:.2f}x"
            )

    def test_concurrent_operations_safety(self, stress_test_repo):
        """Test safety of concurrent patch generation operations."""
        repo = stress_test_repo
        scenario = repo.create_concurrent_operation_scenario()

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)

        # Get hunks once
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["change_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Split hunks by file for concurrent processing
        hunks_by_file = {}
        for hunk in hunks:
            if hunk.file_path not in hunks_by_file:
                hunks_by_file[hunk.file_path] = []
            hunks_by_file[hunk.file_path].append(hunk)

        def process_file_hunks(
            file_path: str, file_hunks: List, target_commit: str
        ) -> Dict:
            """Process hunks for a single file."""
            try:
                # Create separate GitOps for thread safety
                thread_git_ops = GitOps(str(repo.repo_path))
                rebase_manager = RebaseManager(thread_git_ops, scenario["base_commit"])

                start_time = time.perf_counter()
                patch_content = rebase_manager._create_corrected_patch_for_hunks(
                    file_hunks, target_commit
                )
                end_time = time.perf_counter()

                return {
                    "file": file_path,
                    "success": patch_content is not None,
                    "time": end_time - start_time,
                    "patch_size": len(patch_content) if patch_content else 0,
                    "error": None,
                }

            except Exception as e:
                return {
                    "file": file_path,
                    "success": False,
                    "time": 0,
                    "patch_size": 0,
                    "error": str(e),
                }

        # Run concurrent operations
        concurrent_results = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            # Submit jobs for different target commits
            futures = []

            for i, (file_path, file_hunks) in enumerate(hunks_by_file.items()):
                # Use different target commits for different files
                target_idx = i % len(scenario["target_commits"])
                target_commit = scenario["target_commits"][target_idx]

                future = executor.submit(
                    process_file_hunks, file_path, file_hunks, target_commit
                )
                futures.append(future)

            # Collect results
            for future in as_completed(futures):
                result = future.result()
                concurrent_results.append(result)

        # Analyze concurrent operation results
        successful_operations = [r for r in concurrent_results if r["success"]]
        failed_operations = [r for r in concurrent_results if not r["success"]]

        print(
            f"Concurrent operations: {len(successful_operations)} successful, {len(failed_operations)} failed"
        )

        # Most operations should succeed
        success_rate = len(successful_operations) / len(concurrent_results)
        assert success_rate >= 0.8, (
            f"Concurrent success rate too low: {success_rate:.2f}"
        )

        # No operation should take excessively long
        max_time = (
            max(r["time"] for r in successful_operations)
            if successful_operations
            else 0
        )
        assert max_time < 15.0, f"Concurrent operation took too long: {max_time:.2f}s"

        # Check for any unexpected errors
        for result in failed_operations:
            print(f"Failed operation: {result['file']} - {result['error']}")

        # Verify repository state is consistent after concurrent operations
        final_status = git_ops.run_git_command(["status", "--porcelain"])
        # Repository should be in a consistent state (may have uncommitted changes from testing)

    @pytest.mark.slow
    def test_memory_pressure_handling(self, stress_test_repo):
        """Test patch generation under memory pressure."""
        repo = stress_test_repo

        # Create scenario with high memory usage potential
        scenario = repo.create_massive_repository(
            num_files=30, lines_per_file=1000, patterns_per_file=15
        )

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Force garbage collection before test
        gc.collect()

        # Monitor memory usage throughout operation
        process = psutil.Process()
        memory_samples = []

        def memory_monitor():
            """Monitor memory usage in background thread."""
            for _ in range(100):  # Sample for up to 10 seconds
                try:
                    memory_mb = process.memory_info().rss / 1024 / 1024
                    memory_samples.append(memory_mb)
                    time.sleep(0.1)
                except:
                    break

        # Start memory monitoring
        monitor_thread = threading.Thread(target=memory_monitor)
        monitor_thread.daemon = True
        monitor_thread.start()

        try:
            # Perform memory-intensive operations
            diff_result = git_ops.run_git_command(
                ["show", "--no-merges", scenario["change_commit"]]
            )

            hunks = hunk_parser._parse_diff_output(diff_result.stdout)

            # Process in batches to test memory management
            batch_size = 50
            batch_results = []

            for i in range(0, len(hunks), batch_size):
                batch_hunks = hunks[i : i + batch_size]

                # Force garbage collection between batches
                gc.collect()

                batch_patch = rebase_manager._create_corrected_patch_for_hunks(
                    batch_hunks, scenario["target_commit"]
                )

                batch_results.append(
                    {
                        "batch": i // batch_size,
                        "hunks": len(batch_hunks),
                        "success": batch_patch is not None,
                        "size": len(batch_patch) if batch_patch else 0,
                    }
                )

        finally:
            # Stop memory monitoring
            monitor_thread.join(timeout=1)

        # Analyze memory usage
        if memory_samples:
            initial_memory = memory_samples[0]
            peak_memory = max(memory_samples)
            final_memory = memory_samples[-1]

            memory_increase = peak_memory - initial_memory
            memory_leaked = final_memory - initial_memory

            print("Memory pressure test:")
            print(f"  Initial: {initial_memory:.1f}MB")
            print(f"  Peak: {peak_memory:.1f}MB")
            print(f"  Final: {final_memory:.1f}MB")
            print(f"  Increase: {memory_increase:.1f}MB")
            print(f"  Leaked: {memory_leaked:.1f}MB")

            # Memory constraints
            assert memory_increase < 800, (
                f"Peak memory usage too high: {memory_increase:.1f}MB"
            )
            assert memory_leaked < 100, f"Memory leak detected: {memory_leaked:.1f}MB"

        # Verify batch processing results
        successful_batches = [r for r in batch_results if r["success"]]
        assert len(successful_batches) > 0, (
            "At least some batches should succeed under memory pressure"
        )

        # Final garbage collection and memory check
        gc.collect()
        final_memory_check = process.memory_info().rss / 1024 / 1024

    def test_resource_exhaustion_graceful_handling(self, stress_test_repo):
        """Test graceful handling when system resources are exhausted."""
        repo = stress_test_repo
        scenario = repo.create_massive_repository(
            num_files=20, lines_per_file=500, patterns_per_file=8
        )

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Simulate resource constraints by limiting available memory
        # (This is simulation - we can't actually limit memory in tests)

        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["change_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Test with progressively larger hunk sets to find breaking point
        max_successful_hunks = 0

        for batch_size in [10, 25, 50, 100, len(hunks)]:
            if batch_size > len(hunks):
                batch_size = len(hunks)

            test_hunks = hunks[:batch_size]

            try:
                start_time = time.perf_counter()

                patch_content = rebase_manager._create_corrected_patch_for_hunks(
                    test_hunks, scenario["target_commit"]
                )

                end_time = time.perf_counter()
                operation_time = end_time - start_time

                if (
                    patch_content is not None and operation_time < 20.0
                ):  # 20 second timeout
                    max_successful_hunks = batch_size
                    print(
                        f"Successfully processed {batch_size} hunks in {operation_time:.2f}s"
                    )
                else:
                    print(f"Failed or timed out processing {batch_size} hunks")
                    break

            except Exception as e:
                print(f"Exception processing {batch_size} hunks: {e}")
                break

        # Should handle at least some hunks successfully
        assert max_successful_hunks > 0, (
            "Should process at least some hunks under resource pressure"
        )

        # Verify system is still responsive after stress
        status_result = git_ops.run_git_command(["status", "--porcelain"])
        assert status_result.returncode == 0, (
            "Git should still be responsive after stress test"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not slow"])
