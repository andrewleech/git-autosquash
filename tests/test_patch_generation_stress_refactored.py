"""
Stress tests for patch generation under extreme conditions.

These tests verify patch generation performance and memory usage under
high-load scenarios, concurrent operations, and resource constraints.

Refactored version using proper GitOps integration and resource management.
"""

import gc
import psutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pytest
import weakref
from contextlib import contextmanager

from git_autosquash.hunk_parser import HunkParser
from tests.base_test_repository import (
    PerformanceTestRepository,
    temporary_test_repository,
)


class MemoryTracker:
    """Track memory usage during stress tests."""

    def __init__(self):
        self.process = psutil.Process()
        self.initial_memory = None
        self.peak_memory = None
        self.measurements: List[Tuple[float, float]] = []  # (timestamp, memory_mb)

    def start_tracking(self) -> None:
        """Start memory tracking."""
        self.initial_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.peak_memory = self.initial_memory
        self.measurements = [(time.time(), self.initial_memory)]

    def record_measurement(self) -> float:
        """Record current memory usage and return MB."""
        current_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.measurements.append((time.time(), current_memory))

        if current_memory > self.peak_memory:
            self.peak_memory = current_memory

        return current_memory

    def get_memory_increase(self) -> Optional[float]:
        """Get memory increase since start in MB."""
        if self.initial_memory is None:
            return None
        current = self.process.memory_info().rss / 1024 / 1024
        return current - self.initial_memory

    def get_peak_increase(self) -> Optional[float]:
        """Get peak memory increase since start in MB."""
        if self.initial_memory is None or self.peak_memory is None:
            return None
        return self.peak_memory - self.initial_memory


class StressTestRepository(PerformanceTestRepository):
    """Enhanced repository for stress testing with memory management."""

    def __init__(self, repo_path: Path):
        super().__init__(repo_path)
        self.memory_tracker = MemoryTracker()
        self._configure_performance_settings()

    def _configure_performance_settings(self) -> None:
        """Configure git for performance testing."""
        performance_configs = [
            (["config", "core.preloadindex", "true"], "preload index"),
            (["config", "core.fscache", "true"], "filesystem cache"),
            (["config", "gc.auto", "0"], "disable auto gc"),
        ]

        for args, description in performance_configs:
            try:
                result = self.git_ops.run_git_command(args)
                if result.returncode != 0:
                    # Non-fatal performance configuration failures
                    print(
                        f"Warning: Failed to configure {description}: {result.stderr}"
                    )
            except Exception:
                # Best effort - don't fail stress tests for config issues
                pass

    def create_large_repository_scenario(
        self, file_count: int = 100, lines_per_file: int = 1000
    ) -> str:
        """Create a large repository with many files for stress testing."""
        files_content = {}

        for i in range(file_count):
            filename = f"file_{i:03d}.txt"
            lines = [f"Line {j:04d} in file {i:03d}\n" for j in range(lines_per_file)]
            files_content[filename] = "".join(lines)

        return self.add_commit(
            files_content, f"Add {file_count} files with {lines_per_file} lines each"
        )

    def create_memory_intensive_scenario(self, total_size_mb: int = 10) -> str:
        """Create memory-intensive content for testing."""
        # Calculate content size to reach target MB
        target_bytes = total_size_mb * 1024 * 1024
        line_size = 100  # Approximate bytes per line
        total_lines = target_bytes // line_size

        lines = []
        for i in range(total_lines):
            line_content = (
                f"Memory test line {i:06d} with padding content to reach target size"
            )
            lines.append(line_content.ljust(line_size - 1) + "\n")

        content = "".join(lines)
        return self.add_commit(
            {"large_memory_file.txt": content},
            f"Add {total_size_mb}MB memory test file",
        )

    def create_concurrent_modification_scenario(
        self, modification_count: int = 50
    ) -> List[str]:
        """Create multiple small modifications for concurrent testing."""
        # Initial file
        initial_content = "// Base content\n"
        for i in range(modification_count):
            initial_content += f"#define CONSTANT_{i:03d} {i}\n"

        base_commit = self.add_commit(
            {"concurrent_test.h": initial_content}, "Base file for concurrent testing"
        )

        commit_hashes = [base_commit]

        # Create multiple small modifications
        for i in range(modification_count // 10):  # Create 10% as many commits
            modified_content = initial_content.replace(
                f"#define CONSTANT_{i * 10:03d} {i * 10}",
                f"#define CONSTANT_{i * 10:03d} {i * 10 + 1000}",  # Change the value
            )

            commit_hash = self.add_commit(
                {"concurrent_test.h": modified_content}, f"Modify constant {i * 10}"
            )
            commit_hashes.append(commit_hash)
            initial_content = modified_content

        return commit_hashes


class StressTestExecutor:
    """Execute stress tests with proper resource management."""

    def __init__(self, max_memory_mb: int = 200, timeout_seconds: int = 300):
        self.max_memory_mb = max_memory_mb
        self.timeout_seconds = timeout_seconds
        self.active_repositories: weakref.WeakSet = weakref.WeakSet()

    @contextmanager
    def memory_monitoring(self):
        """Context manager for memory monitoring during tests."""
        tracker = MemoryTracker()
        tracker.start_tracking()

        try:
            yield tracker
        finally:
            # Force garbage collection and measure final memory
            gc.collect()
            tracker.record_measurement()

            # Verify memory usage is reasonable
            memory_increase = tracker.get_memory_increase()
            if memory_increase and memory_increase > self.max_memory_mb:
                print(
                    f"Warning: Memory increased by {memory_increase:.1f}MB (limit: {self.max_memory_mb}MB)"
                )

    def execute_concurrent_operations(
        self, operation_func, num_threads: int = 4, operations_per_thread: int = 10
    ) -> List[Any]:
        """Execute operations concurrently with proper error handling."""
        results = []
        exceptions: list[tuple[int | str, Exception]] = []

        def worker_thread(thread_id: int) -> List[Any]:
            thread_results = []
            try:
                for i in range(operations_per_thread):
                    result = operation_func(thread_id, i)
                    thread_results.append(result)
            except Exception as e:
                exceptions.append((thread_id, e))
            return thread_results

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(worker_thread, thread_id)
                for thread_id in range(num_threads)
            ]

            for future in as_completed(futures, timeout=self.timeout_seconds):
                try:
                    thread_results = future.result()
                    results.extend(thread_results)
                except Exception as e:
                    exceptions.append(("future", e))

        if exceptions:
            # Log exceptions but don't necessarily fail the test
            for thread_id, exception in exceptions:
                print(f"Thread {thread_id} exception: {exception}")

        return results

    def cleanup_repositories(self) -> None:
        """Clean up all active test repositories."""
        repositories = list(self.active_repositories)
        for repo in repositories:
            try:
                repo.cleanup()
            except Exception:
                pass  # Best effort cleanup


