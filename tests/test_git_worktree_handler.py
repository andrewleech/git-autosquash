"""Tests for git worktree-based ignore handler."""

import pytest
from unittest.mock import Mock, patch, call
import tempfile
from pathlib import Path

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.git_worktree_handler import GitWorktreeIgnoreHandler
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk


class TestGitWorktreeIgnoreHandler:
    """Test git worktree-based ignore handler functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.git_ops.repo_path = "/test/repo"
        self.handler = GitWorktreeIgnoreHandler(self.git_ops)

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

    def test_worktree_support_check_success(self):
        """Test successful worktree support detection."""
        self.git_ops._run_git_command.return_value = (True, "git-worktree - Manage multiple working trees\\nCOMMANDS\\n   add <path>")
        
        result = self.handler._check_worktree_support()
        
        assert result is True
        self.git_ops._run_git_command.assert_called_with("worktree", "--help")

    def test_worktree_support_check_failure(self):
        """Test worktree support detection failure."""
        self.git_ops._run_git_command.return_value = (False, "command not found")
        
        result = self.handler._check_worktree_support()
        
        assert result is False

    def test_worktree_not_supported(self):
        """Test handling when worktree is not supported."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock worktree support check failure
        self.git_ops._run_git_command.return_value = (False, "command not found")

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should only call worktree support check
        self.git_ops._run_git_command.assert_called_once_with("worktree", "--help")

    @patch('tempfile.mkdtemp')
    def test_successful_worktree_creation(self, mock_mkdtemp):
        """Test successful temporary worktree creation."""
        mock_mkdtemp.return_value = "/tmp/test-worktree-123"
        self.git_ops._run_git_command.return_value = (True, "Preparing worktree")

        result = self.handler._create_temporary_worktree()

        assert result == "/tmp/test-worktree-123"
        mock_mkdtemp.assert_called_once_with(prefix="git-autosquash-", suffix="-worktree")
        self.git_ops._run_git_command.assert_called_with(
            "worktree", "add", "--detach", "/tmp/test-worktree-123", "HEAD"
        )

    @patch('tempfile.mkdtemp')
    @patch('shutil.rmtree')
    def test_worktree_creation_failure_cleanup(self, mock_rmtree, mock_mkdtemp):
        """Test cleanup when worktree creation fails."""
        mock_mkdtemp.return_value = "/tmp/test-worktree-failed"
        self.git_ops._run_git_command.return_value = (False, "worktree add failed")

        result = self.handler._create_temporary_worktree()

        assert result is None
        mock_rmtree.assert_called_once_with("/tmp/test-worktree-failed", ignore_errors=True)

    def test_successful_apply_with_worktree(self):
        """Test successful application using worktree approach."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock successful worktree operations
        with patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch.object(self.handler, '_create_temporary_worktree') as mock_create_wt, \
             patch('git_autosquash.git_worktree_handler.GitOps') as mock_git_ops_class:

            mock_mkdtemp.return_value = "/tmp/test-worktree-success"
            mock_create_wt.return_value = "/tmp/test-worktree-success"
            
            # Mock worktree GitOps instance
            mock_worktree_git_ops = Mock(spec=GitOps)
            mock_git_ops_class.return_value = mock_worktree_git_ops
            
            # Mock git operations
            self.git_ops._run_git_command.side_effect = [
                (True, "worktree help with add command"),      # worktree support check
                (True, "stash created"),                       # stash push (backup)
                (True, "stash dropped"),                       # stash drop (cleanup)
                (True, "worktree removed"),                    # worktree remove
            ]
            
            # Mock worktree-specific operations
            mock_worktree_git_ops._run_git_command.side_effect = [
                (True, "current_hash_123"),                    # hash-object
                (True, "head_hash_456"),                       # rev-parse HEAD:file
                (True, "100644 blob_hash 0\\ttest.py"),        # ls-files --stage
                (True, "diff --git a/test.py b/test.py\\n@@ -1,1 +1,2 @@\\n existing line\\n+new line"),  # diff HEAD
            ]
            
            # Mock patch operations
            mock_worktree_git_ops._run_git_command_with_input.return_value = (True, "")  # apply hunk
            self.git_ops._run_git_command_with_input.side_effect = [
                (True, ""),  # apply --check (validation)
                (True, ""),  # apply (final application)
            ]

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is True
            
            # Verify worktree support check
            self.git_ops._run_git_command.assert_any_call("worktree", "--help")
            
            # Verify stash operations
            self.git_ops._run_git_command.assert_any_call(
                "stash", "push", "--include-untracked", "--message", "git-autosquash-worktree-backup"
            )
            self.git_ops._run_git_command.assert_any_call("stash", "drop", "stash@{0}")
            
            # Verify final patch application
            assert self.git_ops._run_git_command_with_input.call_count == 2  # check + apply

    def test_hunk_application_failure_in_worktree(self):
        """Test handling of hunk application failure within worktree."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        with patch('tempfile.mkdtemp') as mock_mkdtemp, \
             patch.object(self.handler, '_create_temporary_worktree') as mock_create_wt, \
             patch('git_autosquash.git_worktree_handler.GitOps') as mock_git_ops_class:

            mock_create_wt.return_value = "/tmp/test-worktree-fail"
            
            # Mock worktree GitOps instance
            mock_worktree_git_ops = Mock(spec=GitOps)
            mock_git_ops_class.return_value = mock_worktree_git_ops
            
            # Mock git operations with hunk application failure
            self.git_ops._run_git_command.side_effect = [
                (True, "worktree help with add command"),      # worktree support check
                (True, "stash created"),                       # stash push (backup)
                (True, "stash popped"),                        # stash pop (restore)
                (True, "stash dropped"),                       # stash drop (cleanup)
                (True, "worktree removed"),                    # worktree remove
            ]
            
            # Mock worktree operations with hunk apply failure
            mock_worktree_git_ops._run_git_command.side_effect = [
                (True, "current_hash_123"),                    # hash-object
                (True, "head_hash_456"),                       # rev-parse HEAD:file
                (True, "100644 blob_hash 0\\ttest.py"),        # ls-files --stage
            ]
            
            # Mock hunk application failure
            mock_worktree_git_ops._run_git_command_with_input.return_value = (False, "patch does not apply")

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is False
            
            # Should restore from stash after failure
            self.git_ops._run_git_command.assert_any_call("stash", "pop", "stash@{0}")

    def test_change_extraction_failure_with_restore(self):
        """Test handling of change extraction failure with restore."""
        hunk = DiffHunk(
            file_path="test.py", 
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        with patch('tempfile.mkdtemp'), \
             patch.object(self.handler, '_create_temporary_worktree') as mock_create_wt, \
             patch('git_autosquash.git_worktree_handler.GitOps') as mock_git_ops_class:

            mock_create_wt.return_value = "/tmp/test-worktree-extract-fail"
            
            # Mock worktree GitOps instance
            mock_worktree_git_ops = Mock(spec=GitOps)
            mock_git_ops_class.return_value = mock_worktree_git_ops
            
            # Mock git operations
            self.git_ops._run_git_command.side_effect = [
                (True, "worktree help with add command"),      # worktree support check
                (True, "stash created"),                       # stash push (backup)
                (True, "stash popped"),                        # stash pop (restore)
                (True, "stash dropped"),                       # stash drop (cleanup)
                (True, "worktree removed"),                    # worktree remove
            ]
            
            # Mock successful hunk application but extraction failure
            mock_worktree_git_ops._run_git_command.side_effect = [
                (True, "current_hash_123"),                    # hash-object
                (True, "head_hash_456"),                       # rev-parse HEAD:file
                (True, "100644 blob_hash 0\\ttest.py"),        # ls-files --stage
                (False, "diff command failed"),                # diff HEAD (extraction fails)
            ]
            
            mock_worktree_git_ops._run_git_command_with_input.return_value = (True, "")  # apply hunk

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is False
            
            # Should restore from stash after extraction failure
            self.git_ops._run_git_command.assert_any_call("stash", "pop", "stash@{0}")

    def test_path_validation_security(self):
        """Test path validation prevents security issues."""
        # Create hunk with absolute path (security issue)
        hunk_absolute = DiffHunk(
            file_path="/etc/passwd",
            old_start=1, old_count=1, new_start=1, new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-root:x:0:0:root", "+root:x:0:0:hacked"],
            context_before=[], context_after=[]
        )
        mapping_absolute = HunkTargetMapping(
            hunk=hunk_absolute, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock worktree support
        self.git_ops._run_git_command.return_value = (True, "worktree help with add command")

        result = self.handler.apply_ignored_hunks([mapping_absolute])

        assert result is False
        # Should only check worktree support and create stash before failing validation
        calls = [call[0] for call in self.git_ops._run_git_command.call_args_list]
        assert ("worktree", "--help") in calls
        assert ("stash", "push", "--include-untracked", "--message", "git-autosquash-worktree-backup") in calls

    def test_path_traversal_protection(self):
        """Test path traversal attack protection."""
        # Create hunk with path traversal (security issue)
        hunk_traversal = DiffHunk(
            file_path="../../../etc/passwd",
            old_start=1, old_count=1, new_start=1, new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-safe content", "+malicious content"],
            context_before=[], context_after=[]
        )
        mapping_traversal = HunkTargetMapping(
            hunk=hunk_traversal, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock worktree support and stash
        self.git_ops._run_git_command.side_effect = [
            (True, "worktree help with add command"),  # worktree support check
            (True, "stash created"),                   # stash push
            (True, "stash dropped"),                   # stash drop (cleanup)
        ]

        result = self.handler.apply_ignored_hunks([mapping_traversal])

        assert result is False

    def test_worktree_cleanup_with_fallback(self):
        """Test worktree cleanup with manual fallback."""
        worktree_path = "/tmp/test-worktree-cleanup"
        
        # Mock worktree remove failure, triggering manual cleanup
        self.git_ops._run_git_command.return_value = (False, "worktree remove failed")
        
        # Mock the manual cleanup method instead of shutil directly
        with patch.object(self.handler, '_manual_worktree_cleanup') as mock_manual_cleanup:
            
            self.handler._cleanup_worktree(worktree_path)
            
            # Should attempt git worktree remove first
            self.git_ops._run_git_command.assert_called_with(
                "worktree", "remove", "--force", worktree_path
            )
            
            # Should call manual cleanup as fallback
            mock_manual_cleanup.assert_called_once_with(worktree_path)
    
    def test_manual_worktree_cleanup_graceful_handling(self):
        """Test that manual cleanup handles exceptions gracefully."""
        # Test that the method doesn't raise exceptions
        try:
            self.handler._manual_worktree_cleanup("")  # Empty path
            self.handler._manual_worktree_cleanup("/nonexistent/path")  # Nonexistent path
            # Should complete without throwing exceptions
        except Exception as e:
            pytest.fail(f"Manual cleanup should handle exceptions gracefully, but raised: {e}")

    def test_empty_worktree_changes_handling(self):
        """Test handling when worktree has no changes to extract."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[], context_after=[]
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        with patch('tempfile.mkdtemp'), \
             patch.object(self.handler, '_create_temporary_worktree') as mock_create_wt, \
             patch('git_autosquash.git_worktree_handler.GitOps') as mock_git_ops_class:

            mock_create_wt.return_value = "/tmp/test-worktree-empty"
            
            # Mock worktree GitOps instance
            mock_worktree_git_ops = Mock(spec=GitOps)
            mock_git_ops_class.return_value = mock_worktree_git_ops
            
            # Mock git operations
            self.git_ops._run_git_command.side_effect = [
                (True, "worktree help with add command"),      # worktree support check
                (True, "stash created"),                       # stash push (backup)
                (True, "stash dropped"),                       # stash drop (cleanup)
                (True, "worktree removed"),                    # worktree remove
            ]
            
            # Mock successful hunk application but no changes to extract
            mock_worktree_git_ops._run_git_command.side_effect = [
                (True, "current_hash_123"),                    # hash-object
                (True, "head_hash_456"),                       # rev-parse HEAD:file
                (True, "100644 blob_hash 0\\ttest.py"),        # ls-files --stage
                (True, ""),                                    # diff HEAD (empty diff)
            ]
            
            mock_worktree_git_ops._run_git_command_with_input.return_value = (True, "")  # apply hunk

            result = self.handler.apply_ignored_hunks([mapping])

            assert result is True  # Should succeed even with no changes to extract

    def test_blob_info_retrieval_with_fallback(self):
        """Test blob info retrieval with fallback values."""
        # Test with mock GitOps instance
        mock_git_ops = Mock(spec=GitOps)
        
        # Mock partial success (some commands fail)
        mock_git_ops._run_git_command.side_effect = [
            (True, "current_hash_abc"),                        # hash-object (success)
            (False, "file not in HEAD"),                       # rev-parse HEAD:file (fails)
            (False, "file not staged"),                        # ls-files --stage (fails)
        ]
        
        blob_info = self.handler._get_file_blob_info("test.py", mock_git_ops)
        
        # Should use fallback values when ls-files fails (even if hash-object succeeds)
        assert blob_info['new_hash'] == "1" * 40   # fallback
        assert blob_info['old_hash'] == "0" * 40   # fallback
        assert blob_info['mode'] == "100644"       # fallback


class TestGitWorktreeHandlerIntegration:
    """Integration tests for git worktree handler."""

    def test_handler_can_be_imported_and_used(self):
        """Test that the handler can be imported and basic usage works."""
        from git_autosquash.git_worktree_handler import GitWorktreeIgnoreHandler
        
        git_ops = Mock(spec=GitOps)
        git_ops.repo_path = "/test/repo"
        
        handler = GitWorktreeIgnoreHandler(git_ops)
        
        # Test with empty mappings (should not require any git operations)
        result = handler.apply_ignored_hunks([])
        assert result is True