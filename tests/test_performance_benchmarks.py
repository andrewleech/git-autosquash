"""Performance benchmarks for git-autosquash operations."""

import time
from unittest.mock import Mock
from typing import List

import pytest

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.main import _apply_ignored_hunks, _create_combined_patch
from git_autosquash.tui.state_controller import UIStateController


def create_mock_hunks(num_hunks: int) -> List[DiffHunk]:
    """Create mock hunks for performance testing."""
    hunks = []
    for i in range(num_hunks):
        hunk = DiffHunk(
            file_path=f"file_{i % 100}.py",  # Distribute across 100 files
            old_start=i + 1,
            old_count=1,
            new_start=i + 1,
            new_count=2,
            lines=[
                f"@@ -{i + 1},1 +{i + 1},2 @@",
                f" existing line {i}",
                f"+new line {i}",
            ],
            context_before=[],
            context_after=[],
        )
        hunks.append(hunk)
    return hunks


def create_mock_mappings(hunks: List[DiffHunk]) -> List[HunkTargetMapping]:
    """Create mock hunk target mappings for performance testing."""
    mappings = []
    for i, hunk in enumerate(hunks):
        mapping = HunkTargetMapping(
            hunk=hunk,
            target_commit=f"commit_{i % 50}",  # Distribute across 50 commits
            confidence="high" if i % 3 == 0 else "medium",
            blame_info=[],
        )
        mappings.append(mapping)
    return mappings


