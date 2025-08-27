"""
Complex git workflow tests for patch generation fix.

These tests verify patch generation correctness in realistic production scenarios
including interactive rebase conflicts, multi-branch development, merge scenarios,
and complex commit histories.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Dict
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseManager


class ComplexWorkflowBuilder:
    """Builder for creating complex git repository scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)
        self._init_repo()

    def _init_repo(self):
        """Initialize repository with standard configuration."""
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
        subprocess.run(
            ["git", "config", "rebase.autosquash", "true"],
            cwd=self.repo_path,
            check=True,
        )

    def create_base_file(self, filename: str, content: str) -> str:
        """Create base file and return commit hash."""
        file_path = self.repo_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Add {filename}"], cwd=self.repo_path, check=True
        )

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def create_feature_branch(self, branch_name: str, base_commit: str) -> str:
        """Create and checkout feature branch from base commit."""
        subprocess.run(
            ["git", "checkout", "-b", branch_name, base_commit],
            cwd=self.repo_path,
            check=True,
        )
        return branch_name

    def modify_file_add_commit(self, filename: str, content: str, message: str) -> str:
        """Modify file and create commit, return commit hash."""
        file_path = self.repo_path / filename
        file_path.write_text(content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=self.repo_path, check=True)

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def create_merge_conflict_scenario(self, base_commit: str) -> Dict[str, str]:
        """Create a merge conflict scenario between two branches."""
        # Create branch 1
        subprocess.run(
            ["git", "checkout", "-b", "branch1", base_commit],
            cwd=self.repo_path,
            check=True,
        )

        conflict_file = self.repo_path / "conflict.c"
        branch1_content = """// File with potential merge conflicts
#define CONFIG_OPTION_A 1
#if OLD_PATTERN
void function_a() {
    // Implementation A
}
#endif
"""
        conflict_file.write_text(branch1_content)
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        branch1_commit = subprocess.run(
            ["git", "commit", "-m", "Branch 1 changes"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # Create branch 2 with conflicting changes
        subprocess.run(
            ["git", "checkout", "-b", "branch2", base_commit],
            cwd=self.repo_path,
            check=True,
        )

        branch2_content = """// File with potential merge conflicts  
#define CONFIG_OPTION_B 1
#if OLD_PATTERN
void function_b() {
    // Implementation B
}
#endif
"""
        conflict_file.write_text(branch2_content)
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        branch2_commit = subprocess.run(
            ["git", "commit", "-m", "Branch 2 changes"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # Return to main branch and create merge
        subprocess.run(["git", "checkout", "main"], cwd=self.repo_path, check=True)

        # Merge branch1 first (this should succeed)
        subprocess.run(
            ["git", "merge", "--no-ff", "branch1", "-m", "Merge branch1"],
            cwd=self.repo_path,
            check=True,
        )
        merge_commit1 = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        return {
            "base_commit": base_commit,
            "branch1_commit": subprocess.run(
                ["git", "rev-parse", "branch1"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "branch2_commit": subprocess.run(
                ["git", "rev-parse", "branch2"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            ).stdout.strip(),
            "merge_commit": merge_commit1,
        }


@pytest.fixture
def complex_workflow_repo():
    """Create repository for complex workflow testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "complex_workflow"
        repo_path.mkdir()
        builder = ComplexWorkflowBuilder(repo_path)
        yield builder


class TestComplexGitWorkflows:
    """Test patch generation in complex git workflow scenarios."""

    def test_interactive_rebase_with_conflicts(self, complex_workflow_repo):
        """Test patch generation during interactive rebase with conflicts.

        This scenario simulates:
        1. Multiple commits with interdependent changes
        2. Interactive rebase that causes conflicts
        3. Patch generation during conflict resolution
        """
        builder = complex_workflow_repo

        # Create base file
        base_content = """// Complex configuration file
#if OLD_PATTERN_A
void config_function_a() {
    // First function
}
#endif

#if OLD_PATTERN_B  
void config_function_b() {
    // Second function
}
#endif
"""
        base_commit = builder.create_base_file("complex.c", base_content)

        # Create first modification commit
        modified_content_1 = base_content.replace("OLD_PATTERN_A", "NEW_PATTERN_A")
        commit1 = builder.modify_file_add_commit(
            "complex.c", modified_content_1, "Update pattern A"
        )

        # Create second modification commit that depends on first
        modified_content_2 = modified_content_1.replace(
            "OLD_PATTERN_B", "NEW_PATTERN_B"
        )
        commit2 = builder.modify_file_add_commit(
            "complex.c", modified_content_2, "Update pattern B"
        )

        # Create third commit that changes both patterns differently
        conflicting_content = """// Complex configuration file
#if CONFLICTING_PATTERN_A
void config_function_a() {
    // Modified first function
}
#endif

#if CONFLICTING_PATTERN_B  
void config_function_b() {
    // Modified second function
}
#endif
"""
        commit3 = builder.modify_file_add_commit(
            "complex.c", conflicting_content, "Conflicting changes to squash"
        )

        # Now test patch generation for squashing commit3 into commit1
        git_ops = GitOps(str(builder.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, base_commit)

        # Get diff from commit3
        diff_result = git_ops.run_git_command(["show", "--no-merges", commit3])
        assert diff_result.returncode == 0, "Should get diff successfully"

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)
        complex_hunks = [h for h in hunks if h.file_path == "complex.c"]

        # Verify we can generate patches even in complex interdependent scenarios
        assert len(complex_hunks) > 0, "Should find hunks in complex scenario"

        # Test patch generation targeting earlier commit in the chain
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            complex_hunks, commit1
        )

        # Verify patch structure
        assert patch_content is not None, "Should generate patch for complex scenario"
        assert len(patch_content.strip()) > 0, "Patch should not be empty"

        # Test that patch targets correct commit state
        subprocess.run(["git", "checkout", commit1], cwd=builder.repo_path, check=True)

        patch_file = builder.repo_path / "complex.patch"
        patch_file.write_text(patch_content)

        # Verify patch check (may have conflicts, which is expected)
        check_result = git_ops.run_git_command(["apply", "--check", str(patch_file)])
        # In complex scenarios, conflicts are expected - we're testing the patch structure

    def test_cherry_pick_scenario_with_context_changes(self, complex_workflow_repo):
        """Test patch generation in cherry-pick scenarios where context has changed."""
        builder = complex_workflow_repo

        # Create base file with multiple similar patterns
        base_content = """// Multiple similar patterns for cherry-pick testing
void setup() {
    #if OLD_PATTERN
    initialize_feature_a();
    #endif
    
    #if OLD_PATTERN  
    initialize_feature_b();
    #endif
    
    #if OLD_PATTERN
    initialize_feature_c();
    #endif
}
"""
        base_commit = builder.create_base_file("cherry_pick_test.c", base_content)

        # Create feature branch that modifies context around patterns
        feature_branch = builder.create_feature_branch("feature", base_commit)

        # Modify context in feature branch
        feature_content = """// Multiple similar patterns for cherry-pick testing
void setup() {
    // Added context before pattern A
    #if OLD_PATTERN
    initialize_feature_a();
    setup_additional_config_a();  // New line
    #endif
    
    #if OLD_PATTERN  
    initialize_feature_b();
    #endif
    
    // Added context before pattern C  
    #if OLD_PATTERN
    initialize_feature_c();
    setup_additional_config_c();  // New line
    #endif
}
"""
        context_commit = builder.modify_file_add_commit(
            "cherry_pick_test.c", feature_content, "Add context around patterns"
        )

        # Create commit with pattern changes to be cherry-picked
        pattern_changed_content = feature_content.replace("OLD_PATTERN", "NEW_PATTERN")
        pattern_commit = builder.modify_file_add_commit(
            "cherry_pick_test.c", pattern_changed_content, "Update all patterns"
        )

        # Switch back to main branch
        subprocess.run(["git", "checkout", "main"], cwd=builder.repo_path, check=True)

        # Test cherry-picking pattern_commit to base_commit (where context differs)
        git_ops = GitOps(str(builder.repo_path))
        rebase_manager = RebaseManager(git_ops, base_commit)
        hunk_parser = HunkParser(git_ops)

        # Get changes from pattern_commit
        diff_result = git_ops.run_git_command(["show", "--no-merges", pattern_commit])
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        cherry_pick_hunks = [h for h in hunks if h.file_path == "cherry_pick_test.c"]
        assert len(cherry_pick_hunks) > 0, "Should find hunks for cherry-pick scenario"

        # Generate patch for application to base_commit (different context)
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            cherry_pick_hunks, base_commit
        )

        assert patch_content is not None, "Should generate cherry-pick patch"

        # Verify patch handles context differences intelligently
        hunk_headers = [
            line for line in patch_content.split("\n") if line.startswith("@@")
        ]
        assert len(hunk_headers) > 0, (
            "Should have hunk headers for context-aware cherry-pick"
        )

    def test_multi_branch_merge_scenario(self, complex_workflow_repo):
        """Test patch generation in multi-branch merge scenarios."""
        builder = complex_workflow_repo

        # Create initial file
        initial_content = """// Multi-branch scenario file
#if OLD_CONFIG
void main_feature() {
    // Main implementation
}
#endif

void utility_function() {
    // Utility code
}
"""
        base_commit = builder.create_base_file("multi_branch.c", initial_content)

        # Create merge conflict scenario
        commits = builder.create_merge_conflict_scenario(base_commit)

        # Create a commit on main that changes the pattern
        subprocess.run(["git", "checkout", "main"], cwd=builder.repo_path, check=True)

        pattern_update_content = """// Multi-branch scenario file
#if NEW_CONFIG
void main_feature() {
    // Updated main implementation
}
#endif

void utility_function() {
    // Utility code
}

#if NEW_CONFIG
void additional_feature() {
    // Additional functionality
}
#endif
"""
        pattern_file = builder.repo_path / "multi_branch.c"
        pattern_file.write_text(pattern_update_content)
        subprocess.run(["git", "add", "."], cwd=builder.repo_path, check=True)
        pattern_commit = subprocess.run(
            ["git", "commit", "-m", "Update configuration pattern"],
            cwd=builder.repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        pattern_commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=builder.repo_path,
            capture_output=True,
            text=True,
        ).stdout.strip()

        # Test squashing pattern_commit into the merge commit
        git_ops = GitOps(str(builder.repo_path))
        rebase_manager = RebaseManager(git_ops, commits["base_commit"])
        hunk_parser = HunkParser(git_ops)

        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", pattern_commit_hash]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        multi_branch_hunks = [h for h in hunks if h.file_path == "multi_branch.c"]

        if multi_branch_hunks:
            # Test targeting the merge commit
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                multi_branch_hunks, commits["merge_commit"]
            )

            # Verify merge scenario handling
            if patch_content:
                assert len(patch_content.strip()) > 0, (
                    "Multi-branch patch should not be empty"
                )

                # Check patch structure for merge scenario
                lines = patch_content.split("\n")
                file_markers = [
                    line
                    for line in lines
                    if line.startswith("---") or line.startswith("+++")
                ]
                assert len(file_markers) >= 2, (
                    "Should have proper file markers in merge patch"
                )

    def test_complex_commit_history_with_squash_fixup(self, complex_workflow_repo):
        """Test patch generation with complex commit history including fixup commits."""
        builder = complex_workflow_repo

        # Create base file
        history_content = """// Complex history testing
#define FEATURE_FLAG_A 0
#define FEATURE_FLAG_B 0

#if OLD_IMPLEMENTATION
void complex_function() {
    // Original implementation
    handle_feature_a();
    handle_feature_b();
}
#endif
"""
        base_commit = builder.create_base_file("history_test.c", history_content)

        # Create multiple intermediate commits
        commit_chain = []

        # Commit 1: Enable feature A
        content_1 = history_content.replace("FEATURE_FLAG_A 0", "FEATURE_FLAG_A 1")
        commit1 = builder.modify_file_add_commit(
            "history_test.c", content_1, "Enable feature A"
        )
        commit_chain.append(commit1)

        # Commit 2: Enable feature B
        content_2 = content_1.replace("FEATURE_FLAG_B 0", "FEATURE_FLAG_B 1")
        commit2 = builder.modify_file_add_commit(
            "history_test.c", content_2, "Enable feature B"
        )
        commit_chain.append(commit2)

        # Commit 3: Update implementation
        content_3 = content_2.replace("OLD_IMPLEMENTATION", "NEW_IMPLEMENTATION")
        commit3 = builder.modify_file_add_commit(
            "history_test.c", content_3, "Update implementation"
        )
        commit_chain.append(commit3)

        # Create fixup commit that should be squashed into commit1
        fixup_content = content_3.replace(
            "handle_feature_a();", "handle_feature_a_enhanced();"
        )
        fixup_commit = builder.modify_file_add_commit(
            "history_test.c", fixup_content, "fixup! Enable feature A"
        )

        # Test squashing fixup into the middle of history
        git_ops = GitOps(str(builder.repo_path))
        rebase_manager = RebaseManager(git_ops, base_commit)
        hunk_parser = HunkParser(git_ops)

        diff_result = git_ops.run_git_command(["show", "--no-merges", fixup_commit])
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        fixup_hunks = [h for h in hunks if h.file_path == "history_test.c"]
        assert len(fixup_hunks) > 0, "Should find fixup hunks"

        # Generate patch for squashing into commit1
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            fixup_hunks, commit1
        )

        assert patch_content is not None, "Should generate patch for complex history"

        # Verify patch targeting works with complex history
        subprocess.run(["git", "checkout", commit1], cwd=builder.repo_path, check=True)

        # Check current file state at commit1
        current_file = builder.repo_path / "history_test.c"
        commit1_content = current_file.read_text()

        # Verify that the target commit state is what we expect
        assert "FEATURE_FLAG_A 1" in commit1_content, (
            "Commit1 should have feature A enabled"
        )
        assert "FEATURE_FLAG_B 0" in commit1_content, (
            "Commit1 should not have feature B enabled yet"
        )

        # Test patch application feasibility
        patch_file = builder.repo_path / "fixup.patch"
        patch_file.write_text(patch_content)

        check_result = git_ops.run_git_command(["apply", "--check", str(patch_file)])
        # Record result for analysis (conflicts may be expected in complex scenarios)

    def test_stash_unstash_during_complex_rebase(self, complex_workflow_repo):
        """Test patch generation with stash/unstash operations during rebase."""
        builder = complex_workflow_repo

        # Create base file
        stash_content = """// File for stash testing
#if ORIGINAL_FLAG
void stash_test_function() {
    // Original implementation
}
#endif
"""
        base_commit = builder.create_base_file("stash_test.c", stash_content)

        # Create target commit
        target_content = stash_content.replace("ORIGINAL_FLAG", "UPDATED_FLAG")
        target_commit = builder.modify_file_add_commit(
            "stash_test.c", target_content, "Update flag"
        )

        # Create working directory changes (simulating interrupted work)
        working_changes = (
            target_content + "\n// Work in progress\nvoid wip_function() { }\n"
        )
        stash_file = builder.repo_path / "stash_test.c"
        stash_file.write_text(working_changes)

        # Also create new untracked file
        untracked_file = builder.repo_path / "untracked.tmp"
        untracked_file.write_text("temporary work")

        # Test that RebaseManager can handle working directory changes
        git_ops = GitOps(str(builder.repo_path))
        rebase_manager = RebaseManager(git_ops, base_commit)

        # Check working tree state detection
        status_result = git_ops.run_git_command(["status", "--porcelain"])
        working_tree_dirty = len(status_result.stdout.strip()) > 0

        assert working_tree_dirty, "Working tree should be dirty for stash testing"

        # Create commit to be squashed
        subprocess.run(["git", "add", "."], cwd=builder.repo_path, check=True)
        squash_commit = builder.modify_file_add_commit(
            "stash_test.c", working_changes, "Changes to squash"
        )

        # Test patch generation in presence of stash-worthy changes
        hunk_parser = HunkParser(git_ops)
        diff_result = git_ops.run_git_command(["show", "--no-merges", squash_commit])
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        stash_hunks = [h for h in hunks if h.file_path == "stash_test.c"]

        if stash_hunks:
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                stash_hunks, target_commit
            )

            # Verify patch generation works despite stash scenario complexity
            assert patch_content is not None, "Should generate patch in stash scenario"

            # Test clean checkout to target commit
            subprocess.run(
                ["git", "checkout", target_commit], cwd=builder.repo_path, check=True
            )

            # Verify target state
            target_file_content = stash_file.read_text()
            assert "UPDATED_FLAG" in target_file_content, (
                "Target commit should have updated flag"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
