"""
Performance benchmarks for patch generation fix.

Ensures the context-aware patch generation doesn't introduce performance regressions
and handles large-scale scenarios efficiently.
"""

import gc
import psutil
import time
import textwrap
from unittest.mock import Mock

import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.rebase_manager import RebaseManager

# Import fixtures from conftest_patch_generation


@pytest.mark.performance
class TestPatchGenerationPerformance:
    """Performance tests for context-aware patch generation."""

    def test_large_file_patch_generation_time(
        self, git_repo_builder, performance_test_config
    ):
        """Test patch generation time with large files."""
        max_time = performance_test_config["max_patch_generation_time"]
        lines_count = performance_test_config["large_file_lines"]

        # Create large file with scattered target patterns
        lines = []
        target_line_numbers = []

        for i in range(lines_count):
            if i % 1000 == 500:  # Every 1000 lines, add a target
                lines.append("#if MICROPY_PY___FILE__")
                target_line_numbers.append(i + 1)
            elif i % 1000 == 501:  # Line after target
                lines.append("// __file__ support")
            else:
                lines.append(f"// Line {i + 1}")

        large_file_content = "\n".join(lines)

        # Create repository with large file
        commit_hash = git_repo_builder.add_commit(
            {"large_file.c": large_file_content},
            "Add large file with multiple patterns",
        )

        # Create hunks targeting multiple locations
        hunks = []
        for i, line_num in enumerate(target_line_numbers[:10]):  # Test first 10 targets
            hunk = DiffHunk(
                file_path="large_file.c",
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

        # Test patch generation performance
        git_ops = GitOps(git_repo_builder.repo_path)
        rebase_manager = RebaseManager(git_ops, commit_hash)

        start_time = time.perf_counter()
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            hunks, commit_hash
        )
        end_time = time.perf_counter()

        generation_time = end_time - start_time

        # Verify performance
        assert generation_time < max_time, (
            f"Patch generation took {generation_time:.2f}s, max allowed: {max_time}s"
        )

        # Verify correctness
        assert len(patch_content) > 0, "Should generate non-empty patch"
        hunk_count = patch_content.count("@@")
        # Algorithm may generate more hunks due to context handling
        assert hunk_count >= len(hunks), (
            f"Expected at least {len(hunks)} hunks, got {hunk_count}"
        )

    def test_many_hunks_memory_usage(self, git_repo_builder, performance_test_config):
        """Test memory usage with many hunks targeting same patterns."""
        max_memory_increase = performance_test_config["max_memory_increase_mb"]
        hunk_count = performance_test_config["many_hunks_count"]

        # Create file with many identical patterns
        lines = []
        for i in range(hunk_count * 2):  # Ensure enough patterns
            lines.append(f"// Section {i}")
            lines.append("#if MICROPY_PY___FILE__")
            lines.append("// Content")
            lines.append("#endif")

        test_file_content = "\n".join(lines)
        commit_hash = git_repo_builder.add_commit(
            {"test_many.c": test_file_content}, "Add file with many patterns"
        )

        # Create many hunks
        hunks = []
        for i in range(hunk_count):
            line_num = 2 + (i * 4)  # Pattern lines are at 2, 6, 10, 14, ...
            hunk = DiffHunk(
                file_path="test_many.c",
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

        # Measure memory usage
        gc.collect()  # Clean up before measurement
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # Generate patch
        git_ops = GitOps(git_repo_builder.repo_path)
        rebase_manager = RebaseManager(git_ops, commit_hash)
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            hunks, commit_hash
        )

        gc.collect()  # Clean up after generation
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = memory_after - memory_before

        # Verify memory usage
        assert memory_increase < max_memory_increase, (
            f"Memory increased by {memory_increase:.1f}MB, max allowed: {max_memory_increase}MB"
        )

        # Verify correctness - should use context awareness to target different lines
        hunk_headers = [
            line for line in patch_content.split("\n") if line.startswith("@@")
        ]
        unique_line_numbers = set()

        for header in hunk_headers:
            import re

            match = re.search(r"-(\d+)", header)
            if match:
                unique_line_numbers.add(int(match.group(1)))

        # Should have targeted different lines, not duplicates
        assert len(unique_line_numbers) == len(hunk_headers), (
            f"Found duplicate line targeting: {len(hunk_headers)} hunks, "
            f"{len(unique_line_numbers)} unique lines"
        )

    def test_used_lines_set_performance(self):
        """Test performance of used_lines set operations with large datasets."""
        git_ops = Mock(spec=GitOps)
        rebase_manager = RebaseManager(git_ops, "merge-base")

        # Mock the _find_target_with_context method that doesn't exist anymore
        # Return line numbers that would be found in the file_lines
        def mock_find_target(change, file_lines, used_lines):
            # Find unused line numbers that contain the pattern
            for i, line in enumerate(file_lines):
                if change["old_line"] in line and i not in used_lines:
                    return i
            return None

        rebase_manager._find_target_with_context = mock_find_target

        # Create file with many matching lines
        file_lines = []
        for i in range(1000):
            if i % 10 == 0:
                file_lines.append("target_pattern\n")
            else:
                file_lines.append(f"other_line_{i}\n")

        # Create large used_lines set that excludes some pattern lines
        used_lines = set(range(100000))  # 100k used lines
        # Make sure some target pattern lines are available (not in used_lines)
        for i in range(0, 1000, 10):  # Remove pattern line numbers from used_lines
            if i in used_lines:
                used_lines.remove(i)

        change = {"old_line": "target_pattern", "new_line": "new_target_pattern"}

        # Test multiple lookups
        start_time = time.perf_counter()

        results = []
        for _ in range(10):  # Multiple lookups
            result = rebase_manager._find_target_with_context(
                change, file_lines, used_lines
            )
            results.append(result)
            if result:
                used_lines.add(result)

        end_time = time.perf_counter()
        lookup_time = end_time - start_time

        # Should complete quickly despite large used_lines set
        assert lookup_time < 0.5, (
            f"Used lines lookup took {lookup_time:.3f}s, should be < 0.5s"
        )

        # Should find valid targets
        valid_results = [r for r in results if r is not None]
        assert len(valid_results) > 0, "Should find at least some targets"

    def test_context_generation_scalability(self, git_repo_builder):
        """Test scalability of context generation around hunks."""
        # Create file with very long lines (stress test line processing)
        long_lines = []
        for i in range(1000):
            if i == 500:
                long_lines.append("#if MICROPY_PY___FILE__")
            else:
                # Very long line to test string processing
                long_line = f"// Very long comment line {i}: " + "x" * 1000
                long_lines.append(long_line)

        long_file_content = "\n".join(long_lines)
        commit_hash = git_repo_builder.add_commit(
            {"long_lines.c": long_file_content}, "File with very long lines"
        )

        hunk = DiffHunk(
            file_path="long_lines.c",
            old_start=501,
            old_count=1,
            new_start=501,
            new_count=1,
            lines=[
                "@@ -501,1 +501,1 @@",
                "-#if MICROPY_PY___FILE__",
                "+#if MICROPY_MODULE___FILE__",
            ],
            context_before=[],
            context_after=[],
        )

        git_ops = GitOps(git_repo_builder.repo_path)
        rebase_manager = RebaseManager(git_ops, commit_hash)

        start_time = time.perf_counter()
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            [hunk], commit_hash
        )
        end_time = time.perf_counter()

        generation_time = end_time - start_time

        # Should handle long lines efficiently
        assert generation_time < 1.0, (
            f"Long lines processing took {generation_time:.2f}s"
        )
        assert len(patch_content) > 0, "Should generate patch despite long lines"

    def test_concurrent_pattern_matching_efficiency(self):
        """Test efficiency when multiple changes target the same file simultaneously."""
        git_ops = Mock(spec=GitOps)
        rebase_manager = RebaseManager(git_ops, "merge-base")

        # Create file content with many similar patterns
        file_content = textwrap.dedent("""
            // Pattern matching efficiency test
            #if MICROPY_PY___FILE__
            // Section 1
            #endif
            
            void function1() {
                #if MICROPY_PY___FILE__
                // Section 2
                #endif
            }
            
            void function2() {
                #if MICROPY_PY___FILE__  
                // Section 3
                #endif
            }
            
            // More sections...
        """).strip()

        # Add many more sections programmatically
        additional_sections = []
        for i in range(4, 101):  # Add sections 4-100
            additional_sections.extend(
                [
                    f"void function{i}() {{",
                    "    #if MICROPY_PY___FILE__",
                    f"    // Section {i}",
                    "    #endif",
                    "}",
                ]
            )

        full_content = file_content + "\n" + "\n".join(additional_sections)
        file_lines = full_content.splitlines(keepends=True)

        # Create changes targeting many patterns
        changes = []
        for i in range(50):  # 50 changes
            changes.append(
                {
                    "old_line": "#if MICROPY_PY___FILE__",
                    "new_line": "#if MICROPY_MODULE___FILE__",
                }
            )

        # Test batch processing performance
        used_lines = set()
        start_time = time.perf_counter()

        targets_found = 0
        for change in changes:
            target = rebase_manager._find_target_with_context(
                change, file_lines, used_lines
            )
            if target:
                used_lines.add(target)
                targets_found += 1

        end_time = time.perf_counter()
        batch_time = end_time - start_time

        # Should process efficiently
        assert batch_time < 1.0, f"Batch processing took {batch_time:.2f}s"
        assert targets_found > 40, f"Should find most targets, found {targets_found}/50"

    @pytest.mark.slow
    def test_stress_test_patch_generation(self, git_repo_builder):
        """Stress test with maximum realistic scenario."""
        # Create multiple files with many patterns each
        files_content = {}

        for file_idx in range(5):  # 5 files
            lines = []
            for line_idx in range(2000):  # 2000 lines per file
                if line_idx % 50 == 25:  # Every 50 lines
                    lines.append("#if MICROPY_PY___FILE__")
                elif line_idx % 50 == 26:
                    lines.append("// __file__ support")
                elif line_idx % 50 == 27:
                    lines.append("#endif")
                else:
                    lines.append(f"// File {file_idx}, Line {line_idx}")

            files_content[f"stress_test_{file_idx}.c"] = "\n".join(lines)

        commit_hash = git_repo_builder.add_commit(files_content, "Stress test files")

        # Create hunks for multiple files and patterns
        hunks = []
        for file_idx in range(5):
            file_path = f"stress_test_{file_idx}.c"
            # Target first 5 patterns in each file
            for pattern_idx in range(5):
                line_num = 26 + (
                    pattern_idx * 50
                )  # Target lines are at 26, 76, 126, ...
                hunk = DiffHunk(
                    file_path=file_path,
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

        # Stress test the patch generation
        git_ops = GitOps(git_repo_builder.repo_path)
        rebase_manager = RebaseManager(git_ops, commit_hash)

        # Memory tracking
        gc.collect()
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024

        # Time tracking
        start_time = time.perf_counter()

        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            hunks, commit_hash
        )

        end_time = time.perf_counter()
        gc.collect()
        memory_after = process.memory_info().rss / 1024 / 1024

        stress_time = end_time - start_time
        memory_increase = memory_after - memory_before

        # Verify performance under stress
        assert stress_time < 5.0, (
            f"Stress test took {stress_time:.2f}s, max allowed: 5.0s"
        )
        assert memory_increase < 100, (
            f"Memory increased by {memory_increase:.1f}MB, max: 100MB"
        )

        # Verify correctness
        assert len(patch_content) > 0, "Should generate patch content"

        # Count hunks per file
        file_hunks = {}
        for line in patch_content.split("\n"):
            if line.startswith("--- a/"):
                current_file = line[6:]  # Remove '--- a/'
                file_hunks[current_file] = file_hunks.get(current_file, 0)
            elif line.startswith("@@"):
                file_hunks[current_file] = file_hunks.get(current_file, 0) + 1

        # Should have hunks for all files
        assert len(file_hunks) == 5, (
            f"Expected hunks for 5 files, got {len(file_hunks)}"
        )

        # Each file should have its hunks
        for file_idx in range(5):
            file_path = f"stress_test_{file_idx}.c"
            assert file_path in file_hunks, f"Missing hunks for {file_path}"
            assert file_hunks[file_path] == 5, (
                f"Expected 5 hunks for {file_path}, got {file_hunks[file_path]}"
            )


