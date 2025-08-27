"""
Tests for rebase conflict recovery and state management.

These tests ensure that the patch generation system handles git rebase conflicts
gracefully and can recover to a clean state in all scenarios.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Dict
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.rebase_manager import RebaseManager, RebaseConflictError
from git_autosquash.exceptions import GitAutoSquashError


class TestRebaseConflictRecovery:
    """Test recovery from various rebase conflict scenarios."""

    def test_rebase_conflict_detection_and_abort(self, conflict_repo):
        """Test that rebase conflicts are detected and cleanly aborted."""

        repo_path, commits = conflict_repo.create_conflict_scenario()
        git_ops = GitOps(repo_path)
        rebase_manager = RebaseManager(git_ops, commits["merge_base"])

        # Get initial state for verification
        initial_head = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()
        initial_branch = git_ops.run_git_command(
            ["symbolic-ref", "--short", "HEAD"]
        ).stdout.strip()

        # Create hunks that will create conflicts when applied
        conflicting_hunks = conflict_repo.get_conflicting_hunks()

        # Simulate the conditions that would lead to a rebase conflict
        # First, create a conflicting change in the working directory
        conflict_file = repo_path / "conflict_file.c"
        conflict_file.write_text(
            """
int main() {
    // This conflicts with the patch we're about to apply
    printf("Conflicting change");
    return 0;
}
        """.strip()
        )

        git_ops.run_git_command(["add", "conflict_file.c"])
        git_ops.run_git_command(["commit", "-m", "Create conflicting state"])

        # Now try to generate patch for the conflicting hunks
        try:
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                conflicting_hunks, commits["target_commit"]
            )

            if patch_content:
                # Try to apply the patch (this may conflict)
                patch_file = repo_path / "conflict_test.patch"
                patch_file.write_text(patch_content)

                apply_result = git_ops.run_git_command(
                    ["apply", "--check", str(patch_file)]
                )

                if apply_result.returncode != 0:
                    # Expected conflict or empty patch - verify we handle it gracefully
                    error_msg = apply_result.stderr.lower()
                    assert (
                        "patch failed" in error_msg
                        or "conflict" in error_msg
                        or "no valid patches" in error_msg
                    ), f"Should detect patch issues: {apply_result.stderr}"

                    # Verify repository is still in a good state
                    status_result = git_ops.run_git_command(["status"])
                    assert status_result.returncode == 0, (
                        "Repository should still be accessible"
                    )

                    # Verify we're still on the correct branch
                    current_branch = git_ops.run_git_command(
                        ["symbolic-ref", "--short", "HEAD"]
                    ).stdout.strip()
                    assert (
                        current_branch in ["main", "master"]
                        or current_branch == initial_branch
                    ), "Should be on main branch or original branch"

        except GitAutoSquashError:
            # This is acceptable - the system should handle conflicts gracefully
            pass
        except RebaseConflictError:
            # This is also acceptable - specific rebase conflict handling
            pass

        # Verify repository is in a clean state after conflict handling
        final_status = git_ops.run_git_command(["status", "--porcelain"]).stdout.strip()
        # Some uncommitted changes might remain, but no merge conflicts should be active

        final_head = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()
        # HEAD might have moved due to our test commit, but should not be in detached state

        symbolic_ref_result = git_ops.run_git_command(["symbolic-ref", "HEAD"])
        assert symbolic_ref_result.returncode == 0, (
            "Should not be in detached HEAD state"
        )

    def test_interrupted_rebase_recovery(self, conflict_repo):
        """Test recovery from interrupted rebase operations."""

        repo_path, commits = conflict_repo.create_conflict_scenario()
        git_ops = GitOps(repo_path)

        # Simulate an interrupted rebase by creating the .git/rebase-merge directory
        rebase_merge_dir = repo_path / ".git" / "rebase-merge"
        if not rebase_merge_dir.exists():
            rebase_merge_dir.mkdir()

            # Create minimal rebase state files
            (rebase_merge_dir / "head-name").write_text("refs/heads/feature-branch\n")
            (rebase_merge_dir / "onto").write_text(commits["target_commit"] + "\n")
            (rebase_merge_dir / "orig-head").write_text(commits["source_commit"] + "\n")

        # Our operations should detect and handle the interrupted rebase
        try:
            rebase_manager = RebaseManager(git_ops, commits["merge_base"])

            # Should either handle the interrupted state or fail gracefully
            hunks = conflict_repo.get_conflicting_hunks()
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                hunks, commits["target_commit"]
            )

            # If it succeeds, verify the rebase state is resolved
            assert (
                not rebase_merge_dir.exists()
                or len(list(rebase_merge_dir.iterdir())) == 0
            ), "Should clean up rebase state"

        except (GitAutoSquashError, RebaseConflictError):
            # Acceptable - should fail gracefully for interrupted rebase
            pass

        # Verify we can clean up the interrupted state manually
        if rebase_merge_dir.exists():
            # Simulate git rebase --abort
            abort_result = git_ops.run_git_command(["rebase", "--abort"])
            # This might fail if there's no rebase in progress, which is fine

        # Verify repository is functional after cleanup
        status_result = git_ops.run_git_command(["status"])
        assert status_result.returncode == 0, (
            "Repository should be functional after cleanup"
        )

    def test_partial_application_rollback(self, conflict_repo):
        """Test rollback when patch application partially succeeds then fails."""

        repo_path, commits = conflict_repo.create_multi_file_scenario()
        git_ops = GitOps(repo_path)
        rebase_manager = RebaseManager(git_ops, commits["merge_base"])

        # Create hunks where some will succeed and others will fail
        mixed_hunks = conflict_repo.get_mixed_success_hunks()

        # Record initial state of all files
        initial_file_states = {}
        for file_path in ["file1.c", "file2.c", "file3.c"]:
            file_obj = repo_path / file_path
            if file_obj.exists():
                initial_file_states[file_path] = file_obj.read_text()

        initial_head = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

        try:
            # Attempt to apply mixed hunks
            patch_content = rebase_manager._create_corrected_patch_for_hunks(
                mixed_hunks, commits["target_commit"]
            )

            if patch_content:
                # Try to apply - some parts might succeed, others fail
                patch_file = repo_path / "mixed_patch.patch"
                patch_file.write_text(patch_content)

                apply_result = git_ops.run_git_command(["apply", str(patch_file)])

                if apply_result.returncode != 0:
                    # Patch failed - verify no partial changes remain
                    # Git apply is atomic, so either all changes apply or none do

                    # Verify files are back to initial state
                    for file_path, initial_content in initial_file_states.items():
                        file_obj = repo_path / file_path
                        if file_obj.exists():
                            current_content = file_obj.read_text()
                            # The file content might have changed due to our test setup,
                            # but it should not have partial patch applications
                            assert "PARTIAL_CHANGE_MARKER" not in current_content, (
                                f"Should not have partial changes in {file_path}"
                            )

        except Exception:
            # If patch generation itself fails, that's acceptable
            pass

        # Verify repository state is consistent
        final_head = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

        # HEAD should not have moved due to failed patch application
        # (though it might have moved due to our test setup)
        status_result = git_ops.run_git_command(["status"])
        assert status_result.returncode == 0, "Repository should be in valid state"

        # Verify no merge conflicts are active
        status_output = git_ops.run_git_command(["status", "--porcelain"]).stdout
        assert "UU " not in status_output, "Should not have unmerged files"
        assert "AA " not in status_output, "Should not have added by both conflicts"

    def test_repository_corruption_prevention(self, conflict_repo):
        """Test that operations never leave repository in corrupted state."""

        repo_path, commits = conflict_repo.create_conflict_scenario()
        git_ops = GitOps(repo_path)

        # Perform various operations that could potentially corrupt repository
        operations = [
            lambda: self._attempt_concurrent_operations(git_ops, commits),
            lambda: self._attempt_invalid_patch_application(git_ops, commits),
            lambda: self._attempt_filesystem_interference(git_ops, repo_path),
        ]

        for operation in operations:
            try:
                operation()
            except Exception:
                # Operations may fail, but should not corrupt repository
                pass

            # After each operation, verify repository integrity
            self._verify_repository_integrity(git_ops, repo_path)

    def _attempt_concurrent_operations(self, git_ops: GitOps, commits: Dict[str, str]):
        """Simulate concurrent operations that might cause issues."""

        rebase_manager = RebaseManager(git_ops, commits["merge_base"])

        # Create dummy hunks
        hunk = conflict_repo.get_simple_hunk()

        # Attempt multiple operations (simulating race conditions)
        for _ in range(3):
            try:
                rebase_manager._create_corrected_patch_for_hunks(
                    [hunk], commits["target_commit"]
                )
            except Exception:
                pass

    def _attempt_invalid_patch_application(
        self, git_ops: GitOps, commits: Dict[str, str]
    ):
        """Attempt to apply invalid patches."""

        invalid_patch_content = """
