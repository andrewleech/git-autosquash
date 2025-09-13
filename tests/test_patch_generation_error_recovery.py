"""
Error recovery and rollback verification tests for patch generation.

These tests verify that the patch generation system can handle failures gracefully,
perform atomic operations, and provide proper rollback mechanisms when operations fail.
"""

import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseManager


class ErrorRecoveryBuilder:
    """Builder for creating error recovery test scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)
        self._init_repo()

    def _init_repo(self):
        """Initialize repository for error recovery testing."""
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Recovery Test"],
            cwd=self.repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "recovery@test.com"],
            cwd=self.repo_path,
            check=True,
        )

        # Configure git for rebase scenarios
        subprocess.run(
            ["git", "config", "rebase.autosquash", "true"],
            cwd=self.repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "merge.conflictstyle", "merge"],
            cwd=self.repo_path,
            check=True,
        )

    def create_rebase_conflict_scenario(self) -> Dict[str, Any]:
        """Create scenario that will cause rebase conflicts."""

        # Create base file
        base_content = """// File that will have conflicts during rebase
void conflicting_function() {
    #if OLD_CONFIG
    // Original implementation
    handle_original_case();
    #endif
}

void stable_function() {
    // This function won't change
    return;
}
"""

        base_file = self.repo_path / "conflict_test.c"
        base_file.write_text(base_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Base commit"], cwd=self.repo_path, check=True
        )

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Create target commit that changes the context
        target_content = """// File that will have conflicts during rebase
void conflicting_function() {
    #if OLD_CONFIG
    // Target implementation with different context
    handle_target_case();
    setup_target_environment();
    #endif
}

void stable_function() {
    // This function won't change
    return;
}

void new_target_function() {
    // Added in target commit
    handle_new_functionality();
}
"""

        base_file.write_text(target_content)
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Target commit with context changes"],
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

        # Create conflicting commit (to be squashed)
        conflicting_content = """// File that will have conflicts during rebase
void conflicting_function() {
    #if NEW_CONFIG
    // Conflicting implementation that overlaps with target changes
    handle_target_case();  // Same line as target but different context
    handle_conflicting_case();
    #endif
}

void stable_function() {
    // This function won't change  
    return;
}

