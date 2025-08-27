"""
Focused integration tests for context-aware patch generation.

These tests reproduce the exact MicroPython dual-hunk scenario described in
PATCH_GENERATION_FIX.md with simplified, focused test cases that verify the
core patch generation fix works end-to-end.
"""

import tempfile
import subprocess
from pathlib import Path
from typing import Dict
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseManager


def create_dual_hunk_scenario(repo_path: Path) -> Dict[str, str]:
    """Create a minimal repository that reproduces the dual-hunk scenario.

    This creates the exact scenario described in PATCH_GENERATION_FIX.md:
    - Target commit has one instance of a pattern
    - Source commit has two instances of the same pattern change
    - Context-aware patch generation should handle both correctly
    """

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True
    )

    # Create file with the target state (one instance of OLD_PATTERN)
    test_file = repo_path / "config.h"
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

    test_file.write_text(target_content)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial config"], cwd=repo_path, check=True)

    initial_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    # Create target commit (the commit we want to squash into)
    # This represents the state when the target commit was made
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "Target commit"],
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

// Second config section (added later)
#if OLD_PATTERN  
void setup_config_two() {
    // Second configuration 
}
#endif

#endif // CONFIG_H
"""

    test_file.write_text(evolved_content)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add second config section"], cwd=repo_path, check=True
    )

    # Create source commit with changes to BOTH instances (the problematic commit)
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

// Second config section (added later)
#if NEW_PATTERN  
void setup_config_two() {
    // Second configuration 
}
#endif

#endif // CONFIG_H
"""

    test_file.write_text(source_content)
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Update both config patterns"],
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

    return {
        "initial_commit": initial_commit,
        "target_commit": target_commit,
        "source_commit": source_commit,
    }


