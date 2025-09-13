"""
Stress tests for patch generation under extreme conditions.

These tests verify patch generation performance and memory usage under
high-load scenarios, concurrent operations, and resource constraints.
"""

import gc
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from tests.base_test_repository import StressTestRepository, temporary_test_repository
from tests.error_handling_framework import error_boundary


class ImprovedStressTestBuilder(StressTestRepository):
    """
    Improved builder for creating stress test scenarios using GitOps.

    This replaces the old StressTestBuilder that used direct subprocess calls
    with proper GitOps integration and resource management.
    """

    @error_boundary("massive_repository_creation", max_retries=2)
    def create_massive_repository(
        self,
        num_files: int = 50,  # Reduced for better performance
        lines_per_file: int = 500,  # Reduced for better performance
        patterns_per_file: int = 10,  # Reduced for better performance
    ) -> Dict[str, Any]:
        """Create repository with massive number of files and patterns using GitOps."""

        files_content = {}

        for file_idx in range(num_files):
            content_lines = []

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
                else:
                    # Add regular code
                    content_lines.append(f"// File {file_idx} Line {line_idx}")
                    if line_idx % 10 == 5:
                        content_lines.append(
                            f"void function_{file_idx}_{line_idx}() {{ }}"
                        )

            filename = f"massive_{file_idx:03d}.c"
            files_content[filename] = "\n".join(content_lines)

        # Use base class method that uses GitOps
        base_commit = self.add_commit(files_content, "Massive repository base")

        # Create target commit
        target_commit = self.commit_changes(
            "Target for massive squash", allow_empty=True
        )

        # Update all patterns in all files
        modified_files = {}
        for filename, content in files_content.items():
            # Update patterns to create massive diff
            updated_content = content.replace("MASSIVE_PATTERN_", "UPDATED_PATTERN_")
            modified_files[filename] = updated_content

        change_commit = self.add_commit(modified_files, "Update all patterns")

        return {
            "base_commit": base_commit,
            "target_commit": target_commit,
            "change_commit": change_commit,
            "num_files": num_files,
            "lines_per_file": lines_per_file,
            "patterns_per_file": patterns_per_file,
        }

    @error_boundary("deep_history_creation", max_retries=2)
    def create_deep_history_scenario(
        self, history_depth: int = 20
    ) -> Dict[str, Any]:  # Reduced depth
        """Create repository with very deep commit history using GitOps."""

        # Create base file
        base_content = """// Deep history test file
#if HISTORY_PATTERN_0
void base_function() {
    // Base implementation
}
#endif
"""

        base_commit = self.add_commit(
            {"deep_history.c": base_content}, "Deep history base"
        )

        # Create deep commit history
        commits = [base_commit]
        current_content = base_content

        for depth in range(1, history_depth):
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

            current_content = new_pattern_content
            commit_hash = self.add_commit(
                {"deep_history.c": new_pattern_content}, f"Depth {depth} commit"
            )
            commits.append(commit_hash)

        # Create final commit that modifies patterns across history
        final_content = current_content
        # Change first few patterns
        for i in range(min(5, history_depth)):
            final_content = final_content.replace(
                f"HISTORY_PATTERN_{i}", f"UPDATED_PATTERN_{i}"
            )

        final_commit = self.add_commit(
            {"deep_history.c": final_content}, "Update historical patterns"
        )

        return {
            "base_commit": base_commit,
            "history_commits": commits,
            "final_commit": final_commit,
            "history_depth": history_depth,
        }

    @error_boundary("concurrent_scenario_creation", max_retries=2)
    def create_concurrent_operation_scenario(self) -> Dict[str, Any]:
        """Create scenario for testing concurrent operations using GitOps."""

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

        base_commit = self.add_commit(concurrent_files, "Concurrent test base")

        # Create multiple target commits for different files
        target_commits = []
        for i in range(3):  # Create 3 target commits
            target_commit = self.commit_changes(f"Target {i}", allow_empty=True)
            target_commits.append(target_commit)

        # Update files with patterns
        updated_files = {}
        for filename, content in concurrent_files.items():
            updated_content = content.replace("CONCURRENT_PATTERN_", "NEW_CONCURRENT_")
            updated_files[filename] = updated_content

        change_commit = self.add_commit(updated_files, "Update concurrent patterns")

        return {
            "base_commit": base_commit,
            "target_commits": target_commits,
            "change_commit": change_commit,
            "num_files": len(concurrent_files),
        }