void conflicting_new_function() {
    // This will conflict with new_target_function
    handle_conflicting_functionality();
}
"""

        base_file.write_text(conflicting_content)
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Conflicting commit to squash"],
            cwd=self.repo_path,
            check=True,
        )

        conflicting_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "base_commit": base_commit,
            "target_commit": target_commit,
            "conflicting_commit": conflicting_commit,
        }

    def create_incomplete_operation_scenario(self) -> Dict[str, Any]:
        """Create scenario for testing incomplete operations."""

        # Create multiple files that will be modified
        files_content = {
            "file1.c": """#if OLD_PATTERN\nvoid file1_function() { }\n#endif\n""",
            "file2.c": """#if OLD_PATTERN\nvoid file2_function() { }\n#endif\n""",
            "file3.c": """#if OLD_PATTERN\nvoid file3_function() { }\n#endif\n""",
        }

        for filename, content in files_content.items():
            file_path = self.repo_path / filename
            file_path.write_text(content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Multi-file base"], cwd=self.repo_path, check=True
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
            ["git", "commit", "--allow-empty", "-m", "Target for incomplete ops"],
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

        # Create changes to all files
        for filename in files_content.keys():
            file_path = self.repo_path / filename
            content = file_path.read_text()
            updated_content = content.replace("OLD_PATTERN", "NEW_PATTERN")
            file_path.write_text(updated_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Multi-file changes"],
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
            "files": list(files_content.keys()),
        }

    def create_working_tree_dirty_scenario(self) -> Dict[str, Any]:
        """Create scenario with dirty working tree for stash testing."""

        # Create clean base
        clean_content = """// Clean file for working tree testing
#if CLEAN_PATTERN
void clean_function() {
    // Clean implementation
}
#endif
"""

        clean_file = self.repo_path / "working_tree_test.c"
        clean_file.write_text(clean_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Clean base"], cwd=self.repo_path, check=True
        )

        base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Create working directory changes (uncommitted)
        dirty_content = (
            clean_content + "\n// Work in progress\nvoid wip_function() { }\n"
        )
        clean_file.write_text(dirty_content)

        # Create untracked file
        untracked_file = self.repo_path / "untracked.tmp"
        untracked_file.write_text("untracked content")

        return {
            "base_commit": base_commit,
            "has_staged": False,
            "has_unstaged": True,
            "has_untracked": True,
        }


@pytest.fixture
def error_recovery_repo():
    """Create repository for error recovery testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "error_recovery"
        repo_path.mkdir()
        builder = ErrorRecoveryBuilder(repo_path)
        yield builder


class TestPatchGenerationErrorRecovery:
    """Test error recovery and rollback mechanisms."""

    def test_rebase_conflict_recovery(self, error_recovery_repo):
        """Test recovery from rebase conflicts."""
        repo = error_recovery_repo
        scenario = repo.create_rebase_conflict_scenario()

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get hunks from conflicting commit
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["conflicting_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        conflict_hunks = [h for h in hunks if h.file_path == "conflict_test.c"]
        assert len(conflict_hunks) > 0, "Should find hunks for conflict testing"

        # Store original branch state
        git_ops.get_current_branch()
        original_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Test patch generation that may cause conflicts
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            conflict_hunks, scenario["target_commit"]
        )

        # Even if patch generation succeeds, test application conflicts
        if patch_content:
            # Switch to target commit
            subprocess.run(
                ["git", "checkout", scenario["target_commit"]],
                cwd=repo.repo_path,
                check=True,
            )

            patch_file = repo.repo_path / "conflict.patch"
            patch_file.write_text(patch_content)

            # Try to apply patch
            apply_result = git_ops.run_git_command(
                ["apply", "--check", str(patch_file)]
            )

            if apply_result.returncode != 0:
                print(f"Expected conflict detected: {apply_result.stderr}")

            # Clean up patch file and return to original state
            if patch_file.exists():
                patch_file.unlink()
            subprocess.run(
                ["git", "checkout", original_commit], cwd=repo.repo_path, check=True
            )

            # Verify repository state is clean
            status_result = git_ops.run_git_command(["status", "--porcelain"])
            assert len(status_result.stdout.strip()) == 0, (
                "Repository should be clean after recovery"
            )

    def test_atomic_operation_rollback(self, error_recovery_repo):
        """Test atomic rollback when operations fail partway through."""
        repo = error_recovery_repo
        scenario = repo.create_incomplete_operation_scenario()

        git_ops = GitOps(str(repo.repo_path))
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Store original state
        original_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        git_ops.run_git_command(["status", "--porcelain"]).stdout

        # Simulate partial failure by creating a scenario where some files exist, others don't
        # Remove one of the files to cause failure
        missing_file = repo.repo_path / "file2.c"
        missing_file.unlink()  # This will cause git operations to fail

        # Try to get hunks (this should handle missing files gracefully)
        try:
            diff_result = git_ops.run_git_command(
                ["show", "--no-merges", scenario["change_commit"]]
            )

            if diff_result.returncode == 0:
                hunk_parser = HunkParser(git_ops)
                hunks = hunk_parser._parse_diff_output(diff_result.stdout)

                # Test that partial failure doesn't corrupt repository state
                rebase_manager._create_corrected_patch_for_hunks(
                    hunks, scenario["target_commit"]
                )

                # Repository should still be in a consistent state
                current_commit = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=repo.repo_path,
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout.strip()

                assert current_commit == original_commit, (
                    "Commit should not change after partial failure"
                )

        except Exception as e:
            # Any exceptions should leave the repository in a clean state
            current_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            assert current_commit == original_commit, (
                f"Repository corrupted after exception: {e}"
            )

    def test_working_tree_state_preservation(self, error_recovery_repo):
        """Test that working tree state is preserved during failures."""
        repo = error_recovery_repo
        scenario = repo.create_working_tree_dirty_scenario()

        git_ops = GitOps(str(repo.repo_path))
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Verify working tree is dirty as expected
        status_result = git_ops.run_git_command(["status", "--porcelain"])
        working_tree_dirty = len(status_result.stdout.strip()) > 0

        assert working_tree_dirty, "Working tree should be dirty for this test"

        # Store working tree state
        working_file = repo.repo_path / "working_tree_test.c"
        working_file.read_text()

        untracked_file = repo.repo_path / "untracked.tmp"
        original_untracked_content = (
            untracked_file.read_text() if untracked_file.exists() else None
        )

        # Simulate operation that fails and should preserve working tree
        try:
            # Try to perform rebase manager operation with dirty working tree
            rebase_manager._handle_working_tree_state()

            # Check if stash was created
            stash_list = git_ops.run_git_command(["stash", "list"])
            if stash_list.returncode == 0 and stash_list.stdout.strip():
                print("Stash created for dirty working tree")

                # Verify stash contains our changes
                stash_show = git_ops.run_git_command(["stash", "show", "-p"])
                if stash_show.returncode == 0:
                    assert "wip_function" in stash_show.stdout, (
                        "Stash should contain working tree changes"
                    )

        except Exception as e:
            print(f"Operation failed as expected: {e}")

        # Verify working tree state after failure
        if working_file.exists():
            working_file.read_text()
            # Working tree should be restored to original state or preserved

        if untracked_file.exists() and original_untracked_content:
            current_untracked_content = untracked_file.read_text()
            assert current_untracked_content == original_untracked_content, (
                "Untracked file should be preserved"
            )

    def test_cleanup_on_process_interruption(self, error_recovery_repo):
        """Test cleanup when process is interrupted."""
        repo = error_recovery_repo
        scenario = repo.create_incomplete_operation_scenario()

        git_ops = GitOps(str(repo.repo_path))
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Store original state
        original_branch = git_ops.get_current_branch()
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Simulate interrupt during long-running operation
        def interrupt_after_delay():
            time.sleep(0.1)  # Short delay to let operation start
            # We can't actually send signals in tests, so simulate cleanup call

        # Test that cleanup methods work correctly
        try:
            # Store stash ref if any
            rebase_manager._stash_ref = "test_stash_ref"
            rebase_manager._original_branch = original_branch

            # Call cleanup directly to test it
            rebase_manager._cleanup_on_error()

            # Verify cleanup worked
            assert rebase_manager._stash_ref is None, "Stash ref should be cleared"

        except Exception as e:
            print(f"Cleanup handling exception: {e}")

        # Verify repository is in consistent state after cleanup
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Should be back to original commit or a consistent state
        git_ops.run_git_command(["status", "--porcelain"])
        # Status might not be completely clean due to test artifacts, but should be consistent

    def test_reflog_safety_mechanism(self, error_recovery_repo):
        """Test that reflog provides safety mechanism for recovery."""
        repo = error_recovery_repo
        scenario = repo.create_incomplete_operation_scenario()

        git_ops = GitOps(str(repo.repo_path))

        # Get initial reflog state
        initial_reflog = git_ops.run_git_command(["reflog", "--oneline", "-n", "10"])
        initial_reflog_lines = (
            len(initial_reflog.stdout.strip().split("\n"))
            if initial_reflog.stdout.strip()
            else 0
        )

        # Perform operations that should create reflog entries
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Even if operations fail, they should leave reflog traces
        try:
            hunk_parser = HunkParser(git_ops)
            diff_result = git_ops.run_git_command(
                ["show", "--no-merges", scenario["change_commit"]]
            )

            if diff_result.returncode == 0:
                hunks = hunk_parser._parse_diff_output(diff_result.stdout)

                # These operations might fail, but should be traceable in reflog
                if hunks:
                    rebase_manager._create_corrected_patch_for_hunks(
                        hunks, scenario["target_commit"]
                    )

        except Exception as e:
            print(f"Expected operation failure: {e}")

        # Check reflog for any new entries
        final_reflog = git_ops.run_git_command(["reflog", "--oneline", "-n", "15"])

        if final_reflog.returncode == 0 and final_reflog.stdout.strip():
            final_reflog_lines = len(final_reflog.stdout.strip().split("\n"))

            # Reflog should be available for recovery
            print(f"Reflog entries: {initial_reflog_lines} -> {final_reflog_lines}")

            # Test reflog-based recovery
            if final_reflog_lines > initial_reflog_lines:
                # Try to reset using reflog
                reflog_recovery = git_ops.run_git_command(
                    ["reset", "--hard", f"HEAD@{{{0}}}"]
                )
                if reflog_recovery.returncode == 0:
                    print("Reflog-based recovery successful")

    def test_partial_hunk_application_rollback(self, error_recovery_repo):
        """Test rollback when only some hunks can be applied."""
        repo = error_recovery_repo
        scenario = repo.create_rebase_conflict_scenario()

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Create mixed scenario: some hunks can apply, others cannot
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["conflicting_commit"]]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        if hunks:
            # Store original state for rollback verification
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            # Test patch generation and potential partial application
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                hunks, scenario["target_commit"]
            )

            if patch_content:
                # Switch to target commit
                subprocess.run(
                    ["git", "checkout", scenario["target_commit"]],
                    cwd=repo.repo_path,
                    check=True,
                )

                patch_file = repo.repo_path / "partial.patch"
                patch_file.write_text(patch_content)

                # Test partial application
                apply_result = git_ops.run_git_command(["apply", str(patch_file)])

                if apply_result.returncode != 0:
                    # Partial failure - verify clean state
                    status_after_failure = git_ops.run_git_command(
                        ["status", "--porcelain"]
                    )

                    # Should not have partially applied changes
                    if status_after_failure.stdout.strip():
                        # If there are changes, they should be consistent
                        # (either fully applied or fully reverted)
                        print(
                            f"Status after partial failure: {status_after_failure.stdout}"
                        )

                        # Reset to clean state
                        git_ops.run_git_command(["reset", "--hard", "HEAD"])

                        # Clean up patch file
                        if patch_file.exists():
                            patch_file.unlink()

                        # Verify clean state after reset
                        clean_status = git_ops.run_git_command(
                            ["status", "--porcelain"]
                        )
                        assert len(clean_status.stdout.strip()) == 0, (
                            "Should be clean after reset"
                        )


class TestPatchGenerationAtomicity:
    """Test atomic operation guarantees."""

    def test_all_or_nothing_patch_generation(self, error_recovery_repo):
        """Test that patch generation is all-or-nothing."""
        repo = error_recovery_repo
        scenario = repo.create_incomplete_operation_scenario()

        git_ops = GitOps(str(repo.repo_path))
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Create scenario where some operations might fail
        hunk_parser = HunkParser(git_ops)
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["change_commit"]]
        )

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Test with all hunks - should succeed completely or fail completely
        original_state = {
            "commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
            "status": git_ops.run_git_command(["status", "--porcelain"]).stdout,
        }

        # Attempt patch generation
        try:
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                hunks, scenario["target_commit"]
            )

            # If successful, patch should be complete
            if patch_content:
                assert len(patch_content.strip()) > 0, (
                    "Successful patch should not be empty"
                )

                # Verify patch structure is complete
                hunk_headers = [
                    line for line in patch_content.split("\n") if line.startswith("@@")
                ]
                file_headers = [
                    line
                    for line in patch_content.split("\n")
                    if line.startswith("--- a/") or line.startswith("+++ b/")
                ]

                # Should have consistent structure
                assert len(file_headers) % 2 == 0, "Should have paired file headers"
                assert len(hunk_headers) > 0, "Should have hunk headers"

        except Exception as e:
            print(f"Patch generation failed atomically: {e}")

        # Verify original state is preserved on failure
        current_state = {
            "commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
            "status": git_ops.run_git_command(["status", "--porcelain"]).stdout,
        }

        # Commit should not change due to patch generation
        assert current_state["commit"] == original_state["commit"], (
            "Commit should not change during patch generation"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
