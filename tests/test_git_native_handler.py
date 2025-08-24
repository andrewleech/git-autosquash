"""Tests for git-native ignore handler."""

import pytest
from unittest.mock import Mock, patch, call

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.git_native_handler import GitNativeIgnoreHandler
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk


class TestGitNativeIgnoreHandler:
    """Test git-native ignore handler functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.git_ops.repo_path = "/test/repo"
        self.handler = GitNativeIgnoreHandler(self.git_ops)

    def test_initialization(self):
        """Test handler initialization."""
        assert self.handler.git_ops is self.git_ops
        assert self.handler.logger is not None

    def test_empty_mappings_success(self):
        """Test handling of empty ignored mappings."""
        result = self.handler.apply_ignored_hunks([])
        
        assert result is True
        # Should not call any git operations
        self.git_ops._run_git_command.assert_not_called()
        self.git_ops._run_git_command_with_input.assert_not_called()

    def test_successful_apply_with_backup_restore(self):
        """Test successful application with backup creation and cleanup."""
        # Create test hunk and mapping
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock git operations for the new index-based approach
        self.git_ops._run_git_command.side_effect = [
            (True, "Saved working directory and index state WIP on main: abc123 commit"),  # stash push
            (True, "tree_hash_original"),   # write-tree (capture index)
            (True, "current_hash_123"),     # hash-object
            (True, "head_hash_456"),        # rev-parse HEAD:file
            (True, "100644 blob_hash 0\ttest.py"),  # ls-files --stage
            (True, "tree_hash_original"),   # read-tree (restore index)
            (True, "diff --git a/test.py b/test.py\nindex head..current 100644\n--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,2 @@\n existing line\n+new line"),  # diff --cached
            (True, "stash@{0} dropped"),    # stash drop
        ]
        
        # Mock patch operations
        self.git_ops._run_git_command_with_input.side_effect = [
            (True, ""),  # apply --cached (stage hunk)
            (True, ""),  # apply --check
            (True, ""),  # apply
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is True
        
        # Verify stash operations
        self.git_ops._run_git_command.assert_any_call(
            "stash", "push", "--include-untracked", "--message", "git-autosquash-comprehensive-backup"
        )
        self.git_ops._run_git_command.assert_any_call("stash", "drop", "stash@{0}")
        
        # Verify index manipulation
        self.git_ops._run_git_command.assert_any_call("write-tree")
        self.git_ops._run_git_command.assert_any_call("read-tree", "tree_hash_original")
        self.git_ops._run_git_command.assert_any_call("diff", "--cached")
        
        # Verify patch operations (stage + validate + apply)
        assert self.git_ops._run_git_command_with_input.call_count == 3

    def test_stash_backup_failure(self):
        """Test handling when stash backup creation fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock stash creation failure
        self.git_ops._run_git_command.return_value = (False, "Cannot save working tree state")

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should not attempt patch operations if backup fails
        self.git_ops._run_git_command_with_input.assert_not_called()

    def test_path_validation_security(self):
        """Test path validation prevents security vulnerabilities."""
        # Test absolute path
        hunk_abs = DiffHunk(
            file_path="/etc/passwd",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing", "+malicious"],
            context_before=[], context_after=[]
        )
        mapping_abs = HunkTargetMapping(
            hunk=hunk_abs, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock successful stash creation
        self.git_ops._run_git_command.return_value = (True, "stash created")

        result = self.handler.apply_ignored_hunks([mapping_abs])

        assert result is False
        # Should clean up stash even on validation failure
        self.git_ops._run_git_command.assert_any_call("stash", "drop", "stash@{0}")

    def test_path_traversal_protection(self):
        """Test protection against path traversal attacks."""
        hunk_traversal = DiffHunk(
            file_path="../../../etc/passwd",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing", "+malicious"],
            context_before=[], context_after=[]
        )
        mapping_traversal = HunkTargetMapping(
            hunk=hunk_traversal, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock successful stash creation
        self.git_ops._run_git_command.return_value = (True, "stash created")

        result = self.handler.apply_ignored_hunks([mapping_traversal])

        assert result is False

    def test_patch_validation_failure(self):
        """Test handling when patch validation fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock operations for index-based approach with validation failure
        self.git_ops._run_git_command.side_effect = [
            (True, "stash created"),      # stash push
            (True, "tree_hash_orig"),    # write-tree (capture)
            (True, "current_hash"),      # hash-object
            (True, "head_hash"),         # rev-parse
            (True, "100644 blob 0\ttest.py"),  # ls-files
            (True, "tree_hash_orig"),    # read-tree (restore)
            (True, "patch content"),     # diff --cached
            (True, "stash popped"),      # stash pop (restore)
            (True, "stash dropped"),     # stash drop (cleanup)
        ]
        
        # Mock patch operations: stage succeeds, but validation fails
        self.git_ops._run_git_command_with_input.side_effect = [
            (True, ""),                   # apply --cached (stage hunk)
            (False, "patch does not apply"),  # apply --check (validation fails)
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should restore from stash on validation failure
        self.git_ops._run_git_command.assert_any_call("stash", "pop", "stash@{0}")

    def test_patch_application_failure_with_restore(self):
        """Test restore behavior when patch application fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock git operations for index approach
        self.git_ops._run_git_command.side_effect = [
            (True, "stash created"),     # stash push
            (True, "tree_hash_orig"),   # write-tree (capture)
            (True, "current_hash"),     # hash-object
            (True, "head_hash"),        # rev-parse
            (True, "100644 blob 0\ttest.py"),  # ls-files
            (True, "tree_hash_orig"),   # read-tree (restore index)
            (True, "patch content"),    # diff --cached
            (True, "stash popped"),     # stash pop (restore)
            (True, "stash dropped"),    # stash drop (cleanup)
        ]
        
        # Mock patch operations - stage succeeds, validation passes, application fails
        self.git_ops._run_git_command_with_input.side_effect = [
            (True, ""),                  # apply --cached (stage)
            (True, ""),                  # apply --check (validation passes)
            (False, "patch application failed"),  # apply (application fails)
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should restore from stash after application failure
        self.git_ops._run_git_command.assert_any_call("stash", "pop", "stash@{0}")

    def test_exception_handling_with_restore(self):
        """Test exception handling triggers restore."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock stash operations
        self.git_ops._run_git_command.side_effect = [
            (True, "stash created"),   # stash push
            (True, "current_hash"),    # hash-object
            (True, "head_hash"),       # rev-parse
            Exception("Unexpected error"),  # Exception during patch creation
            (True, "stash popped"),    # stash pop (restore)
            (True, "stash dropped"),   # stash drop (cleanup)
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should restore from stash after exception
        self.git_ops._run_git_command.assert_any_call("stash", "pop", "stash@{0}")

    def test_force_restore_fallback(self):
        """Test force restore fallback when normal restore fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock git operations with restore failure for index approach
        self.git_ops._run_git_command.side_effect = [
            (True, "stash created"),          # stash push
            (True, "tree_hash_orig"),        # write-tree (capture)
            (True, "current_hash"),          # hash-object
            (True, "head_hash"),             # rev-parse
            (True, "100644 blob 0\ttest.py"),   # ls-files
            (True, "tree_hash_orig"),        # read-tree (restore index)
            (True, "patch content"),         # diff --cached
            (False, "stash pop failed"),     # stash pop (fails)
            (True, "HEAD is now at abc123"),  # reset --hard (force restore)
            (True, "files checked out"),     # checkout (force restore)
            (True, "stash dropped"),         # stash drop (cleanup)
        ]
        
        # Mock patch operations: stage succeeds, validation fails to trigger restore
        self.git_ops._run_git_command_with_input.side_effect = [
            (True, ""),                       # apply --cached (stage)
            (False, "patch validation failed"),  # apply --check (validation fails)
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should attempt force restore fallback
        self.git_ops._run_git_command.assert_any_call("reset", "--hard", "HEAD")
        self.git_ops._run_git_command.assert_any_call("checkout", "stash@{0}", "--", ".")

    def test_multiple_files_batch_processing(self):
        """Test batch processing of multiple files."""
        # Create hunks for different files
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line 1", "+new line 1"],
            context_before=[], context_after=[]
        )
        hunk2 = DiffHunk(
            file_path="file2.py",
            old_start=5, old_count=1, new_start=5, new_count=2,
            lines=["@@ -5,1 +5,2 @@", " line 5", "+new line 5"],
            context_before=[], context_after=[]
        )

        mappings = [
            HunkTargetMapping(hunk=hunk1, target_commit="abc123", confidence="high", blame_info=[]),
            HunkTargetMapping(hunk=hunk2, target_commit="def456", confidence="high", blame_info=[])
        ]

        # Mock git operations for both files with index approach
        self.git_ops._run_git_command.side_effect = [
            (True, "stash created"),      # stash push
            (True, "tree_hash_orig"),    # write-tree (capture)
            (True, "hash1"),              # hash-object file1
            (True, "head_hash1"),         # rev-parse file1
            (True, "100644 blob1 0\tfile1.py"),  # ls-files file1
            (True, "hash2"),              # hash-object file2
            (True, "head_hash2"),         # rev-parse file2
            (True, "100644 blob2 0\tfile2.py"),  # ls-files file2
            (True, "tree_hash_orig"),    # read-tree (restore index)
            (True, "combined patch content"),  # diff --cached
            (True, "stash dropped"),      # stash drop
        ]
        
        # Mock successful patch operations (stage 2 hunks + validate + apply)
        self.git_ops._run_git_command_with_input.side_effect = [
            (True, ""),  # apply --cached (file1)
            (True, ""),  # apply --cached (file2)
            (True, ""),  # apply --check
            (True, ""),  # apply
        ]

        result = self.handler.apply_ignored_hunks(mappings)

        assert result is True
        
        # Should stage both hunks + validate + apply (4 operations)
        assert self.git_ops._run_git_command_with_input.call_count == 4
        
        # Verify final apply call contains patch from diff --cached
        # The patch content comes from diff --cached, not from input_text
        calls = self.git_ops._run_git_command_with_input.call_args_list
        final_apply_call = calls[-1]  # Last call should be the final apply
        assert final_apply_call[0] == ("apply",)

    def test_index_state_capture_and_restore(self):
        """Test git index state capture and restore functionality."""
        handler = GitNativeIgnoreHandler(self.git_ops)
        
        # Mock write-tree and read-tree operations
        self.git_ops._run_git_command.side_effect = [
            (True, "tree_hash_abc123"),  # write-tree (capture)
            (True, ""),                  # read-tree (restore)
        ]

        # Test capture
        success, tree_hash = handler._capture_index_state()
        assert success is True
        assert tree_hash == "tree_hash_abc123"
        
        # Test restore
        success = handler._restore_index_state(tree_hash)
        assert success is True
        
        # Verify git commands were called correctly
        self.git_ops._run_git_command.assert_any_call("write-tree")
        self.git_ops._run_git_command.assert_any_call("read-tree", "tree_hash_abc123")

    def test_stash_info_retrieval(self):
        """Test stash information retrieval for debugging."""
        # Mock stash list output
        stash_output = """stash@{0}: WIP on main: abc123 work in progress
stash@{1}: On feature: def456 saved changes"""
        
        self.git_ops._run_git_command.return_value = (True, stash_output)

        stashes = self.handler.get_stash_info()

        assert len(stashes) == 2
        assert stashes[0]['ref'] == 'stash@{0}'
        assert stashes[0]['type'] == 'WIP on main'
        assert stashes[0]['message'] == 'abc123 work in progress'
        
        assert stashes[1]['ref'] == 'stash@{1}'
        assert stashes[1]['type'] == 'On feature'
        assert stashes[1]['message'] == 'def456 saved changes'

    def test_cleanup_continues_on_failure(self):
        """Test that cleanup continues even if stash drop fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock operations with cleanup failure for index approach
        self.git_ops._run_git_command.side_effect = [
            (True, "stash created"),        # stash push
            (True, "tree_hash_orig"),      # write-tree (capture)
            (True, "current_hash"),        # hash-object
            (True, "head_hash"),           # rev-parse
            (True, "100644 blob 0\ttest.py"),  # ls-files
            (True, "tree_hash_orig"),      # read-tree (restore)
            (True, "patch content"),       # diff --cached
            (False, "stash drop failed"),  # stash drop (fails)
        ]
        
        # Mock successful patch operations
        self.git_ops._run_git_command_with_input.side_effect = [
            (True, ""),  # apply --cached (stage)
            (True, ""),  # apply --check
            (True, ""),  # apply
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        # Should succeed despite cleanup failure
        assert result is True
        
        # Should attempt cleanup even if it fails
        self.git_ops._run_git_command.assert_any_call("stash", "drop", "stash@{0}")


class TestGitNativeHandlerIntegration:
    """Integration tests for git-native handler with main module."""

    @patch('git_autosquash.git_native_complete_handler.GitNativeCompleteHandler')
    def test_main_uses_git_native_handler(self, mock_handler_class):
        """Test that main module uses the complete git-native handler."""
        from git_autosquash.main import _apply_ignored_hunks
        
        # Create mock handler instance
        mock_handler = Mock()
        mock_handler.apply_ignored_hunks.return_value = True
        mock_handler_class.return_value = mock_handler
        
        # Create test data
        git_ops = Mock()
        ignored_mappings = [Mock()]
        
        # Call the function
        result = _apply_ignored_hunks(ignored_mappings, git_ops)
        
        # Verify handler was created and used
        mock_handler_class.assert_called_once_with(git_ops)
        mock_handler.apply_ignored_hunks.assert_called_once_with(ignored_mappings)
        assert result is True