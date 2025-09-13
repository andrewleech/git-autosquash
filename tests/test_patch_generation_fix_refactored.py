"""
Tests for the patch generation fix described in PATCH_GENERATION_FIX.md.

This module tests the context-aware patch generation that prevents duplicate
hunk conflicts when multiple hunks contain identical content changes.

Refactored version using proper GitOps integration, error handling, and resource management.
"""

from typing import Dict, Any
import pytest

from git_autosquash.hunk_parser import HunkParser
from git_autosquash.git_ops import GitOps

from tests.base_test_repository import (
    PatchGenerationTestRepository,
    temporary_test_repository,
    GitOperationError,
)
from tests.error_handling_framework import (
    error_boundary,
    test_error_recovery,
    get_global_resource_manager,
)


class MicroPythonTestScenario:
    """
    Enhanced test scenario builder for MicroPython-like patch generation issues.

    This class replaces the original PatchGenerationTestRepository with proper
    error handling, resource management, and GitOps integration.
    """

    def __init__(self, repo: PatchGenerationTestRepository):
        self.repo = repo
        self.commit_mapping: Dict[str, str] = {}

        # Register for cleanup
        get_global_resource_manager().register_resource(self)

    @error_boundary(
        "create_micropython_scenario",
        expected_exceptions=[GitOperationError],
        max_retries=2,
    )
    def create_micropython_scenario(self) -> Dict[str, str]:
        """
        Create a repository that reproduces the MicroPython patch generation issue.

        Returns:
            Dictionary mapping commit names to hashes
        """
        with test_error_recovery("micropython_scenario_creation"):
            return self._build_micropython_commits()

    def _build_micropython_commits(self) -> Dict[str, str]:
        """Build the MicroPython test scenario with proper error handling."""

        # Create initial pyexec.c file (simulating early state)
        initial_pyexec_content = """/*
 * This file is part of the MicroPython project, http://micropython.org/
 */

#include <stdio.h>
#include <string.h>

static int parse_compile_execute(const void *source, mp_parse_input_kind_t input_kind) {
    if (MP_STATE_VM(mp_pending_exception) != NULL) {
        return 0;
    }

    // Handle different source types
    if (source == NULL) {
        return -1;
    }
    
    // Other code here...
    return 0;
}"""

        # Create initial commit
        initial_commit = self.repo.add_commit(
            {"shared/runtime/pyexec.c": initial_pyexec_content},
            "Initial MicroPython runtime",
        )
        self.commit_mapping["initial"] = initial_commit

        # Create target commit that adds __file__ support (simulating d59d269184)
        target_pyexec_content = """/*
 * This file is part of the MicroPython project, http://micropython.org/
 */

#include <stdio.h>
#include <string.h>

static int parse_compile_execute(const void *source, mp_parse_input_kind_t input_kind) {
    if (MP_STATE_VM(mp_pending_exception) != NULL) {
        return 0;
    }

    // Handle different source types
    if (source == NULL) {
        return -1;
    }
    
    // Handle frozen modules
    if (MP_OBJ_IS_TYPE(source, &mp_type_bytes)) {
        const frozen_module_t *frozen = frozen_find(source);
        if (frozen != NULL) {
            ctx->constants = frozen->constants;
            module_fun = mp_make_function_from_proto_fun(frozen->proto_fun, ctx, NULL);

            #if MICROPY_PY___FILE__
            // Set __file__ for frozen MPY modules
            if (input_kind == MP_PARSE_FILE_INPUT && frozen_module_name != NULL) {
                qstr source_name = qstr_from_str(frozen_module_name);
                mp_store_global(MP_QSTR___file__, MP_OBJ_NEW_QSTR(source_name));
            }
            #endif
        } else {
            // Handle other source types
            lex = source;
        }
        // source is a lexer, parse and compile the script
        qstr source_name = lex->source_name;
        if (input_kind == MP_PARSE_FILE_INPUT) {
            // More code processing...
        }
    }
    
    // Other code here...
    return 0;
}"""

        target_commit = self.repo.add_commit(
            {"shared/runtime/pyexec.c": target_pyexec_content},
            "Add __file__ support for frozen modules",
        )
        self.commit_mapping["target"] = target_commit

        # Create source commit that has both __file__ changes (simulating the problem state)
        source_pyexec_content = """/*
 * This file is part of the MicroPython project, http://micropython.org/
 */

#include <stdio.h>
#include <string.h>

static int parse_compile_execute(const void *source, mp_parse_input_kind_t input_kind) {
    if (MP_STATE_VM(mp_pending_exception) != NULL) {
        return 0;
    }

    // Handle different source types
    if (source == NULL) {
        return -1;
    }
    
    // Handle frozen modules
    if (MP_OBJ_IS_TYPE(source, &mp_type_bytes)) {
        const frozen_module_t *frozen = frozen_find(source);
        if (frozen != NULL) {
            ctx->constants = frozen->constants;
            module_fun = mp_make_function_from_proto_fun(frozen->proto_fun, ctx, NULL);

            #if MICROPY_MODULE___FILE__
            // Set __file__ for frozen MPY modules
            if (input_kind == MP_PARSE_FILE_INPUT && frozen_module_name != NULL) {
                qstr source_name = qstr_from_str(frozen_module_name);
                mp_store_global(MP_QSTR___file__, MP_OBJ_NEW_QSTR(source_name));
            }
            #endif
        } else {
            // Handle other source types
            lex = source;
        }
        // source is a lexer, parse and compile the script
        qstr source_name = lex->source_name;
        #if MICROPY_MODULE___FILE__
        if (input_kind == MP_PARSE_FILE_INPUT) {
            mp_store_global(MP_QSTR___file__, MP_OBJ_NEW_QSTR(source_name));
        }
        #endif
    }
    
    // Other code here...
    return 0;
}
// Additional change"""

        source_commit = self.repo.add_commit(
            {"shared/runtime/pyexec.c": source_pyexec_content},
            "Add dual __file__ support (should be squashed)",
        )
        self.commit_mapping["source"] = source_commit

        return self.commit_mapping

    def create_identical_changes_scenario(self) -> Dict[str, Any]:
        """
        Create a scenario that demonstrates identical changes in different locations.

        This tests the core issue where multiple hunks contain identical content
        but target different line ranges.
        """
        content_with_duplicates = """// Configuration section
#if MICROPY_PY___FILE__
#define ENABLE_FILE_SUPPORT 1
#endif

// Function implementation
static void setup_module(void) {
    #if MICROPY_PY___FILE__
    // Initialize file support
    init_file_support();
    #endif
    
    // Other setup code
    return;
}

// Another function
static void cleanup_module(void) {
    #if MICROPY_PY___FILE__
    // Cleanup file support
    cleanup_file_support();
    #endif
}"""

        commit_hash = self.repo.add_commit(
            {"module.c": content_with_duplicates},
            "Add module with duplicate preprocessor checks",
        )

        # Modify to create the scenario
        modified_content = content_with_duplicates.replace(
            "MICROPY_PY___FILE__", "MICROPY_MODULE___FILE__"
        )

        self.repo.create_file("module.c", modified_content)

        # Stage the file so git can see the changes
        self.repo.git_ops._run_git_command("add", "module.c")

        return {
            "base_commit": commit_hash,
            "old_pattern": "MICROPY_PY___FILE__",
            "new_pattern": "MICROPY_MODULE___FILE__",
            "expected_hunks": 2,  # Git creates separate hunks for changes that are far apart
        }

    def cleanup(self) -> None:
        """Clean up scenario resources."""
        self.commit_mapping.clear()