class TestPerformanceBenchmarks:
    """Performance benchmarks for large repository scenarios."""

    @pytest.mark.parametrize("num_hunks", [100, 500, 1000, 2000])
    def test_patch_creation_performance(self, num_hunks: int) -> None:
        """Benchmark patch creation for various numbers of hunks."""
        hunks = create_mock_hunks(num_hunks)
        mappings = create_mock_mappings(hunks)

        start_time = time.perf_counter()
        patch_content = _create_combined_patch(mappings)
        end_time = time.perf_counter()

        execution_time = end_time - start_time

        # Performance assertions - should be fast even for large numbers
        assert execution_time < 1.0, (
            f"Patch creation too slow for {num_hunks} hunks: {execution_time:.3f}s"
        )

        # Verify patch contains expected content
        assert len(patch_content) > 0
        assert "file_0.py" in patch_content
        assert f"file_{min(99, num_hunks - 1)}.py" in patch_content

        print(f"✓ Created patch for {num_hunks} hunks in {execution_time:.3f}s")

    @pytest.mark.parametrize("num_mappings", [100, 500, 1000, 2000])
    def test_ui_state_controller_performance(self, num_mappings: int) -> None:
        """Benchmark UI state operations for large numbers of mappings."""
        hunks = create_mock_hunks(num_mappings)
        mappings = create_mock_mappings(hunks)

        controller = UIStateController(mappings)

        # Test bulk approve operation performance
        start_time = time.perf_counter()
        controller.approve_all()
        end_time = time.perf_counter()
        approve_time = end_time - start_time

        # Test individual lookup performance
        start_time = time.perf_counter()
        for i in range(min(100, num_mappings)):  # Test first 100 lookups
            controller.is_approved(mappings[i])
            controller.is_ignored(mappings[i])
        end_time = time.perf_counter()
        lookup_time = end_time - start_time

        # Test bulk toggle operation performance
        start_time = time.perf_counter()
        controller.ignore_all_toggle()
        end_time = time.perf_counter()
        toggle_time = end_time - start_time

        # Performance assertions - should be O(1) or O(log n)
        assert approve_time < 0.1, (
            f"Approve all too slow for {num_mappings} mappings: {approve_time:.3f}s"
        )
        assert lookup_time < 0.01, (
            f"Individual lookups too slow: {lookup_time:.3f}s for 100 lookups"
        )
        assert toggle_time < 0.1, (
            f"Ignore toggle too slow for {num_mappings} mappings: {toggle_time:.3f}s"
        )

        # Verify correctness - after ignore_all_toggle, everything should be ignored
        # and approved state is cleared (since ignore and approve are mutually exclusive)
        stats = controller.get_progress_stats()
        assert stats["total"] == num_mappings
        assert stats["approved"] == 0  # Cleared by ignore_all_toggle
        assert stats["ignored"] == num_mappings

        print(
            f"✓ UI operations for {num_mappings} mappings: approve={approve_time:.3f}s, lookup={lookup_time:.3f}s, toggle={toggle_time:.3f}s"
        )

    @pytest.mark.parametrize("num_mappings", [100, 500, 1000])
    def test_mapping_processing_performance(self, num_mappings: int) -> None:
        """Benchmark processing performance for large numbers of pre-existing mappings."""
        hunks = create_mock_hunks(num_mappings)
        mappings = create_mock_mappings(hunks)

        # Test various operations that would be performed in the application
        start_time = time.perf_counter()

        # Simulate filtering mappings by confidence
        high_confidence = [m for m in mappings if m.confidence == "high"]
        medium_confidence = [m for m in mappings if m.confidence == "medium"]

        # Simulate grouping by commit
        from collections import defaultdict

        by_commit = defaultdict(list)
        for mapping in mappings:
            by_commit[mapping.target_commit].append(mapping)

        # Simulate sorting by file path
        sorted_mappings = sorted(mappings, key=lambda m: m.hunk.file_path)

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Performance assertions - should be fast for data processing
        assert execution_time < 0.5, (
            f"Mapping processing too slow for {num_mappings} mappings: {execution_time:.3f}s"
        )

        # Verify results
        assert len(high_confidence) + len(medium_confidence) == num_mappings
        assert len(by_commit) > 0
        assert len(sorted_mappings) == num_mappings

        print(f"✓ Processed {num_mappings} mappings in {execution_time:.3f}s")

    def test_large_repository_end_to_end_simulation(self) -> None:
        """Simulate end-to-end performance for a large repository scenario."""
        # Simulate a large feature branch with many changes
        num_hunks = 1500
        hunks = create_mock_hunks(num_hunks)
        mappings = create_mock_mappings(hunks)

        # Mock git operations for realistic simulation
        git_ops = Mock()
        git_ops.repo_path = "/test/large/repo"
        git_ops._run_git_command.return_value = (True, "stash-ref-large-test")
        git_ops._run_git_command_with_input.return_value = (
            True,
            "Applied successfully",
        )

        # Time the complete ignored hunks application
        start_time = time.perf_counter()
        result = _apply_ignored_hunks(mappings, git_ops)
        end_time = time.perf_counter()

        execution_time = end_time - start_time

        assert result is True
        # Should handle large repositories efficiently
        assert execution_time < 1.0, (
            f"Large repository simulation too slow: {execution_time:.3f}s"
        )

        # Verify git-native approach: n hunks staged + validation + final apply
        expected_calls = (
            num_hunks + 2
        )  # stage each hunk individually + validate + apply
        assert git_ops._run_git_command_with_input.call_count == expected_calls

        # Verify cleanup occurred (uses actual stash reference format)
        git_ops._run_git_command.assert_any_call("stash", "drop", "stash@{0}")

        print(
            f"✓ Large repository simulation ({num_hunks} hunks) completed in {execution_time:.3f}s"
        )

    def test_memory_usage_with_large_datasets(self) -> None:
        """Test memory efficiency with large numbers of hunks."""
        import gc

        # Get baseline memory usage
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Create large dataset
        num_hunks = 2000
        hunks = create_mock_hunks(num_hunks)
        mappings = create_mock_mappings(hunks)

        # Create UI state controller
        controller = UIStateController(mappings)
        controller.approve_all()

        # Create combined patch
        patch_content = _create_combined_patch(mappings)

        # Measure memory usage
        gc.collect()
        final_objects = len(gc.get_objects())
        objects_created = final_objects - initial_objects

        # Memory usage should be reasonable
        # Allow for some overhead but shouldn't be excessive
        max_expected_objects = num_hunks * 10  # Allow 10x overhead factor
        assert objects_created < max_expected_objects, (
            f"Memory usage too high: {objects_created} objects for {num_hunks} hunks"
        )

        # Verify functionality still works correctly
        stats = controller.get_progress_stats()
        assert stats["total"] == num_hunks
        assert len(patch_content) > 1000  # Should be substantial patch content

        print(f"✓ Memory test: {objects_created} objects created for {num_hunks} hunks")

    def test_concurrent_access_performance(self) -> None:
        """Test performance under simulated concurrent access patterns."""
        num_mappings = 1000
        hunks = create_mock_hunks(num_mappings)
        mappings = create_mock_mappings(hunks)

        controller = UIStateController(mappings)

        # Simulate rapid state changes (like user clicking through UI quickly)
        start_time = time.perf_counter()

        for i in range(100):  # 100 rapid operations
            mapping_idx = i % num_mappings
            controller.set_approved(mappings[mapping_idx], True)
            controller.set_ignored(mappings[mapping_idx], i % 2 == 0)
            controller.is_approved(mappings[mapping_idx])
            controller.get_progress_stats()

        end_time = time.perf_counter()
        execution_time = end_time - start_time

        # Should handle rapid operations efficiently
        assert execution_time < 0.1, (
            f"Concurrent access simulation too slow: {execution_time:.3f}s"
        )

        print(f"✓ Concurrent access test: 400 operations in {execution_time:.3f}s")


if __name__ == "__main__":
    # Run benchmarks if executed directly
    test = TestPerformanceBenchmarks()

    print("🚀 Starting performance benchmarks...")

    # Run key benchmarks
    test.test_patch_creation_performance(1000)
    test.test_ui_state_controller_performance(1000)
    test.test_large_repository_end_to_end_simulation()
    test.test_memory_usage_with_large_datasets()
    test.test_concurrent_access_performance()

    print("✅ All performance benchmarks completed successfully!")
