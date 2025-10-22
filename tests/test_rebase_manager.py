"""Tests for RebaseManager."""

import subprocess
import unittest.mock
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.rebase_manager import RebaseConflictError, RebaseManager


class TestRebaseManager:
    """Test cases for RebaseManager."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.mock_git_ops = Mock()
        self.mock_git_ops.repo_path = "/test/repo"
        self.merge_base = "abc123"
        self.rebase_manager = RebaseManager(self.mock_git_ops, self.merge_base)

    def test_init(self) -> None:
        """Test RebaseManager initialization."""
        assert self.rebase_manager.git_ops is self.mock_git_ops
        assert self.rebase_manager.merge_base == self.merge_base
        assert self.rebase_manager._stash_ref is None
        assert self.rebase_manager._original_branch is None

    def test_group_hunks_by_commit(self) -> None:
        """Test grouping hunks by target commit."""
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line1", "+line2"],
            context_before=[],
            context_after=[],
        )
        hunk2 = DiffHunk(
            file_path="file2.py",
            old_start=5,
            old_count=1,
            new_start=5,
            new_count=1,
            lines=["@@ -5,1 +5,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )
        hunk3 = DiffHunk(
            file_path="file1.py",
            old_start=10,
            old_count=1,
            new_start=10,
            new_count=1,
            lines=["@@ -10,1 +10,1 @@", "-old2", "+new2"],
            context_before=[],
            context_after=[],
        )

        mappings = [
            HunkTargetMapping(
                hunk=hunk1, target_commit="commit1", confidence="high", blame_info=[]
            ),
            HunkTargetMapping(
                hunk=hunk2, target_commit="commit2", confidence="high", blame_info=[]
            ),
            HunkTargetMapping(
                hunk=hunk3, target_commit="commit1", confidence="medium", blame_info=[]
            ),
            HunkTargetMapping(
                hunk=hunk1, target_commit=None, confidence="low", blame_info=[]
            ),
        ]

        result = self.rebase_manager._group_hunks_by_commit(mappings)

        assert len(result) == 2
        assert "commit1" in result
        assert "commit2" in result
        assert len(result["commit1"]) == 2
        assert len(result["commit2"]) == 1
        assert result["commit1"] == [hunk1, hunk3]
        assert result["commit2"] == [hunk2]

    def test_get_commit_order(self) -> None:
        """Test getting commits in git topological order."""
        commits = {"commit1", "commit2", "commit3"}

        # Mock BatchGitOperations to return branch commits in topological order (newest first)
        with patch(
            "git_autosquash.rebase_manager.BatchGitOperations"
        ) as mock_batch_ops_class:
            mock_batch_ops = Mock()
            mock_batch_ops_class.return_value = mock_batch_ops

            # Simulate git chronological order: commit2 -> commit3 -> commit1 (chronological order)
            mock_batch_ops.get_branch_commits.return_value = [
                "commit2",
                "commit3",
                "commit1",
            ]

            result = self.rebase_manager._get_commit_order(commits)

            # Should maintain the chronological order from get_branch_commits
            assert result == ["commit2", "commit3", "commit1"]

    def test_get_commit_order_with_missing_commits(self) -> None:
        """Test commit ordering when some commits are not found in branch."""
        commits = {"commit1", "commit2", "commit3"}

        # Mock BatchGitOperations to return only some commits
        with patch(
            "git_autosquash.rebase_manager.BatchGitOperations"
        ) as mock_batch_ops_class:
            mock_batch_ops = Mock()
            mock_batch_ops_class.return_value = mock_batch_ops

            # Only commit1 and commit2 are in branch, commit3 is missing
            mock_batch_ops.get_branch_commits.return_value = ["commit2", "commit1"]

            result = self.rebase_manager._get_commit_order(commits)

            # commit2 and commit1 should be in chronological order, commit3 at end (fallback)
            assert result[0] == "commit2"  # first in chronological order
            assert result[1] == "commit1"
            assert result[2] == "commit3"  # missing commits added at end

    def test_handle_working_tree_state_clean(self) -> None:
        """Test handling clean working tree."""
        self.mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": True,
            "has_staged": False,
            "has_unstaged": False,
        }

        self.rebase_manager._handle_working_tree_state()

        # Should not call stash
        self.mock_git_ops.run_git_command.assert_not_called()
        assert self.rebase_manager._stash_ref is None

    def test_handle_working_tree_state_dirty(self) -> None:
        """Test handling dirty working tree."""
        self.mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": True,
            "has_unstaged": False,
        }

        # Mock successful stash create/store (new behavior)
        # First call: diff --cached --quiet (checks for staged changes)
        diff_result = Mock()
        diff_result.returncode = 1  # Non-zero means changes exist

        # Second call: write-tree (for staged-only stash)
        tree_result = Mock()
        tree_result.returncode = 0
        tree_result.stdout = "abc123tree"

        # Third call: commit-tree (creates stash commit)
        commit_result = Mock()
        commit_result.returncode = 0
        commit_result.stdout = "def456stash1234567890123456789012345678"  # Valid SHA

        # Fourth call: stash store
        store_result = Mock()
        store_result.returncode = 0

        self.mock_git_ops.run_git_command.side_effect = [
            diff_result,
            tree_result,
            commit_result,
            store_result,
        ]

        self.rebase_manager._handle_working_tree_state()

        # Should have created stash with SHA reference
        assert (
            self.rebase_manager._stash_ref == "def456stash1234567890123456789012345678"
        )

    def test_handle_working_tree_state_stash_fails(self) -> None:
        """Test handling when stash fails."""
        self.mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": True,
            "has_unstaged": False,
        }

        # Mock failed stash create/store (new behavior)
        # First call: diff --cached --quiet (checks for staged changes)
        diff_result = Mock()
        diff_result.returncode = 1  # Non-zero means changes exist

        # Second call: write-tree fails
        tree_result = Mock()
        tree_result.returncode = 1
        tree_result.stderr = "write-tree failed"

        self.mock_git_ops.run_git_command.side_effect = [diff_result, tree_result]

        # Should NOT raise exception - just logs and continues with None stash
        self.rebase_manager._handle_working_tree_state()

        # Stash ref should be None since stash creation failed
        assert self.rebase_manager._stash_ref is None

    def test_create_patch_for_hunks(self) -> None:
        """Test creating patch content from hunks."""
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line1", "+line2"],
            context_before=[],
            context_after=[],
        )
        hunk2 = DiffHunk(
            file_path="file2.py",
            old_start=5,
            old_count=1,
            new_start=5,
            new_count=1,
            lines=["@@ -5,1 +5,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )

        result = self.rebase_manager._create_patch_for_hunks([hunk1, hunk2])

        expected_lines = [
            "--- a/file1.py",
            "+++ b/file1.py",
            "@@ -1,1 +1,2 @@",
            " line1",
            "+line2",
            "--- a/file2.py",
            "+++ b/file2.py",
            "@@ -5,1 +5,1 @@",
            "-old",
            "+new",
        ]
        expected = "\n".join(expected_lines) + "\n"
        assert result == expected

    def test_create_patch_for_hunks_same_file(self) -> None:
        """Test creating patch when multiple hunks are from same file."""
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line1", "+line2"],
            context_before=[],
            context_after=[],
        )
        hunk2 = DiffHunk(
            file_path="file1.py",
            old_start=5,
            old_count=1,
            new_start=5,
            new_count=1,
            lines=["@@ -5,1 +5,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )

        result = self.rebase_manager._create_patch_for_hunks([hunk1, hunk2])

        # Should only have one file header for file1.py
        lines = result.split("\n")
        file_headers = [line for line in lines if line.startswith("---")]
        assert len(file_headers) == 1
        assert file_headers[0] == "--- a/file1.py"

    @patch("tempfile.NamedTemporaryFile")
    @patch("os.unlink")
    @patch("os.path.exists")
    def test_start_rebase_edit_success(
        self, mock_exists, mock_unlink, mock_tempfile
    ) -> None:
        """Test starting rebase edit successfully."""
        # Mock temp file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test_todo"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        # Mock no existing rebase state
        mock_exists.return_value = False

        # Mock successful rebase start - need four calls: rev-parse, merge-base, rev-list, then rebase
        # First call: rev-parse HEAD (from _generate_rebase_todo)
        head_result = Mock()
        head_result.returncode = 0
        head_result.stdout = "currenthead123456789012345678901234567"

        # Second call: merge-base --is-ancestor (check if target is ancestor)
        merge_base_result = Mock()
        merge_base_result.returncode = 0  # is-ancestor succeeds

        # Third call: rev-list --reverse (get commit list)
        rev_list_result = Mock()
        rev_list_result.returncode = 0
        rev_list_result.stdout = "commit123\ncommit456\n"  # Mock commit list output

        # Fourth call: rebase -i
        rebase_result = Mock()
        rebase_result.returncode = 0

        self.mock_git_ops.run_git_command.side_effect = [
            head_result,
            merge_base_result,
            rev_list_result,
            rebase_result,
        ]

        result = self.rebase_manager._start_rebase_edit("commit123")

        assert result is True
        mock_file.write.assert_called_once_with("edit commit123\npick commit456\n")
        assert self.mock_git_ops.run_git_command.call_count == 4
        mock_unlink.assert_called_once_with("/tmp/test_todo")

    @patch("tempfile.NamedTemporaryFile")
    def test_start_rebase_edit_failure(self, mock_tempfile) -> None:
        """Test rebase edit start failure."""
        # Mock temp file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test_todo"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        # Mock failed rebase start
        rebase_result = Mock()
        rebase_result.returncode = 1
        self.mock_git_ops.run_git_command.return_value = rebase_result

        result = self.rebase_manager._start_rebase_edit("commit123")

        assert result is False

    @patch("tempfile.NamedTemporaryFile")
    @patch("os.unlink")
    def test_apply_patch_success(self, mock_unlink, mock_tempfile) -> None:
        """Test successful patch application."""
        # Mock temp file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test_patch"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        # Mock successful git apply
        apply_result = Mock()
        apply_result.returncode = 0
        self.mock_git_ops.run_git_command.return_value = apply_result

        patch_content = "patch content"
        self.rebase_manager._apply_patch(patch_content)

        mock_file.write.assert_called_once_with(patch_content)
        self.mock_git_ops.run_git_command.assert_called_once_with(
            [
                "apply",
                "--ignore-whitespace",
                "--whitespace=nowarn",
                "/tmp/test_patch",
            ]
        )
        mock_unlink.assert_called_once_with("/tmp/test_patch")

    @patch("tempfile.NamedTemporaryFile")
    def test_apply_patch_with_conflicts(self, mock_tempfile) -> None:
        """Test patch application with conflicts."""
        # Mock temp file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test_patch"
        mock_tempfile.return_value.__enter__.return_value = mock_file

        # Mock failed git apply
        apply_result = Mock()
        apply_result.returncode = 1
        apply_result.stderr = "conflict error"
        self.mock_git_ops.run_git_command.return_value = apply_result

        # Mock _get_conflicted_files to return conflicts
        with patch.object(
            self.rebase_manager, "_get_conflicted_files", return_value=["file1.py"]
        ):
            with pytest.raises(RebaseConflictError) as exc_info:
                self.rebase_manager._apply_patch("patch content")

            assert "conflict error" in str(exc_info.value)
            assert exc_info.value.conflicted_files == ["file1.py"]

    def test_amend_commit_success(self) -> None:
        """Test successful commit amendment."""
        # Mock successful git commands
        success_result = Mock()
        success_result.returncode = 0
        self.mock_git_ops.run_git_command.return_value = success_result

        self.rebase_manager._amend_commit()

        # Should call git add and git commit
        expected_calls = [
            unittest.mock.call(["add", "."]),
            unittest.mock.call(["commit", "--amend", "--no-edit"]),
        ]
        self.mock_git_ops.run_git_command.assert_has_calls(expected_calls)

    def test_amend_commit_add_fails(self) -> None:
        """Test commit amendment when git add fails."""
        # Mock failed git add
        add_result = Mock()
        add_result.returncode = 1
        add_result.stderr = "add failed"
        self.mock_git_ops.run_git_command.return_value = add_result

        with pytest.raises(Exception, match="Failed to stage changes"):
            self.rebase_manager._amend_commit()

    def test_continue_rebase_success(self) -> None:
        """Test successful rebase continuation."""
        continue_result = Mock()
        continue_result.returncode = 0
        self.mock_git_ops.run_git_command.return_value = continue_result

        self.rebase_manager._continue_rebase()

        self.mock_git_ops.run_git_command.assert_called_once_with(
            ["rebase", "--continue"]
        )

    def test_continue_rebase_with_conflicts(self) -> None:
        """Test rebase continuation with conflicts."""
        # Mock failed rebase continue
        continue_result = Mock()
        continue_result.returncode = 1
        continue_result.stderr = "conflicts detected"
        self.mock_git_ops.run_git_command.return_value = continue_result

        # Mock conflicted files
        with patch.object(
            self.rebase_manager, "_get_conflicted_files", return_value=["file1.py"]
        ):
            with pytest.raises(RebaseConflictError) as exc_info:
                self.rebase_manager._continue_rebase()

            assert "conflicts detected" in str(exc_info.value)
            assert exc_info.value.conflicted_files == ["file1.py"]

    def test_get_conflicted_files(self) -> None:
        """Test getting conflicted files."""
        # Mock git diff output with conflicted files
        diff_result = Mock()
        diff_result.returncode = 0
        diff_result.stdout = "file1.py\nfile2.py\n"
        self.mock_git_ops.run_git_command.return_value = diff_result

        result = self.rebase_manager._get_conflicted_files()

        assert result == ["file1.py", "file2.py"]
        self.mock_git_ops.run_git_command.assert_called_once_with(
            ["diff", "--name-only", "--diff-filter=U"]
        )

    def test_get_conflicted_files_no_conflicts(self) -> None:
        """Test getting conflicted files when none exist."""
        # Mock git diff with no output
        diff_result = Mock()
        diff_result.returncode = 0
        diff_result.stdout = ""
        self.mock_git_ops.run_git_command.return_value = diff_result

        result = self.rebase_manager._get_conflicted_files()

        assert result == []

    def test_get_conflicted_files_command_fails(self) -> None:
        """Test getting conflicted files when git command fails."""
        # Mock git diff failure
        diff_result = Mock()
        diff_result.returncode = 1
        self.mock_git_ops.run_git_command.return_value = diff_result

        result = self.rebase_manager._get_conflicted_files()

        assert result == []

    def test_abort_rebase(self) -> None:
        """Test aborting rebase."""
        abort_result = Mock()
        abort_result.returncode = 0
        self.mock_git_ops.run_git_command.return_value = abort_result

        self.rebase_manager._abort_rebase()

        self.mock_git_ops.run_git_command.assert_called_once_with(["rebase", "--abort"])

    def test_abort_rebase_ignores_errors(self) -> None:
        """Test that abort rebase ignores errors."""
        # Mock git command to raise subprocess error
        self.mock_git_ops.run_git_command.side_effect = subprocess.SubprocessError(
            "abort failed"
        )

        # Should not raise exception
        self.rebase_manager._abort_rebase()

    def test_cleanup_on_error(self) -> None:
        """Test cleanup after error."""
        # Use valid SHA format (new behavior)
        stash_sha = "abc123def456789012345678901234567890abcd"
        self.rebase_manager._stash_ref = stash_sha

        # Mock successful commands for new stash restoration flow
        # First call: rebase --abort
        abort_result = Mock()
        abort_result.returncode = 0

        # Second call: cat-file -t (verify stash exists)
        catfile_result = Mock()
        catfile_result.returncode = 0
        catfile_result.stdout = "commit"

        # Third call: stash apply <sha>
        apply_result = Mock()
        apply_result.returncode = 0

        # Fourth call: stash list --format=%H %gd (find stash reference)
        list_result = Mock()
        list_result.returncode = 0
        list_result.stdout = f"{stash_sha} (stash@{{0}})\n"

        # Fifth call: stash drop stash@{0}
        drop_result = Mock()
        drop_result.returncode = 0

        self.mock_git_ops.run_git_command.side_effect = [
            abort_result,
            catfile_result,
            apply_result,
            list_result,
            drop_result,
        ]

        self.rebase_manager._cleanup_on_error()

        # Should have called rebase abort and stash restoration sequence
        assert self.mock_git_ops.run_git_command.call_count == 5
        assert self.rebase_manager._stash_ref is None

    def test_cleanup_on_error_no_stash(self) -> None:
        """Test cleanup when no stash exists."""
        # No stash ref set
        assert self.rebase_manager._stash_ref is None

        success_result = Mock()
        success_result.returncode = 0
        self.mock_git_ops.run_git_command.return_value = success_result

        self.rebase_manager._cleanup_on_error()

        # Should only call abort rebase, not stash pop
        self.mock_git_ops.run_git_command.assert_called_once_with(["rebase", "--abort"])

    def test_is_rebase_in_progress_true(self) -> None:
        """Test detecting rebase in progress."""
        status_result = Mock()
        status_result.returncode = 0
        status_result.stdout = (
            "# rebase in progress; onto abc123\n# branch.head = main\n"
        )
        self.mock_git_ops.run_git_command.return_value = status_result

        result = self.rebase_manager.is_rebase_in_progress()

        assert result is True

    def test_is_rebase_in_progress_false(self) -> None:
        """Test detecting no rebase in progress."""
        status_result = Mock()
        status_result.returncode = 0
        status_result.stdout = "# branch.head = main\n"
        self.mock_git_ops.run_git_command.return_value = status_result

        result = self.rebase_manager.is_rebase_in_progress()

        assert result is False

    def test_is_rebase_in_progress_command_fails(self) -> None:
        """Test rebase detection when git command fails."""
        status_result = Mock()
        status_result.returncode = 1
        self.mock_git_ops.run_git_command.return_value = status_result

        result = self.rebase_manager.is_rebase_in_progress()

        assert result is False

    @patch("os.path.exists")
    @patch("builtins.open", new_callable=mock_open)
    def test_get_rebase_status_in_progress(self, mock_file, mock_exists) -> None:
        """Test getting rebase status when rebase is in progress."""
        # Mock rebase directory and files exist
        mock_exists.return_value = True
        mock_file.return_value.read.side_effect = ["3", "10"]  # step 3 of 10

        # Mock rebase in progress
        with patch.object(
            self.rebase_manager, "is_rebase_in_progress", return_value=True
        ):
            with patch.object(
                self.rebase_manager, "_get_conflicted_files", return_value=["file1.py"]
            ):
                result = self.rebase_manager.get_rebase_status()

                assert result["in_progress"] is True
                assert result["conflicted_files"] == ["file1.py"]
                assert result["step"] == 3
                assert result["total_steps"] == 10

    def test_get_rebase_status_not_in_progress(self) -> None:
        """Test getting rebase status when no rebase is active."""
        with patch.object(
            self.rebase_manager, "is_rebase_in_progress", return_value=False
        ):
            result = self.rebase_manager.get_rebase_status()

            assert result["in_progress"] is False
            assert result["current_commit"] is None
            assert result["conflicted_files"] == []
            assert result["step"] is None
            assert result["total_steps"] is None

    def test_execute_squash_empty_mappings(self) -> None:
        """Test executing squash with no mappings."""
        from git_autosquash.squash_context import SquashContext

        mock_context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        result = self.rebase_manager.execute_squash([], [], context=mock_context)
        assert result is True
        self.mock_git_ops.get_current_branch.assert_not_called()

    def test_execute_squash_no_current_branch(self) -> None:
        """Test executing squash when current branch cannot be determined."""
        from git_autosquash.squash_context import SquashContext

        hunk = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line1", "+line2"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        mock_context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        self.mock_git_ops.get_current_branch.return_value = None

        with pytest.raises(ValueError, match="Cannot determine current branch"):
            self.rebase_manager.execute_squash([mapping], [], context=mock_context)


class TestRebaseConflictError:
    """Test cases for RebaseConflictError."""

    def test_init(self) -> None:
        """Test RebaseConflictError initialization."""
        conflicted_files = ["file1.py", "file2.py"]
        error = RebaseConflictError("Conflicts detected", conflicted_files)

        assert str(error) == "Conflicts detected"
        assert error.conflicted_files == conflicted_files

    def test_init_empty_files(self) -> None:
        """Test RebaseConflictError with no conflicted files."""
        error = RebaseConflictError("Some error", [])

        assert str(error) == "Some error"
        assert error.conflicted_files == []