class MemoryTracker:
    """Track memory usage during stress tests with proper resource management."""

    def __init__(self):
        self.start_memory = None
        self.peak_memory = 0
        self.monitoring = False
        self._process = None

    def start_tracking(self):
        """Start memory tracking with error handling."""
        try:
            import psutil

            self._process = psutil.Process()
            self.start_memory = self._process.memory_info().rss / 1024 / 1024  # MB
            self.peak_memory = self.start_memory
            self.monitoring = True
        except ImportError:
            # psutil not available - use basic tracking
            self.start_memory = 0
            self.peak_memory = 0
            self.monitoring = False

    def update_peak(self):
        """Update peak memory usage."""
        if not self.monitoring or self._process is None:
            return

        try:
            current = self._process.memory_info().rss / 1024 / 1024
            if current > self.peak_memory:
                self.peak_memory = current
        except Exception:
            # Handle process monitoring errors gracefully
            pass

    def get_memory_delta(self) -> float:
        """Get memory usage delta in MB."""
        if not self.monitoring or self.start_memory is None:
            return 0.0

        try:
            current = self._process.memory_info().rss / 1024 / 1024
            return current - self.start_memory
        except Exception:
            return 0.0

    def cleanup(self):
        """Clean up tracking resources."""
        self.monitoring = False
        self._process = None


@pytest.fixture
def stress_test_repo():
    """Provide a stress test repository with proper cleanup."""
    with temporary_test_repository("stress_test_repo") as repo:
        builder = ImprovedStressTestBuilder(repo.repo_path)
        yield builder


class TestMassiveRepositoryHandling:
    """Test handling of repositories with massive amounts of data."""

    def test_massive_file_generation_memory_usage(self, stress_test_repo):
        """Test memory usage during massive file scenario generation."""
        memory_tracker = MemoryTracker()
        memory_tracker.start_tracking()

        # Create smaller scenario for CI stability
        scenario = stress_test_repo.create_massive_repository(
            num_files=20, lines_per_file=200, patterns_per_file=5
        )

        memory_tracker.update_peak()
        memory_delta = memory_tracker.get_memory_delta()

        # Verify scenario was created
        assert "base_commit" in scenario
        assert "change_commit" in scenario
        assert scenario["num_files"] == 20

        # Memory should be reasonable (less than 100MB delta)
        assert memory_delta < 100, f"Memory usage too high: {memory_delta}MB"

        memory_tracker.cleanup()

    def test_hunk_parser_massive_diff_handling(self, stress_test_repo):
        """Test hunk parser performance with massive diffs."""
        scenario = stress_test_repo.create_massive_repository(
            num_files=10, lines_per_file=100, patterns_per_file=3
        )

        git_ops = GitOps(stress_test_repo.repo_path)

        # Generate diff between base and change commits
        diff_result = git_ops.run_git_command(
            ["diff", scenario["base_commit"], scenario["change_commit"]]
        )

        assert diff_result.returncode == 0
        diff_content = diff_result.stdout

        # Parse the massive diff
        memory_tracker = MemoryTracker()
        memory_tracker.start_tracking()

        start_time = time.time()
        hunk_parser = HunkParser(git_ops)
        hunks = hunk_parser._parse_diff_output(diff_content)
        parsing_time = time.time() - start_time

        memory_tracker.update_peak()
        memory_delta = memory_tracker.get_memory_delta()

        # Verify parsing results
        assert len(hunks) > 0
        assert parsing_time < 10.0, f"Parsing took too long: {parsing_time:.2f}s"
        assert memory_delta < 50, f"Parsing used too much memory: {memory_delta}MB"

        memory_tracker.cleanup()


class TestDeepHistoryHandling:
    """Test handling of repositories with deep commit history."""

    def test_deep_history_blame_performance(self, stress_test_repo):
        """Test blame analysis performance with deep history."""
        stress_test_repo.create_deep_history_scenario(history_depth=10)

        git_ops = GitOps(stress_test_repo.repo_path)

        # Test blame performance
        start_time = time.time()
        blame_result = git_ops.run_git_command(["blame", "deep_history.c"])
        blame_time = time.time() - start_time

        assert blame_result.returncode == 0
        assert blame_time < 5.0, f"Blame analysis took too long: {blame_time:.2f}s"

        # Verify blame output contains expected patterns
        blame_output = blame_result.stdout
        assert "UPDATED_PATTERN_" in blame_output or "HISTORY_PATTERN_" in blame_output