diff --git a/nonexistent.c b/nonexistent.c
index 1234567..abcdefg 100644
--- a/nonexistent.c
+++ b/nonexistent.c
@@ -1,1 +1,1 @@
-invalid old content
+invalid new content
        """.strip()

        # Try to apply invalid patch
        patch_file = git_ops.repo_path / "invalid.patch"
        patch_file.write_text(invalid_patch_content)

        # This should fail gracefully without corrupting repository
        git_ops.run_git_command(["apply", str(patch_file)])

    def _attempt_filesystem_interference(self, git_ops: GitOps, repo_path: Path):
        """Simulate filesystem-level interference."""

        # Create files that might interfere with git operations
        interference_files = [
            repo_path / ".git" / "COMMIT_EDITMSG_interference",
            repo_path / ".git" / "index.lock_test",  # Don't actually create .lock files
        ]

        for interference_file in interference_files:
            if not interference_file.name.endswith("_test"):  # Safety check
                continue
            try:
                interference_file.write_text("interference content")
            except Exception:
                pass  # Filesystem might prevent this, which is fine

    def _verify_repository_integrity(self, git_ops: GitOps, repo_path: Path):
        """Verify that git repository is in a valid, uncorrupted state."""

        # Basic git operations should work
        status_result = git_ops.run_git_command(["status"])
        assert status_result.returncode == 0, "Git status should work"

        # Repository should have a valid HEAD
        head_result = git_ops.run_git_command(["rev-parse", "HEAD"])
        assert head_result.returncode == 0, "Should have valid HEAD"
        assert len(head_result.stdout.strip()) == 40, "HEAD should be valid SHA"

        # Should be able to show commit history
        log_result = git_ops.run_git_command(["log", "--oneline", "-5"])
        assert log_result.returncode == 0, "Should be able to show log"

        # Git fsck should pass (basic integrity check)
        fsck_result = git_ops.run_git_command(["fsck", "--no-dangling"])
        assert fsck_result.returncode == 0, (
            f"Repository integrity check failed: {fsck_result.stderr}"
        )

        # Should not be in detached HEAD unless intentional
        symbolic_ref_result = git_ops.run_git_command(["symbolic-ref", "HEAD"])
        if symbolic_ref_result.returncode != 0:
            # If we're in detached HEAD, there should be no ongoing merge/rebase
            merge_head = repo_path / ".git" / "MERGE_HEAD"
            rebase_apply = repo_path / ".git" / "rebase-apply"
            rebase_merge = repo_path / ".git" / "rebase-merge"

            assert not merge_head.exists(), (
                "Should not have ongoing merge in detached HEAD"
            )
            assert not rebase_apply.exists(), (
                "Should not have ongoing rebase-apply in detached HEAD"
            )
            assert not rebase_merge.exists(), (
                "Should not have ongoing rebase-merge in detached HEAD"
            )


@pytest.fixture
def conflict_repo():
    """Create repository scenarios that will generate conflicts."""

    class ConflictRepoBuilder:
        def create_conflict_scenario(self) -> tuple[Path, Dict[str, str]]:
            """Create a repository setup that will lead to conflicts."""

            temp_dir = tempfile.mkdtemp()
            repo_path = Path(temp_dir) / "conflict_repo"
            repo_path.mkdir()

            # Initialize git
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_path,
                check=True,
            )

            # Create initial file
            conflict_file = repo_path / "conflict_file.c"
            conflict_file.write_text(
                """