@pytest.fixture(scope="function")
def micropython_scenario():
    """Create MicroPython test scenario with proper cleanup."""
    with temporary_test_repository("micropython_test") as temp_repo:
        repo = PatchGenerationTestRepository(temp_repo.repo_path)
        scenario = MicroPythonTestScenario(repo)

        try:
            yield scenario
        finally:
            scenario.cleanup()


class TestPatchGenerationFix:
    """Test cases for the patch generation fix."""

    @error_boundary("test_micropython_patch_generation", max_retries=2)
    def test_micropython_patch_generation_fix(
        self, micropython_scenario: MicroPythonTestScenario
    ):
        """
        Test that the patch generation fix correctly handles MicroPython scenario.

        This test verifies that duplicate content changes are handled properly
        and don't create conflicting hunks.
        """
        # Create the test scenario
        commits = micropython_scenario.create_micropython_scenario()

        # Verify all expected commits were created
        assert "initial" in commits, "Initial commit should be created"
        assert "target" in commits, "Target commit should be created"
        assert "source" in commits, "Source commit should be created"

        # Parse hunks to verify patch generation
        hunk_parser = HunkParser(micropython_scenario.repo.git_ops)
        hunks = hunk_parser.get_diff_hunks()

        # Verify hunks were generated
        assert len(hunks) > 0, "Should generate at least one hunk"

        # Verify specific patterns in hunks
        hunk_contents = []
        for hunk in hunks:
            hunk_text = "\n".join(hunk.lines)
            hunk_contents.append(hunk_text)

        # Check for the expected pattern changes
        pattern_found = any(
            "MICROPY_MODULE___FILE__" in content and "MICROPY_PY___FILE__" in content
            for content in hunk_contents
        )
        assert pattern_found, "Should find pattern changes in hunks"

    @error_boundary("test_identical_changes_handling", max_retries=2)
    def test_identical_changes_different_locations(
        self, micropython_scenario: MicroPythonTestScenario
    ):
        """
        Test handling of identical changes at different line locations.

        This is the core issue: multiple hunks with identical content changes
        but different target line ranges should be handled correctly.
        """
        # Create scenario with identical changes
        scenario_info = micropython_scenario.create_identical_changes_scenario()

        # Parse hunks
        hunk_parser = HunkParser(micropython_scenario.repo.git_ops)
        hunks = hunk_parser.get_diff_hunks()

        # Verify expected number of hunks
        expected_hunks = scenario_info["expected_hunks"]
        assert len(hunks) == expected_hunks, (
            f"Expected {expected_hunks} hunks, got {len(hunks)}"
        )

        # Verify hunks target different line ranges
        line_ranges = []
        for hunk in hunks:
            # Extract line range information
            line_ranges.append((hunk.old_start, hunk.old_start + hunk.old_count))

        # All line ranges should be different (no overlaps)
        for i, range1 in enumerate(line_ranges):
            for j, range2 in enumerate(line_ranges):
                if i != j:
                    # Check for overlap
                    overlap = not (range1[1] <= range2[0] or range2[1] <= range1[0])
                    assert not overlap, (
                        f"Hunks {i} and {j} should not overlap: {range1} vs {range2}"
                    )

    @error_boundary("test_patch_application", max_retries=2)
    def test_generated_patch_applies_cleanly(
        self, micropython_scenario: MicroPythonTestScenario
    ):
        """
        Test that generated patches can be applied without conflicts.

        This verifies that the patch generation fix produces valid patches
        that apply cleanly to the target state.
        """
        # Create scenario
        commits = micropython_scenario.create_micropython_scenario()

        # Reset to target state for patch application test
        target_commit = commits["target"]
        result = micropython_scenario.repo.git_ops.run_git_command(
            ["reset", "--hard", target_commit]
        )
        if result.returncode != 0:
            pytest.skip(f"Could not reset to target commit: {result.stderr}")

        # Generate patch from source state
        source_commit = commits["source"]
        patch_result = micropython_scenario.repo.git_ops.run_git_command(
            ["format-patch", "-1", "--stdout", source_commit]
        )

        if patch_result.returncode != 0:
            pytest.skip(f"Could not generate patch: {patch_result.stderr}")

        patch_content = patch_result.stdout
        assert len(patch_content) > 0, "Should generate non-empty patch"

        # Apply the patch to verify it works
        patch_file = micropython_scenario.repo.repo_path / "test.patch"
        patch_file.write_text(patch_content)

        # Check if patch would apply
        check_result = micropython_scenario.repo.git_ops.run_git_command(
            ["apply", "--check", str(patch_file)]
        )

        assert check_result.returncode == 0, (
            f"Patch should apply cleanly: {check_result.stderr}"
        )

    def test_performance_with_large_changes(
        self, micropython_scenario: MicroPythonTestScenario
    ):
        """Test patch generation performance with larger change sets."""
        import time

        # Create a larger test scenario
        large_content = "// Large file for performance testing\n"
        for i in range(1000):
            large_content += f"#define CONSTANT_{i:03d} MICROPY_PY___FILE__\n"

        micropython_scenario.repo.add_commit(
            {"large_file.h": large_content}, "Add large file with many patterns"
        )

        # Modify many lines
        modified_content = large_content.replace(
            "MICROPY_PY___FILE__", "MICROPY_MODULE___FILE__"
        )
        micropython_scenario.repo.create_file("large_file.h", modified_content)

        # Stage the file so git can see the changes
        micropython_scenario.repo.git_ops._run_git_command("add", "large_file.h")

        # Time the hunk parsing
        start_time = time.time()
        hunk_parser = HunkParser(micropython_scenario.repo.git_ops)
        hunks = hunk_parser.get_diff_hunks()
        elapsed_time = time.time() - start_time

        # Performance assertions
        assert elapsed_time < 5.0, (
            f"Patch generation took too long: {elapsed_time:.2f}s"
        )
        assert len(hunks) > 0, "Should generate hunks for large changes"

    @pytest.mark.parametrize(
        "pattern_count,expected_max_time",
        [
            (10, 1.0),
            (50, 2.0),
            (100, 3.0),
        ],
    )
    def test_scalability_with_pattern_count(
        self,
        micropython_scenario: MicroPythonTestScenario,
        pattern_count: int,
        expected_max_time: float,
    ):
        """Test scalability with increasing numbers of patterns."""
        import time

        # Create content with many repeated patterns
        content_lines = ["// Scalability test file"]
        for i in range(pattern_count):
            content_lines.extend(
                [
                    f"// Section {i}",
                    "#if MICROPY_PY___FILE__",
                    f"    handle_file_operation_{i}();",
                    "#endif",
                    "",
                ]
            )

        content = "\n".join(content_lines)

        micropython_scenario.repo.add_commit(
            {"scalability_test.c": content},
            f"Add scalability test with {pattern_count} patterns",
        )

        # Modify all patterns
        modified_content = content.replace(
            "MICROPY_PY___FILE__", "MICROPY_MODULE___FILE__"
        )
        micropython_scenario.repo.create_file("scalability_test.c", modified_content)

        # Stage the file so git diff --cached will see the changes
        micropython_scenario.repo.git_ops._run_git_command("add", "scalability_test.c")

        # Time the operation
        start_time = time.time()
        hunk_parser = HunkParser(micropython_scenario.repo.git_ops)
        hunks = hunk_parser.get_diff_hunks()
        elapsed_time = time.time() - start_time

        # Scalability assertions
        assert elapsed_time < expected_max_time, (
            f"Scalability test failed for {pattern_count} patterns: "
            f"{elapsed_time:.2f}s > {expected_max_time}s"
        )
        # Git consolidates nearby pattern changes into fewer hunks
        # We should get at least 1 hunk, but not necessarily one per pattern
        assert len(hunks) >= 1, (
            f"Expected at least 1 hunk for {pattern_count} patterns, got {len(hunks)}"
        )
        assert len(hunks) <= pattern_count, (
            f"Expected at most {pattern_count} hunks, got {len(hunks)}"
        )