class TestConcurrentOperations:
    """Test concurrent operations and thread safety."""

    def test_concurrent_hunk_parsing(self, stress_test_repo):
        """Test concurrent hunk parsing operations."""
        scenario = stress_test_repo.create_concurrent_operation_scenario()

        git_ops = GitOps(stress_test_repo.repo_path)

        # Generate diff
        diff_result = git_ops.run_git_command(
            ["diff", scenario["base_commit"], scenario["change_commit"]]
        )

        assert diff_result.returncode == 0
        diff_content = diff_result.stdout

        def parse_hunks_worker(worker_id: int) -> int:
            """Worker function for concurrent hunk parsing."""
            hunk_parser = HunkParser(git_ops)
            hunks = hunk_parser._parse_diff_output(diff_content)
            return len(hunks)

        # Run concurrent parsing
        memory_tracker = MemoryTracker()
        memory_tracker.start_tracking()

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(parse_hunks_worker, i) for i in range(8)]

            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                memory_tracker.update_peak()

        concurrent_time = time.time() - start_time
        memory_delta = memory_tracker.get_memory_delta()

        # Verify all workers got consistent results
        assert len(results) == 8
        assert all(r == results[0] for r in results), (
            "Concurrent parsing results inconsistent"
        )
        assert concurrent_time < 15.0, (
            f"Concurrent parsing took too long: {concurrent_time:.2f}s"
        )
        assert memory_delta < 100, (
            f"Concurrent operations used too much memory: {memory_delta}MB"
        )

        memory_tracker.cleanup()

    def test_resource_cleanup_under_stress(self, stress_test_repo):
        """Test that resources are properly cleaned up under stress conditions."""
        initial_memory = MemoryTracker()
        initial_memory.start_tracking()

        # Create multiple scenarios to stress resource usage
        scenarios = []

        for i in range(5):  # Reduced iterations for CI stability
            scenario = stress_test_repo.create_concurrent_operation_scenario()
            scenarios.append(scenario)

            # Force garbage collection
            gc.collect()
            initial_memory.update_peak()

        memory_delta = initial_memory.get_memory_delta()

        # Memory growth should be reasonable
        assert memory_delta < 200, f"Memory leak detected: {memory_delta}MB growth"

        initial_memory.cleanup()


class TestErrorRecoveryUnderStress:
    """Test error recovery mechanisms under stress conditions."""

    def test_git_operation_failure_recovery(self, stress_test_repo):
        """Test recovery from git operation failures during stress testing."""

        # Create a scenario that might cause git operations to fail
        stress_test_repo.create_massive_repository(
            num_files=5, lines_per_file=50, patterns_per_file=2
        )

        git_ops = GitOps(stress_test_repo.repo_path)

        # Test that the repository is in a valid state after stress operations
        status_result = git_ops.run_git_command(["status", "--porcelain"])
        assert status_result.returncode == 0

        # Verify we can still perform basic operations
        log_result = git_ops.run_git_command(["log", "--oneline", "-5"])
        assert log_result.returncode == 0

        log_output = log_result.stdout
        assert "Update all patterns" in log_output
        assert "Massive repository base" in log_output

    def test_memory_pressure_handling(self, stress_test_repo):
        """Test handling of operations under memory pressure."""
        memory_tracker = MemoryTracker()
        memory_tracker.start_tracking()

        # Create scenario that uses significant memory
        scenario = stress_test_repo.create_deep_history_scenario(history_depth=5)

        # Perform operations that might stress memory
        git_ops = GitOps(stress_test_repo.repo_path)

        # Generate large diff
        diff_result = git_ops.run_git_command(
            ["diff", scenario["base_commit"], scenario["final_commit"]]
        )

        memory_tracker.update_peak()

        assert diff_result.returncode == 0

        # Parse the diff
        hunk_parser = HunkParser(git_ops)
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        memory_tracker.update_peak()
        memory_delta = memory_tracker.get_memory_delta()

        # Should handle memory pressure gracefully
        assert len(hunks) > 0
        assert memory_delta < 150, (
            f"Memory usage under pressure too high: {memory_delta}MB"
        )

        memory_tracker.cleanup()


if __name__ == "__main__":
    # Run basic stress test
    with temporary_test_repository("manual_stress_test") as repo:
        builder = ImprovedStressTestBuilder(repo.repo_path)

        print("Creating massive repository scenario...")
        scenario = builder.create_massive_repository(
            num_files=5, lines_per_file=100, patterns_per_file=3
        )
        print(f"Created scenario with {scenario['num_files']} files")

        print("Testing hunk parsing...")
        git_ops = GitOps(builder.repo_path)
        diff_result = git_ops.run_git_command(
            ["diff", scenario["base_commit"], scenario["change_commit"]]
        )

        hunk_parser = HunkParser(git_ops)
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)
        print(f"Parsed {len(hunks)} hunks successfully")

        print("Stress test completed successfully!")