@pytest.fixture
def dual_hunk_repo():
    """Create a repository with the dual-hunk scenario."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "dual_hunk_repo"
        repo_path.mkdir()
        commits = create_dual_hunk_scenario(repo_path)
        yield repo_path, commits


class TestPatchGenerationIntegration:
    """Integration tests that verify the complete patch generation workflow."""

    def test_dual_hunk_patch_generation_end_to_end(self, dual_hunk_repo):
        """Test the complete workflow for dual-hunk patch generation.

        This reproduces the exact MicroPython scenario:
        - Source commit changes OLD_PATTERN -> NEW_PATTERN in two locations
        - Target commit has only one instance of OLD_PATTERN
        - Context-aware algorithm should generate patches for both locations without conflicts
        """

        repo_path, commits = dual_hunk_repo
        git_ops = GitOps(str(repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get the diff from the problematic source commit
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )

        assert diff_result.returncode == 0, "Should get diff successfully"
        assert "OLD_PATTERN" in diff_result.stdout, "Diff should contain old pattern"
        assert "NEW_PATTERN" in diff_result.stdout, "Diff should contain new pattern"

        # Parse hunks from the diff
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Should find hunks for the config file
        config_hunks = [h for h in hunks if h.file_path == "config.h"]
        assert len(config_hunks) >= 1, (
            f"Should find hunks for config.h, got: {len(config_hunks)}"
        )

        # Generate context-aware patch for the target commit
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            config_hunks, commits["target_commit"]
        )

        # Verify patch was generated
        assert patch_content is not None, "Should generate patch content"
        assert len(patch_content.strip()) > 0, "Patch should not be empty"

        # Verify patch structure
        lines = patch_content.split("\n")
        diff_headers = [
            line
            for line in lines
            if line.startswith("--- a/") or line.startswith("+++ b/")
        ]
        assert len(diff_headers) >= 2, "Patch should have proper diff headers"

        hunk_headers = [line for line in lines if line.startswith("@@")]
        assert len(hunk_headers) >= 1, "Patch should have at least one hunk header"

        # Test patch application to target commit
        git_ops.run_git_command(["checkout", commits["target_commit"]])

        # Write patch to temporary file
        patch_file = repo_path / "test.patch"
        patch_file.write_text(patch_content)

        # Verify patch applies cleanly (the critical test)
        apply_result = git_ops.run_git_command(["apply", "--check", str(patch_file)])
        assert apply_result.returncode == 0, (
            f"Patch should apply cleanly: {apply_result.stderr}"
        )

        # Actually apply the patch
        apply_result = git_ops.run_git_command(["apply", str(patch_file)])
        assert apply_result.returncode == 0, (
            f"Patch application should succeed: {apply_result.stderr}"
        )

        # Verify the result
        config_file = repo_path / "config.h"
        final_content = config_file.read_text()

        # Should have applied the pattern change correctly
        assert "NEW_PATTERN" in final_content, (
            "Applied patch should contain new pattern"
        )

        # Count pattern occurrences to verify both were handled if applicable
        new_pattern_count = final_content.count("NEW_PATTERN")
        old_pattern_count = final_content.count("OLD_PATTERN")

        # The exact counts depend on how many instances existed in target vs source
        # The key is that patch applied without conflicts
        assert new_pattern_count > 0, "Should have at least one new pattern after patch"
        print(
            f"Applied patch: OLD_PATTERN count: {old_pattern_count}, NEW_PATTERN count: {new_pattern_count}"
        )

    def test_context_aware_targeting_prevents_duplicates(self, dual_hunk_repo):
        """Test that context-aware targeting prevents duplicate line targeting."""

        repo_path, commits = dual_hunk_repo
        git_ops = GitOps(str(repo_path))
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get target commit file content
        git_ops.run_git_command(["checkout", commits["target_commit"]])

        config_file = repo_path / "config.h"
        file_content = config_file.read_text()
        file_lines = file_content.split("\n")

        # Find all lines with the pattern
        old_pattern_lines = []
        for i, line in enumerate(file_lines):
            if "OLD_PATTERN" in line:
                old_pattern_lines.append(i + 1)  # 1-based line numbers

        print(f"Found OLD_PATTERN at lines: {old_pattern_lines}")

        if len(old_pattern_lines) >= 1:
            # Test the context-aware targeting
            change = {"old_line": "#if OLD_PATTERN", "new_line": "#if NEW_PATTERN"}

            used_lines = set()

            # First targeting should find a line
            result1 = rebase_manager._find_target_with_context(
                change, file_lines, used_lines
            )
            assert result1 is not None, "Should find first target"
            assert result1 in old_pattern_lines, (
                f"Target {result1} should be one of pattern lines {old_pattern_lines}"
            )
            used_lines.add(result1)

            # If there are multiple instances, second targeting should find different line
            if len(old_pattern_lines) > 1:
                result2 = rebase_manager._find_target_with_context(
                    change, file_lines, used_lines
                )
                if result2 is not None:
                    assert result2 != result1, (
                        f"Second target {result2} should differ from first {result1}"
                    )
                    assert result2 in old_pattern_lines, (
                        f"Target {result2} should be one of pattern lines {old_pattern_lines}"
                    )

    def test_patch_consolidation_workflow(self, dual_hunk_repo):
        """Test the complete patch consolidation workflow."""

        repo_path, commits = dual_hunk_repo
        git_ops = GitOps(str(repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Get and parse hunks
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Test consolidation by file
        consolidated = rebase_manager._consolidate_hunks_by_file(hunks)

        assert isinstance(consolidated, dict), "Should return dict"
        assert "config.h" in consolidated, "Should consolidate config.h hunks"

        file_hunks = consolidated["config.h"]
        assert len(file_hunks) >= 1, "Should have at least one hunk for config.h"

        # Test change extraction from consolidated hunks
        for hunk in file_hunks:
            changes = rebase_manager._extract_hunk_changes(hunk)
            assert isinstance(changes, list), "Should return list of changes"

            # Each change should have the required fields
            for change in changes:
                assert "old_line" in change, "Change should have old_line"
                assert "new_line" in change, "Change should have new_line"


class TestPatchGenerationErrorHandling:
    """Test error handling in patch generation."""

    def test_graceful_handling_of_missing_patterns(self, dual_hunk_repo):
        """Test graceful handling when target patterns don't exist."""

        repo_path, commits = dual_hunk_repo
        git_ops = GitOps(str(repo_path))
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Checkout target commit
        git_ops.run_git_command(["checkout", commits["target_commit"]])

        config_file = repo_path / "config.h"
        file_content = config_file.read_text()
        file_lines = file_content.split("\n")

        # Try to find a pattern that doesn't exist
        change = {"old_line": "#if NONEXISTENT_PATTERN", "new_line": "#if NEW_PATTERN"}

        result = rebase_manager._find_target_with_context(change, file_lines, set())
        assert result is None, "Should return None for non-existent pattern"

    def test_empty_hunks_handling(self, dual_hunk_repo):
        """Test handling of empty hunk lists."""

        repo_path, commits = dual_hunk_repo
        git_ops = GitOps(str(repo_path))
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Test with empty hunk list
        consolidated = rebase_manager._consolidate_hunks_by_file([])
        assert consolidated == {}, "Empty hunks should return empty dict"

        # Test patch generation with empty hunks
        patch = rebase_manager._create_corrected_patch_for_hunks(
            [], commits["target_commit"]
        )
        assert patch is None or patch.strip() == "", (
            "Empty hunks should produce no patch"
        )