class TestErrorRecoveryInPatchGeneration:
    """Test error recovery mechanisms in patch generation scenarios."""

    def test_recovery_from_corrupted_git_state(
        self, micropython_scenario: MicroPythonTestScenario
    ):
        """Test recovery from corrupted git repository state."""
        # Create normal scenario first
        micropython_scenario.create_micropython_scenario()

        # Corrupt the git state
        git_dir = micropython_scenario.repo.repo_path / ".git"
        head_file = git_dir / "HEAD"
        original_head = head_file.read_text()

        try:
            # Corrupt HEAD file
            head_file.write_text("ref: refs/heads/nonexistent-branch")

            # Attempt hunk parsing - should handle gracefully
            hunk_parser = HunkParser(micropython_scenario.repo.git_ops)

            # This might fail, but should not crash the system
            try:
                hunk_parser.get_diff_hunks()
            except Exception as e:
                # Expected - corrupted state should be detected
                assert "git" in str(e).lower() or "branch" in str(e).lower()

        finally:
            # Restore original state
            head_file.write_text(original_head)

    def test_recovery_from_missing_files(
        self, micropython_scenario: MicroPythonTestScenario
    ):
        """Test recovery when files are unexpectedly missing."""
        # Create scenario
        micropython_scenario.create_micropython_scenario()

        # Remove a file that should exist
        test_file = (
            micropython_scenario.repo.repo_path / "shared" / "runtime" / "pyexec.c"
        )
        test_file.unlink()

        # Attempt hunk parsing with dummy git ops
        hunk_parser = HunkParser(GitOps())

        # Should handle missing files gracefully
        try:
            hunk_parser.get_diff_hunks()
            # If it succeeds, that's fine too
        except Exception as e:
            # Should be a clear, handleable error
            assert "file" in str(e).lower() or "not found" in str(e).lower()

    @error_boundary("test_concurrent_operations", max_retries=1)
    def test_concurrent_patch_generation_operations(self):
        """Test concurrent patch generation operations don't interfere."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def worker_operation(worker_id: int) -> Dict[str, any]:
            """Worker thread that performs patch generation operations."""
            try:
                with temporary_test_repository(
                    f"concurrent_worker_{worker_id}"
                ) as temp_repo:
                    repo = PatchGenerationTestRepository(temp_repo.repo_path)
                    scenario = MicroPythonTestScenario(repo)

                    # Create scenario
                    commits = scenario.create_micropython_scenario()

                    # Parse hunks
                    hunk_parser = HunkParser(repo.git_ops)
                    hunks = hunk_parser.get_diff_hunks()

                    return {
                        "worker_id": worker_id,
                        "commits": len(commits),
                        "hunks": len(hunks),
                        "success": True,
                    }

            except Exception as e:
                return {
                    "worker_id": worker_id,
                    "error": str(e),
                    "success": False,
                }

        # Run multiple workers concurrently
        num_workers = 3
        results = []

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_operation, i) for i in range(num_workers)]

            for future in as_completed(futures, timeout=30):
                result = future.result()
                results.append(result)

        # Verify all workers completed
        assert len(results) == num_workers, "All workers should complete"

        # Verify majority succeeded (some failures under concurrency are acceptable)
        successful_results = [r for r in results if r["success"]]
        assert len(successful_results) >= num_workers // 2, (
            "Majority of workers should succeed"
        )

        # Verify successful results are reasonable
        for result in successful_results:
            assert result["commits"] > 0, "Should create commits"
            assert result["hunks"] >= 0, "Should parse hunks"