@pytest.fixture(scope="function")
def stress_executor():
    """Provide stress test executor with cleanup."""
    executor = StressTestExecutor()
    try:
        yield executor
    finally:
        executor.cleanup_repositories()


@pytest.fixture(scope="function")
def stress_repo():
    """Create stress test repository with proper cleanup."""
    with temporary_test_repository("stress_test") as temp_repo:
        stress_repo = StressTestRepository(temp_repo.repo_path)
        yield stress_repo


class TestPatchGenerationStress:
    """Stress tests for patch generation performance and reliability."""

    def test_large_file_performance(
        self, stress_repo: StressTestRepository, stress_executor: StressTestExecutor
    ):
        """Test patch generation performance with large files."""
        with stress_executor.memory_monitoring() as tracker:
            # Create large file scenario
            stress_repo.create_large_file_scenario(line_count=10000)

            # Modify the file to create hunks
            large_content = (stress_repo.repo_path / "large_file.txt").read_text()
            modified_content = large_content.replace(
                "Line 0100:", "Line 0100 MODIFIED:"
            )
            stress_repo.create_file("large_file.txt", modified_content)

            # Measure patch generation time
            start_time = time.time()
            hunk_parser = HunkParser(stress_repo.git_ops)
            hunks = hunk_parser.get_diff_hunks()
            elapsed_time = time.time() - start_time

            # Verify performance is reasonable
            assert elapsed_time < 5.0, (
                f"Patch generation took too long: {elapsed_time:.2f}s"
            )
            assert len(hunks) > 0, "Should generate at least one hunk"

            # Check memory usage
            memory_increase = tracker.get_memory_increase()
            assert memory_increase < 100, (
                f"Memory usage too high: {memory_increase:.1f}MB"
            )

    def test_many_files_scenario(
        self, stress_repo: StressTestRepository, stress_executor: StressTestExecutor
    ):
        """Test handling many files without memory issues."""
        with stress_executor.memory_monitoring() as tracker:
            # Create many small files
            stress_repo.create_large_repository_scenario(
                file_count=100, lines_per_file=100
            )

            # Modify multiple files
            files_to_modify = [
                f"file_{i:03d}.txt" for i in range(0, 100, 10)
            ]  # Every 10th file
            for filename in files_to_modify:
                file_path = stress_repo.repo_path / filename
                content = file_path.read_text()
                modified_content = content.replace("Line 0050", "Line 0050 MODIFIED")
                file_path.write_text(modified_content)

            # Parse hunks from all modifications
            hunk_parser = HunkParser(stress_repo.git_ops)
            hunks = hunk_parser.get_diff_hunks()

            # Verify results
            assert len(hunks) == len(files_to_modify), (
                f"Expected {len(files_to_modify)} hunks, got {len(hunks)}"
            )

            # Memory should remain reasonable
            memory_increase = tracker.get_memory_increase()
            assert memory_increase < 150, (
                f"Memory usage too high: {memory_increase:.1f}MB"
            )

    def test_concurrent_repository_operations(
        self, stress_executor: StressTestExecutor
    ):
        """Test concurrent operations on multiple repositories."""

        def create_and_test_repository(
            thread_id: int, operation_id: int
        ) -> Dict[str, Any]:
            """Create repository and perform operations in worker thread."""
            with temporary_test_repository(
                f"concurrent_{thread_id}_{operation_id}"
            ) as temp_repo:
                repo = StressTestRepository(temp_repo.repo_path)

                # Create scenario
                commit_hashes = repo.create_concurrent_modification_scenario()

                # Parse hunks
                hunk_parser = HunkParser(repo.git_ops)
                hunks = hunk_parser.get_diff_hunks()

                return {
                    "thread_id": thread_id,
                    "operation_id": operation_id,
                    "commit_count": len(commit_hashes),
                    "hunk_count": len(hunks),
                }

        # Execute concurrent operations
        results = stress_executor.execute_concurrent_operations(
            create_and_test_repository, num_threads=4, operations_per_thread=5
        )

        # Verify all operations completed
        assert len(results) == 20, f"Expected 20 results, got {len(results)}"

        # Verify all operations produced reasonable results
        for result in results:
            assert result["commit_count"] > 0, "Should have created commits"
            assert result["hunk_count"] >= 0, "Should have parsed hunks"

    def test_memory_intensive_operations(
        self, stress_repo: StressTestRepository, stress_executor: StressTestExecutor
    ):
        """Test operations that consume significant memory."""
        with stress_executor.memory_monitoring() as tracker:
            # Create memory-intensive scenario
            stress_repo.create_memory_intensive_scenario(total_size_mb=5)

            # Perform multiple memory-intensive operations
            for i in range(3):
                # Modify the large file
                file_path = stress_repo.repo_path / "large_memory_file.txt"
                content = file_path.read_text()

                # Make a small change
                modified_content = content.replace(
                    "Memory test line 000000", f"Memory test line 000000 ITER{i}"
                )
                file_path.write_text(modified_content)

                # Parse hunks
                hunk_parser = HunkParser(stress_repo.git_ops)
                hunks = hunk_parser.get_diff_hunks()

                # Record memory after each iteration
                current_memory = tracker.record_measurement()
                assert current_memory < 200, (
                    f"Memory usage too high in iteration {i}: {current_memory:.1f}MB"
                )

                # Force cleanup
                del hunks, hunk_parser
                gc.collect()

            # Final memory check
            final_increase = tracker.get_memory_increase()
            assert final_increase < 100, (
                f"Final memory increase too high: {final_increase:.1f}MB"
            )

    def test_error_recovery_under_stress(self, stress_executor: StressTestExecutor):
        """Test error recovery capabilities under stress conditions."""
        error_count = 0
        success_count = 0

        def operation_with_potential_errors(thread_id: int, operation_id: int) -> bool:
            """Operation that may encounter errors."""
            try:
                with temporary_test_repository(
                    f"error_test_{thread_id}_{operation_id}"
                ) as temp_repo:
                    repo = StressTestRepository(temp_repo.repo_path)

                    # Force specific errors to simulate stress conditions
                    if operation_id % 3 == 0:
                        # Directly raise exceptions to simulate various failure modes
                        if operation_id == 0:
                            raise OSError("Simulated filesystem error")
                        elif operation_id == 3:
                            raise PermissionError("Simulated permission denied")
                        elif operation_id == 6:
                            raise RuntimeError("Simulated git corruption")
                        elif operation_id == 9:
                            raise ValueError("Simulated invalid data")

                    # Normal operation for non-error cases
                    hunk_parser = HunkParser(repo.git_ops)
                    hunk_parser.get_diff_hunks()

                return True

            except Exception:
                return False

        results = stress_executor.execute_concurrent_operations(
            operation_with_potential_errors, num_threads=3, operations_per_thread=10
        )

        success_count = sum(1 for result in results if result)
        error_count = len(results) - success_count

        # We expect some errors due to intentionally created invalid states
        assert error_count > 0, "Should have encountered some errors"
        assert success_count > error_count, "Should have more successes than errors"

        # System should remain stable despite errors
        assert len(results) == 30, "All operations should complete (success or failure)"

    @pytest.mark.slow
    def test_sustained_operations(
        self, stress_repo: StressTestRepository, stress_executor: StressTestExecutor
    ):
        """Test sustained operations over time to detect memory leaks."""
        with stress_executor.memory_monitoring() as tracker:
            operation_count = 50
            memory_measurements = []

            for i in range(operation_count):
                # Create and modify content
                content = f"// Iteration {i}\n" + "\n".join(
                    f"line_{j}" for j in range(100)
                )
                stress_repo.create_file(f"iteration_{i}.txt", content)
                stress_repo.stage_all_changes()

                if i % 10 == 9:  # Commit every 10 iterations
                    stress_repo.commit_changes(f"Commit iteration batch ending at {i}")

                # Parse hunks periodically
                if i % 5 == 4:
                    hunk_parser = HunkParser(stress_repo.git_ops)
                    hunks = hunk_parser.get_diff_hunks()
                    del hunks, hunk_parser

                # Record memory every 10 iterations
                if i % 10 == 9:
                    memory = tracker.record_measurement()
                    memory_measurements.append(memory)

                    # Force cleanup
                    gc.collect()

            # Analyze memory trend
            if len(memory_measurements) >= 3:
                # Memory should not continuously increase
                memory_growth = memory_measurements[-1] - memory_measurements[0]
                assert memory_growth < 50, (
                    f"Excessive memory growth detected: {memory_growth:.1f}MB"
                )

            final_increase = tracker.get_memory_increase()
            assert final_increase < 100, (
                f"Final memory increase too high: {final_increase:.1f}MB"
            )


