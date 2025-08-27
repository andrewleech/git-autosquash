"""
Tests for the patch generation fix described in PATCH_GENERATION_FIX.md.

This module tests the context-aware patch generation that prevents duplicate
hunk conflicts when multiple hunks contain identical content changes.
"""

import tempfile
import subprocess
from pathlib import Path
from typing import Dict
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseManager


class PatchGenerationTestRepository:
    """Helper class to create test git repositories with specific commit structures."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)

    def create_micropython_scenario(self) -> Dict[str, str]:
        """Create a repository that reproduces the MicroPython patch generation issue."""

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

        # Create initial shared/runtime directory structure
        runtime_dir = self.repo_path / "shared" / "runtime"
        runtime_dir.mkdir(parents=True)

        # Create initial pyexec.c file (simulating early state)
        pyexec_content = """/*
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
}
"""

        pyexec_file = runtime_dir / "pyexec.c"
        pyexec_file.write_text(pyexec_content)

        # Commit initial state
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial MicroPython runtime"],
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
}
"""

        pyexec_file.write_text(target_pyexec_content)
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "shared/runtime/pyexec: Add __file__ support for frozen modules",
            ],
            cwd=self.repo_path,
            check=True,
        )
        target_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Add another commit in between
        pyexec_file.write_text(target_pyexec_content + "\n// Additional change\n")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "shared/runtime/pyexec: Fix UBSan error in pyexec_stdin()",
            ],
            cwd=self.repo_path,
            check=True,
        )
        intermediate_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Create source commit with the problematic changes (simulating 595096ae7b)
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
// Additional change
"""

        pyexec_file.write_text(source_pyexec_content)
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "update"], cwd=self.repo_path, check=True
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
            "intermediate_commit": intermediate_commit,
            "source_commit": source_commit,
        }


@pytest.fixture
def temp_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "test_repo"
        repo_path.mkdir()
        yield PatchGenerationTestRepository(repo_path)


class TestPatchGenerationFix:
    """Test cases for the context-aware patch generation fix."""

    def test_micropython_dual_hunk_scenario(self, temp_repo):
        """Test the exact MicroPython scenario described in PATCH_GENERATION_FIX.md."""

        # Create the repository structure
        commits = temp_repo.create_micropython_scenario()

        # Initialize components
        git_ops = temp_repo.git_ops
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get diff from source commit
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )
        assert diff_result.returncode == 0

        # Parse hunks from the diff
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Should find exactly 2 hunks in the same file
        file_hunks = [h for h in hunks if h.file_path == "shared/runtime/pyexec.c"]
        assert len(file_hunks) == 2, f"Expected 2 hunks, found {len(file_hunks)}"

        # Both hunks should contain the same change pattern
        for hunk in file_hunks:
            hunk_lines = [line for line in hunk.lines if line.strip()]

            # Should find the patterns we're changing
            has_old_pattern = any(
                "#if MICROPY_PY___FILE__" in line for line in hunk_lines
            )
            has_new_pattern = any(
                "#if MICROPY_MODULE___FILE__" in line for line in hunk_lines
            )

            assert has_old_pattern, f"Hunk should contain old pattern: {hunk_lines}"
            assert has_new_pattern, f"Hunk should contain new pattern: {hunk_lines}"

        # Test the context-aware patch generation
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            file_hunks, commits["target_commit"]
        )

        # Verify patch structure
        assert patch_content is not None, "Patch should be generated"

        # Patch should contain exactly 2 hunk headers (@@)
        hunk_headers = [
            line for line in patch_content.split("\n") if line.startswith("@@")
        ]
        assert len(hunk_headers) == 2, (
            f"Expected 2 hunk headers, found {len(hunk_headers)}: {hunk_headers}"
        )

        # Hunk headers should have different line ranges
        line_ranges = [header.split("@@")[1].strip() for header in hunk_headers]
        assert len(set(line_ranges)) == 2, (
            f"Hunk headers should have different ranges: {line_ranges}"
        )

        # Test that patch applies cleanly to target commit
        # First, checkout the target commit
        checkout_result = git_ops.run_git_command(
            ["checkout", commits["target_commit"]]
        )
        assert checkout_result.returncode == 0

        # Write patch to file and apply it
        patch_file = temp_repo.repo_path / "test.patch"
        patch_file.write_text(patch_content)

        apply_result = git_ops.run_git_command(["apply", "--check", str(patch_file)])
        assert apply_result.returncode == 0, (
            f"Patch should apply cleanly: {apply_result.stderr}"
        )

        # Actually apply the patch
        apply_result = git_ops.run_git_command(["apply", str(patch_file)])
        assert apply_result.returncode == 0, (
            f"Patch application failed: {apply_result.stderr}"
        )

        # Verify the changes were applied correctly
        pyexec_file = temp_repo.repo_path / "shared" / "runtime" / "pyexec.c"
        final_content = pyexec_file.read_text()

        # Should have both instances changed
        old_pattern_count = final_content.count("#if MICROPY_PY___FILE__")
        new_pattern_count = final_content.count("#if MICROPY_MODULE___FILE__")

        assert old_pattern_count == 0, (
            f"Should have no old patterns left: {old_pattern_count}"
        )
        assert new_pattern_count == 2, (
            f"Should have 2 new patterns: {new_pattern_count}"
        )

    def test_context_aware_line_tracking(self, temp_repo):
        """Test that used line tracking prevents duplicate targeting."""

        commits = temp_repo.create_micropython_scenario()

        git_ops = temp_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get the target commit file content
        checkout_result = git_ops.run_git_command(
            ["checkout", commits["target_commit"]]
        )
        assert checkout_result.returncode == 0

        pyexec_file = temp_repo.repo_path / "shared" / "runtime" / "pyexec.c"
        file_lines = pyexec_file.read_text().split("\n")

        # Create mock changes that would target the same line
        changes = [
            {
                "old_line": "            #if MICROPY_PY___FILE__",
                "new_line": "            #if MICROPY_MODULE___FILE__",
                "line_context": ["            ctx->constants = frozen->constants;"],
            },
            {
                "old_line": "            #if MICROPY_PY___FILE__",  # Same line content
                "new_line": "            #if MICROPY_MODULE___FILE__",
                "line_context": [
                    "        // source is a lexer, parse and compile the script"
                ],
            },
        ]

        used_lines = set()
        targets = []

        # Test the context-aware matching
        for change in changes:
            target = rebase_manager._find_target_with_context(
                change, file_lines, used_lines
            )
            if target:
                targets.append(target)
                used_lines.add(target)

        # Should find 2 different targets
        assert len(targets) == 2, f"Should find 2 different targets: {targets}"
        assert len(set(targets)) == 2, f"Targets should be different: {targets}"
        assert targets[0] != targets[1], (
            f"First target ({targets[0]}) should differ from second ({targets[1]})"
        )

    def test_multiple_candidate_selection(self, temp_repo):
        """Test selection logic when multiple candidates exist."""

        commits = temp_repo.create_micropython_scenario()

        git_ops = temp_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Checkout target commit
        git_ops.run_git_command(["checkout", commits["target_commit"]])

        pyexec_file = temp_repo.repo_path / "shared" / "runtime" / "pyexec.c"
        file_lines = pyexec_file.read_text().split("\n")

        # Find the line we're looking for
        target_line = "            #if MICROPY_PY___FILE__"
        candidates = []
        for i, line in enumerate(file_lines):
            if line.rstrip("\n").strip() == target_line.strip():
                candidates.append(i + 1)

        assert len(candidates) >= 1, f"Should find at least 1 candidate: {candidates}"

        # Test with empty used_lines - should select first candidate
        used_lines = set()
        change = {
            "old_line": target_line,
            "new_line": "            #if MICROPY_MODULE___FILE__",
        }
        result = rebase_manager._find_target_with_context(
            change, file_lines, used_lines
        )

        assert result == candidates[0], (
            f"Should select first candidate {candidates[0]}, got {result}"
        )

        # Test with first candidate used - should select second if available
        if len(candidates) > 1:
            used_lines.add(candidates[0])
            result = rebase_manager._find_target_with_context(
                change, file_lines, used_lines
            )
            assert result == candidates[1], (
                f"Should select second candidate {candidates[1]}, got {result}"
            )

    def test_patch_consolidation_by_file(self, temp_repo):
        """Test that hunks are properly consolidated by file."""

        commits = temp_repo.create_micropython_scenario()

        git_ops = temp_repo.git_ops
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get hunks from source commit
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Test consolidation
        consolidated = rebase_manager._consolidate_hunks_by_file(hunks)

        assert "shared/runtime/pyexec.c" in consolidated, (
            "Should have pyexec.c in consolidated hunks"
        )
        file_hunks = consolidated["shared/runtime/pyexec.c"]
        assert len(file_hunks) == 2, (
            f"Should have 2 hunks for pyexec.c: {len(file_hunks)}"
        )

    def test_change_extraction_from_hunks(self, temp_repo):
        """Test extraction of individual changes from hunks."""

        commits = temp_repo.create_micropython_scenario()

        git_ops = temp_repo.git_ops
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get hunks
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        file_hunks = [h for h in hunks if h.file_path == "shared/runtime/pyexec.c"]
        assert len(file_hunks) >= 1

        # Extract changes from first hunk
        changes = rebase_manager._extract_hunk_changes(file_hunks[0])

        assert len(changes) >= 1, f"Should extract at least 1 change: {changes}"

        # Each change should have required fields
        for change in changes:
            assert "old_line" in change, f"Change should have old_line: {change}"
            assert "new_line" in change, f"Change should have new_line: {change}"
            assert change["old_line"] != change["new_line"], (
                f"Old and new lines should differ: {change}"
            )


class TestPatchGenerationEdgeCases:
    """Test edge cases and error conditions."""

    def test_no_matching_lines(self, temp_repo):
        """Test behavior when no matching lines are found."""

        commits = temp_repo.create_micropython_scenario()

        git_ops = temp_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        git_ops.run_git_command(["checkout", commits["target_commit"]])

        pyexec_file = temp_repo.repo_path / "shared" / "runtime" / "pyexec.c"
        file_lines = pyexec_file.read_text().split("\n")

        # Try to find a line that doesn't exist
        change = {
            "old_line": "    // This line does not exist in the file",
            "new_line": "    // This is the replacement",
        }

        result = rebase_manager._find_target_with_context(change, file_lines, set())
        assert result is None, "Should return None for non-existent lines"

    def test_all_candidates_used(self, temp_repo):
        """Test behavior when all matching lines are already used."""

        commits = temp_repo.create_micropython_scenario()

        git_ops = temp_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        git_ops.run_git_command(["checkout", commits["target_commit"]])

        pyexec_file = temp_repo.repo_path / "shared" / "runtime" / "pyexec.c"
        file_lines = pyexec_file.read_text().split("\n")

        # Find all candidates for a specific line
        target_line = "            #if MICROPY_PY___FILE__"
        candidates = set()
        for i, line in enumerate(file_lines):
            if line.rstrip("\n").strip() == target_line.strip():
                candidates.add(i + 1)

        # Mark all candidates as used
        change = {
            "old_line": target_line,
            "new_line": "            #if MICROPY_MODULE___FILE__",
        }
        result = rebase_manager._find_target_with_context(
            change, file_lines, candidates
        )

        assert result is None, "Should return None when all candidates are used"

    def test_empty_file_lines(self, temp_repo):
        """Test behavior with empty file."""

        commits = temp_repo.create_micropython_scenario()

        git_ops = temp_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Test with empty file
        change = {"old_line": "any line", "new_line": "replacement"}
        result = rebase_manager._find_target_with_context(change, [], set())

        assert result is None, "Should return None for empty file"