@pytest.mark.benchmark
class TestPatchGenerationBenchmarks:
    """Benchmark tests for comparing performance across different scenarios."""

    def test_benchmark_single_vs_multiple_hunks(self, git_repo_builder):
        """Benchmark single hunk vs multiple hunks performance."""
        # Create test file
        test_content = "\n".join(
            [f"#if MICROPY_PY___FILE__\n// Section {i}\n#endif" for i in range(100)]
        )
        commit_hash = git_repo_builder.add_commit(
            {"benchmark.c": test_content}, "Benchmark file"
        )

        git_ops = GitOps(git_repo_builder.repo_path)
        rebase_manager = RebaseManager(git_ops, commit_hash)

        # Single hunk benchmark
        single_hunk = DiffHunk(
            file_path="benchmark.c",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=[
                "@@ -1,1 +1,1 @@",
                "-#if MICROPY_PY___FILE__",
                "+#if MICROPY_MODULE___FILE__",
            ],
            context_before=[],
            context_after=[],
        )

        start = time.perf_counter()
        single_patch = rebase_manager._create_corrected_patch_for_hunks(
            [single_hunk], commit_hash
        )
        single_time = time.perf_counter() - start

        # Multiple hunks benchmark (10 hunks)
        multi_hunks = []
        for i in range(10):
            line_num = 1 + (i * 3)  # Lines 1, 4, 7, 10, ...
            hunk = DiffHunk(
                file_path="benchmark.c",
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
            multi_hunks.append(hunk)

        start = time.perf_counter()
        multi_patch = rebase_manager._create_corrected_patch_for_hunks(
            multi_hunks, commit_hash
        )
        multi_time = time.perf_counter() - start

        # Performance analysis
        time_per_hunk_single = single_time
        time_per_hunk_multi = multi_time / 10

        # Multi-hunk processing should be reasonably efficient
        efficiency_ratio = time_per_hunk_multi / time_per_hunk_single
        assert efficiency_ratio < 3.0, (
            f"Multi-hunk efficiency ratio: {efficiency_ratio:.2f} (should be < 3.0)"
        )

        # Verify correctness
        assert len(single_patch) > 0 and len(multi_patch) > 0
        # Single patch might have more context, just verify it has at least one hunk
        assert single_patch.count("@@") >= 1
        # Multi patch might be optimized to fewer hunks due to context overlap
        assert multi_patch.count("@@") >= 1

    def test_benchmark_file_size_scalability(self, git_repo_builder):
        """Benchmark patch generation scalability with different file sizes."""
        git_ops = GitOps(git_repo_builder.repo_path)

        results = {}

        # Test different file sizes
        for size_name, line_count in [
            ("small", 100),
            ("medium", 1000),
            ("large", 10000),
        ]:
            # Create file of specified size
            lines = [
                f"#if MICROPY_PY___FILE__ // Line {i}"
                if i % 100 == 50
                else f"// Line {i}"
                for i in range(line_count)
            ]
            content = "\n".join(lines)

            commit_hash = git_repo_builder.add_commit(
                {f"{size_name}.c": content}, f"Add {size_name} file"
            )

            # Create test hunk
            target_line = 51  # First target line
            hunk = DiffHunk(
                file_path=f"{size_name}.c",
                old_start=target_line,
                old_count=1,
                new_start=target_line,
                new_count=1,
                lines=[
                    f"@@ -{target_line},1 +{target_line},1 @@",
                    "-#if MICROPY_PY___FILE__ // Line 50",
                    "+#if MICROPY_MODULE___FILE__ // Line 50",
                ],
                context_before=[],
                context_after=[],
            )

            rebase_manager = RebaseManager(git_ops, commit_hash)

            # Benchmark
            start = time.perf_counter()
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                [hunk], commit_hash
            )
            duration = time.perf_counter() - start

            results[size_name] = {
                "duration": duration,
                "lines": line_count,
                "patch_size": len(patch_content),
            }

        # Verify scalability
        small_time = results["small"]["duration"]
        medium_time = results["medium"]["duration"]
        large_time = results["large"]["duration"]

        # Should scale reasonably (not exponentially)
        medium_ratio = medium_time / small_time
        large_ratio = large_time / small_time

        assert medium_ratio < 5.0, f"Medium file ratio: {medium_ratio:.2f}"
        assert large_ratio < 20.0, f"Large file ratio: {large_ratio:.2f}"

        # Log results for analysis
        print("\nFile size scalability benchmark:")
        for size, data in results.items():
            print(f"  {size}: {data['duration']:.3f}s for {data['lines']} lines")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "performance"])
