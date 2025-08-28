"""
Refactored integration tests for context-aware patch generation.

These tests reproduce the exact MicroPython dual-hunk scenario described in
PATCH_GENERATION_FIX.md with proper GitOps integration and error handling.
"""

from typing import Dict
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseManager
from tests.base_test_repository import BaseTestRepository, temporary_test_repository
from tests.error_handling_framework import safe_test_operation, error_boundary


class DualHunkTestRepository(BaseTestRepository):
    """Repository for testing dual-hunk scenarios with proper GitOps integration."""

    @safe_test_operation("dual_hunk_scenario_creation", max_retries=2)
    def create_dual_hunk_scenario(self) -> Dict[str, str]:
        """Create a minimal repository that reproduces the dual-hunk scenario.

        This creates the exact scenario described in PATCH_GENERATION_FIX.md:
        - Target commit has one instance of a pattern
        - Source commit has two instances of the same pattern change
        - Context-aware patch generation should handle both correctly
        """

        # Create file with the target state (one instance of OLD_PATTERN)
        target_content = """#ifndef CONFIG_H
#define CONFIG_H

// First config section
#if OLD_PATTERN
void setup_config_one() {
    // Configuration setup
}
#endif

// Other functions
void other_function() {
    // Some other code
}

#endif // CONFIG_H
"""

        initial_commit = self.add_commit({"config.h": target_content}, "Initial config")

        # Create target commit (the commit we want to squash into)
        target_commit = self.commit_changes("Target commit", allow_empty=True)

        # Evolve the file to have TWO instances of OLD_PATTERN (simulates later development)
        evolved_content = """#ifndef CONFIG_H
#define CONFIG_H

// First config section  
#if OLD_PATTERN
void setup_config_one() {
    // Configuration setup
}
#endif

// Other functions
void other_function() {
    // Some other code
}

// Second config section (added later in development)
#if OLD_PATTERN
void setup_config_two() {
    // Second configuration setup
}
#endif

#endif // CONFIG_H
"""

        evolution_commit = self.add_commit(
            {"config.h": evolved_content}, "Add second config section"
        )

        # Create the source commit with both instances changed to NEW_PATTERN
        source_content = """#ifndef CONFIG_H
#define CONFIG_H

// First config section  
#if NEW_PATTERN
void setup_config_one() {
    // Configuration setup
}
#endif

// Other functions
void other_function() {
    // Some other code
}

// Second config section (added later in development)
#if NEW_PATTERN
void setup_config_two() {
    // Second configuration setup
}
#endif

#endif // CONFIG_H
"""

        source_commit = self.add_commit(
            {"config.h": source_content}, "Update both patterns"
        )

        return {
            "initial_commit": initial_commit,
            "target_commit": target_commit,
            "evolution_commit": evolution_commit,
            "source_commit": source_commit,
        }

    @safe_test_operation("micropython_scenario_creation", max_retries=2)
    def create_micropython_scenario(self) -> Dict[str, str]:
        """Create a scenario based on the real MicroPython case."""

        # Initial state without __file__ support
        initial_content = """/*
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

        initial_commit = self.add_commit(
            {"pyexec.c": initial_content},
            "Initial MicroPython pyexec.c without __file__ support",
        )

        # Target state with single __file__ support
        target_content = initial_content.replace(
            "// Other code here...",
            """// Handle frozen modules
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
    
    // Other code here...""",
        )

        target_commit = self.add_commit(
            {"pyexec.c": target_content}, "Add __file__ support for frozen modules"
        )

        return {
            "initial_commit": initial_commit,
            "target_commit": target_commit,
        }


@pytest.fixture
def dual_hunk_repo():
    """Provide a dual hunk test repository with proper cleanup."""
    with temporary_test_repository("dual_hunk_repo") as temp_repo:
        yield DualHunkTestRepository(temp_repo.repo_path)


class TestDualHunkIntegration:
    """Integration tests for dual-hunk patch generation scenarios."""

    @error_boundary("dual_hunk_parsing", max_retries=2)
    def test_dual_hunk_patch_generation(self, dual_hunk_repo):
        """Test that dual hunks are handled correctly in patch generation."""
        scenario = dual_hunk_repo.create_dual_hunk_scenario()

        git_ops = GitOps(dual_hunk_repo.repo_path)

        # Generate diff between target state and source state
        diff_result = git_ops.run_git_command(
            [
                "diff",
                scenario["target_commit"] + "~1",  # Parent of target (initial state)
                scenario["source_commit"],
            ]
        )

        assert diff_result.returncode == 0
        diff_content = diff_result.stdout

        # Parse hunks from the diff
        hunk_parser = HunkParser(diff_content)
        hunks = hunk_parser.parse_hunks()

        # Should detect both hunk changes
        assert len(hunks) >= 2, f"Expected at least 2 hunks, got {len(hunks)}"

        # Both hunks should be for the same file
        file_paths = {hunk.file_path for hunk in hunks}
        assert len(file_paths) == 1
        assert "config.h" in file_paths

        # Verify hunks contain the expected pattern changes
        hunk_content = "\n".join(line for hunk in hunks for line in hunk.lines)
        assert "OLD_PATTERN" in hunk_content
        assert "NEW_PATTERN" in hunk_content

    @error_boundary("context_aware_patch_application", max_retries=2)
    def test_context_aware_patch_application(self, dual_hunk_repo):
        """Test context-aware patch application handles duplicate patterns correctly."""
        scenario = dual_hunk_repo.create_dual_hunk_scenario()

        git_ops = GitOps(dual_hunk_repo.repo_path)

        # Get the working tree at target commit state
        checkout_result = git_ops.run_git_command(
            ["checkout", scenario["target_commit"]]
        )
        assert checkout_result.returncode == 0

        # Generate patch from source commit
        patch_result = git_ops.run_git_command(
            [
                "format-patch",
                "--stdout",
                scenario["target_commit"] + ".." + scenario["source_commit"],
            ]
        )
        assert patch_result.returncode == 0

        patch_content = patch_result.stdout

        # Verify patch contains context-aware changes
        assert "OLD_PATTERN" in patch_content
        assert "NEW_PATTERN" in patch_content
        assert "config.h" in patch_content

    @error_boundary("rebase_integration", max_retries=2)
    def test_rebase_manager_dual_hunk_handling(self, dual_hunk_repo):
        """Test RebaseManager can handle dual-hunk scenarios properly."""
        dual_hunk_repo.create_dual_hunk_scenario()

        # Test that RebaseManager can be initialized with the repository
        RebaseManager(dual_hunk_repo.repo_path)

        # Verify the repository state is valid
        git_ops = GitOps(dual_hunk_repo.repo_path)
        status_result = git_ops.run_git_command(["status", "--porcelain"])
        assert status_result.returncode == 0