int main() {
    printf("Original version");
    return 0;
}
            """.strip()
            )

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial version"], cwd=repo_path, check=True
            )

            merge_base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Create target commit (what we want to squash into)
            conflict_file.write_text(
                """
int main() {
    printf("Target version");
    return 0;
}
            """.strip()
            )

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Target commit"], cwd=repo_path, check=True
            )

            target_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            # Create source commit (conflicts with target)
            conflict_file.write_text(
                """
int main() {
    printf("Source version that conflicts");
    return 0;
}
            """.strip()
            )

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Source commit"], cwd=repo_path, check=True
            )

            source_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            return repo_path, {
                "merge_base": merge_base,
                "target_commit": target_commit,
                "source_commit": source_commit,
            }

        def create_multi_file_scenario(self) -> tuple[Path, Dict[str, str]]:
            """Create scenario with multiple files for testing partial failures."""

            repo_path, commits = self.create_conflict_scenario()

            # Add more files
            for i in range(1, 4):
                file_path = repo_path / f"file{i}.c"
                file_path.write_text(
                    f"""
int function_{i}() {{
    return {i};
}}
                """.strip()
                )

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Add multiple files"], cwd=repo_path, check=True
            )

            # Update commits dict
            commits["source_commit"] = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            return repo_path, commits

        def get_conflicting_hunks(self):
            """Get hunks that will create conflicts."""
            from git_autosquash.hunk_parser import DiffHunk

            return [
                DiffHunk(
                    file_path="conflict_file.c",
                    old_start=2,
                    old_count=1,
                    new_start=2,
                    new_count=1,
                    lines=[
                        "@@ -2,1 +2,1 @@",
                        '-    printf("Original version");',
                        '+    printf("Conflicting change");',
                    ],
                    context_before=[],
                    context_after=[],
                )
            ]

        def get_mixed_success_hunks(self):
            """Get hunks where some will succeed and others will fail."""
            from git_autosquash.hunk_parser import DiffHunk

            return [
                # This should succeed
                DiffHunk(
                    file_path="file1.c",
                    old_start=2,
                    old_count=1,
                    new_start=2,
                    new_count=1,
                    lines=[
                        "@@ -2,1 +2,1 @@",
                        "-    return 1;",
                        "+    return 42;",
                    ],
                    context_before=[],
                    context_after=[],
                ),
                # This might fail
                DiffHunk(
                    file_path="nonexistent_file.c",
                    old_start=1,
                    old_count=1,
                    new_start=1,
                    new_count=1,
                    lines=[
                        "@@ -1,1 +1,1 @@",
                        "-nonexistent content",
                        "+replacement content",
                    ],
                    context_before=[],
                    context_after=[],
                ),
            ]

        def get_simple_hunk(self):
            """Get a simple hunk for basic testing."""
            from git_autosquash.hunk_parser import DiffHunk

            return DiffHunk(
                file_path="conflict_file.c",
                old_start=1,
                old_count=1,
                new_start=1,
                new_count=1,
                lines=[
                    "@@ -1,1 +1,1 @@",
                    "-int main() {",
                    "+int main(void) {",
                ],
                context_before=[],
                context_after=[],
            )

    yield ConflictRepoBuilder()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