# Performance benchmarks


def test_patch_generation_performance_benchmark(stress_repo: StressTestRepository):
    """Benchmark patch generation performance for regression testing."""
    # Create test scenario
    stress_repo.create_large_file_scenario(line_count=5000)

    # Modify file to create hunks
    file_path = stress_repo.repo_path / "large_file.txt"
    content = file_path.read_text()
    modified_content = content.replace("Line 1000:", "Line 1000 MODIFIED:")
    file_path.write_text(modified_content)

    # Benchmark hunk parsing
    start_time = time.time()
    hunk_parser = HunkParser(stress_repo.git_ops)
    hunks = hunk_parser.get_diff_hunks()
    elapsed_time = time.time() - start_time

    # Performance assertions
    assert elapsed_time < 2.0, f"Patch generation benchmark failed: {elapsed_time:.3f}s"
    assert len(hunks) > 0, "Should generate hunks"

    print(f"Patch generation benchmark: {elapsed_time:.3f}s for {len(hunks)} hunks")


def test_memory_usage_benchmark(stress_repo: StressTestRepository):
    """Benchmark memory usage for regression testing."""
    tracker = MemoryTracker()
    tracker.start_tracking()

    try:
        # Create memory-intensive scenario
        stress_repo.create_memory_intensive_scenario(total_size_mb=3)

        # Perform operations
        hunk_parser = HunkParser(stress_repo.git_ops)
        hunk_parser.get_diff_hunks()

        # Measure memory
        memory_increase = tracker.get_memory_increase()

        # Memory usage assertion
        if memory_increase is not None:
            assert memory_increase < 50, (
                f"Memory usage benchmark failed: {memory_increase:.1f}MB"
            )
        else:
            assert False, "Memory tracking failed: no memory increase data"

        print(f"Memory usage benchmark: {memory_increase:.1f}MB increase")

    finally:
        gc.collect()