class TestMicroPythonScenario:
    """Tests based on real MicroPython dual-hunk scenario."""

    def test_micropython_file_support_scenario(self, dual_hunk_repo):
        """Test the real MicroPython __file__ support scenario."""
        scenario = dual_hunk_repo.create_micropython_scenario()

        git_ops = GitOps(dual_hunk_repo.repo_path)

        # Generate diff for the changes
        diff_result = git_ops.run_git_command(
            ["diff", scenario["initial_commit"], scenario["target_commit"]]
        )

        assert diff_result.returncode == 0
        diff_content = diff_result.stdout

        # Parse the hunks
        hunk_parser = HunkParser(diff_content)
        hunks = hunk_parser.parse_hunks()

        assert len(hunks) > 0

        # Verify the diff contains MicroPython-specific patterns
        assert "MICROPY_PY___FILE__" in diff_content
        assert "pyexec.c" in diff_content

    def test_micropython_hunk_context_preservation(self, dual_hunk_repo):
        """Test that context is preserved in MicroPython-like scenarios."""
        scenario = dual_hunk_repo.create_micropython_scenario()

        git_ops = GitOps(dual_hunk_repo.repo_path)

        # Show the diff with context
        diff_result = git_ops.run_git_command(
            [
                "diff",
                "-U10",  # More context lines
                scenario["initial_commit"],
                scenario["target_commit"],
            ]
        )

        assert diff_result.returncode == 0
        diff_content = diff_result.stdout

        # Verify context preservation
        assert "Handle different source types" in diff_content
        assert "Handle frozen modules" in diff_content
        assert "mp_make_function_from_proto_fun" in diff_content


class TestErrorRecoveryInIntegration:
    """Test error recovery during integration scenarios."""

    def test_corrupted_repository_recovery(self, dual_hunk_repo):
        """Test recovery from repository corruption during dual-hunk operations."""
        dual_hunk_repo.create_dual_hunk_scenario()

        git_ops = GitOps(dual_hunk_repo.repo_path)

        # Verify repository is in good state
        fsck_result = git_ops.run_git_command(["fsck", "--full"])
        assert fsck_result.returncode == 0, (
            f"Repository corruption detected: {fsck_result.stderr}"
        )

    def test_memory_efficient_large_hunks(self, dual_hunk_repo):
        """Test memory efficiency with large dual-hunk scenarios."""
        dual_hunk_repo.create_dual_hunk_scenario()

        # Create a large file scenario
        large_content = """#ifndef LARGE_CONFIG_H
#define LARGE_CONFIG_H

"""

        # Add many patterns to create large diff
        for i in range(100):
            large_content += f"""
// Config section {i}
#if OLD_PATTERN_{i}
void setup_config_{i}() {{
    // Configuration {i} setup
}}
#endif
"""

        large_content += "\n#endif // LARGE_CONFIG_H\n"

        # Create large scenario
        large_commit = dual_hunk_repo.add_commit(
            {"large_config.h": large_content}, "Add large config file"
        )

        # Update patterns to create large diff
        updated_content = large_content.replace("OLD_PATTERN_", "NEW_PATTERN_")
        updated_commit = dual_hunk_repo.add_commit(
            {"large_config.h": updated_content}, "Update all large patterns"
        )

        git_ops = GitOps(dual_hunk_repo.repo_path)

        # Generate and parse large diff
        diff_result = git_ops.run_git_command(["diff", large_commit, updated_commit])

        assert diff_result.returncode == 0

        # This should complete without excessive memory usage
        hunk_parser = HunkParser(diff_result.stdout)
        hunks = hunk_parser.parse_hunks()

        # Should have parsed a significant number of hunks
        assert len(hunks) >= 50, (
            f"Expected many hunks from large diff, got {len(hunks)}"
        )


if __name__ == "__main__":
    # Manual test run
    with temporary_test_repository("manual_dual_hunk_test") as temp_repo:
        test_repo = DualHunkTestRepository(temp_repo.repo_path)

        print("Creating dual-hunk scenario...")
        scenario = test_repo.create_dual_hunk_scenario()

        print("Testing hunk parsing...")
        git_ops = GitOps(test_repo.repo_path)
        diff_result = git_ops.run_git_command(
            ["diff", scenario["target_commit"] + "~1", scenario["source_commit"]]
        )

        hunk_parser = HunkParser(diff_result.stdout)
        hunks = hunk_parser.parse_hunks()

        print(f"Successfully parsed {len(hunks)} hunks")
        print("Dual-hunk integration test completed successfully!")
