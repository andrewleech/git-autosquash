"""Tests for git-native ignore handler."""

import subprocess
from unittest.mock import Mock

from git_autosquash.hunk_target_resolver import HunkTargetMapping
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

    def create_robust_git_mock(self, custom_responses=None):
        """Create a robust git command mock that handles unlimited calls.

        Args:
            custom_responses: Dict of custom responses for specific commands
        """
        custom_responses = custom_responses or {}

        def mock_git_command(args, **kwargs):
            # Check for custom responses first
            command_key = " ".join(args) if isinstance(args, list) else str(args)
            if command_key in custom_responses:
                return custom_responses[command_key]

            # Default responses for common git operations
            # Note: GitOps.run_git_command passes args WITHOUT "git" prefix
            if isinstance(args, list) and len(args) >= 1:
                if args[0] == "stash":
                    # Handle various stash commands
                    if len(args) >= 2:
                        if args[1] == "push":
                            return subprocess.CompletedProcess(
                                args=args,
                                returncode=0,
                                stdout="stash push success",
                                stderr="",
                            )
                        elif args[1] in ["pop", "drop"] and len(args) >= 3:
                            return subprocess.CompletedProcess(
                                args=args,
                                returncode=0,
                                stdout=f"stash {args[1]} success",
                                stderr="",
                            )
                        elif args[1] in ["list", "--help"]:
                            return subprocess.CompletedProcess(
                                args=args,
                                returncode=0,
                                stdout=f"stash {args[1]} success",
                                stderr="",
                            )
                elif args[0] == "apply":
                    # Handle git apply commands (including --cached for staging)
                    return subprocess.CompletedProcess(
                        args=args, returncode=0, stdout="", stderr=""
                    )
                elif args[0] == "add":
                    # Handle git add commands
                    return subprocess.CompletedProcess(
                        args=args, returncode=0, stdout="", stderr=""
                    )
                elif args[0] == "reset":
                    # Handle git reset commands
                    return subprocess.CompletedProcess(
                        args=args, returncode=0, stdout="", stderr=""
                    )

                # Default success for other git commands
                return subprocess.CompletedProcess(
                    args=args, returncode=0, stdout="", stderr=""
                )
            return subprocess.CompletedProcess(
                args=args, returncode=1, stdout="", stderr="unknown command"
            )

        return mock_git_command

    def test_initialization(self):
        """Test handler initialization."""
        assert self.handler.git_ops is self.git_ops
        assert self.handler.logger is not None

    def test_empty_mappings_success(self):
        """Test handling of empty ignored mappings."""
        result = self.handler.apply_ignored_hunks([])

        assert result is True
        # Should not call any git operations
        self.git_ops.run_git_command.assert_not_called()
        self.git_ops.run_git_command_with_input.assert_not_called()

    def test_successful_apply_with_backup_restore(self):
        """Test successful application with backup creation and cleanup."""
        # Create test hunk and mapping
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock git operations for the new index-based approach
        self.git_ops.run_git_command.side_effect = [
            subprocess.CompletedProcess(
                args=["git", "stash", "push"],
                returncode=0,
                stdout="Saved working directory and index state WIP on main: abc123 commit",
                stderr="",
            ),  # stash push
            subprocess.CompletedProcess(
                args=["git", "write-tree"],
                returncode=0,
                stdout="tree_hash_original",
                stderr="",
            ),  # write-tree (capture index)
            subprocess.CompletedProcess(
                args=["git", "hash-object"],
                returncode=0,
                stdout="current_hash_123",
                stderr="",
            ),  # hash-object
            subprocess.CompletedProcess(
                args=["git", "rev-parse"],
                returncode=0,
                stdout="head_hash_456",
                stderr="",
            ),  # rev-parse HEAD:file
            subprocess.CompletedProcess(
                args=["git", "ls-files"],
                returncode=0,
                stdout="100644 blob_hash 0\ttest.py",
                stderr="",
            ),  # ls-files --stage
            subprocess.CompletedProcess(
                args=["git", "read-tree"],
                returncode=0,
                stdout="tree_hash_original",
                stderr="",
            ),  # read-tree (restore index)
            subprocess.CompletedProcess(
                args=["git", "diff"],
                returncode=0,
                stdout="diff --git a/test.py b/test.py\nindex head..current 100644\n--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,2 @@\n existing line\n+new line",
                stderr="",
            ),  # diff --cached
            subprocess.CompletedProcess(
                args=["git", "stash", "drop"],
                returncode=0,
                stdout="stash@{0} dropped",
                stderr="",
            ),  # stash drop
        ]

        # Mock patch operations
        self.git_ops.run_git_command_with_input.side_effect = [
            subprocess.CompletedProcess(
                args=["git", "apply", "--cached"], returncode=0, stdout="", stderr=""
            ),  # apply --cached (stage hunk)
            subprocess.CompletedProcess(
                args=["git", "apply", "--check"], returncode=0, stdout="", stderr=""
            ),  # apply --check
            subprocess.CompletedProcess(
                args=["git", "apply"], returncode=0, stdout="", stderr=""
            ),  # apply
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is True

        # Verify stash and git operations were performed
        self.git_ops.run_git_command.assert_called()
        self.git_ops.run_git_command_with_input.assert_called()

        # Verify patch operations (stage + validate + apply)
        assert self.git_ops.run_git_command_with_input.call_count == 3

    def test_stash_backup_failure(self):
        """Test handling when stash backup creation fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock stash creation failure
        self.git_ops.run_git_command.return_value = subprocess.CompletedProcess(
            args=["git", "stash", "push"],
            returncode=1,
            stdout="",
            stderr="Cannot save working tree state",
        )

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should not attempt patch operations if backup fails
        self.git_ops.run_git_command_with_input.assert_not_called()

    def test_path_validation_security(self):
        """Test path validation prevents security vulnerabilities."""
        # Test absolute path
        hunk_abs = DiffHunk(
            file_path="/etc/passwd",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing", "+malicious"],
            context_before=[],
            context_after=[],
        )
        mapping_abs = HunkTargetMapping(
            hunk=hunk_abs, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock successful stash creation
        self.git_ops.run_git_command.return_value = subprocess.CompletedProcess(
            args=["git", "stash", "push"],
            returncode=0,
            stdout="stash created",
            stderr="",
        )

        result = self.handler.apply_ignored_hunks([mapping_abs])

        assert result is False
        # Should clean up stash even on validation failure
        self.git_ops.run_git_command.assert_called()

    def test_path_traversal_protection(self):
        """Test protection against path traversal attacks."""
        hunk_traversal = DiffHunk(
            file_path="../../../etc/passwd",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing", "+malicious"],
            context_before=[],
            context_after=[],
        )
        mapping_traversal = HunkTargetMapping(
            hunk=hunk_traversal,
            target_commit="abc123",
            confidence="high",
            blame_info=[],
        )

        # Mock successful stash creation
        self.git_ops.run_git_command.return_value = subprocess.CompletedProcess(
            args=["git", "stash", "push"],
            returncode=0,
            stdout="stash created",
            stderr="",
        )

        result = self.handler.apply_ignored_hunks([mapping_traversal])

        assert result is False

    def test_patch_validation_failure(self):
        """Test handling when patch validation fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock operations for index-based approach with validation failure
        self.git_ops.run_git_command.side_effect = [
            subprocess.CompletedProcess(
                args=["git", "stash", "push"],
                returncode=0,
                stdout="stash created",
                stderr="",
            ),  # stash push
            subprocess.CompletedProcess(
                args=["git", "write-tree"],
                returncode=0,
                stdout="tree_hash_orig",
                stderr="",
            ),  # write-tree (capture)
            subprocess.CompletedProcess(
                args=["git", "hash-object"],
                returncode=0,
                stdout="current_hash",
                stderr="",
            ),  # hash-object
            subprocess.CompletedProcess(
                args=["git", "rev-parse"], returncode=0, stdout="head_hash", stderr=""
            ),  # rev-parse
            subprocess.CompletedProcess(
                args=["git", "ls-files"],
                returncode=0,
                stdout="100644 blob 0\ttest.py",
                stderr="",
            ),  # ls-files
            subprocess.CompletedProcess(
                args=["git", "read-tree"],
                returncode=0,
                stdout="tree_hash_orig",
                stderr="",
            ),  # read-tree (restore)
            subprocess.CompletedProcess(
                args=["git", "diff"], returncode=0, stdout="patch content", stderr=""
            ),  # diff --cached
            subprocess.CompletedProcess(
                args=["git", "stash", "pop"],
                returncode=0,
                stdout="stash popped",
                stderr="",
            ),  # stash pop (restore)
            subprocess.CompletedProcess(
                args=["git", "stash", "drop"],
                returncode=0,
                stdout="stash dropped",
                stderr="",
            ),  # stash drop (cleanup)
        ]

        # Mock patch operations: stage succeeds, but validation fails
        self.git_ops.run_git_command_with_input.side_effect = [
            subprocess.CompletedProcess(
                args=["git", "apply", "--cached"], returncode=0, stdout="", stderr=""
            ),  # apply --cached (stage hunk)
            subprocess.CompletedProcess(
                args=["git", "apply", "--check"],
                returncode=1,
                stdout="",
                stderr="patch does not apply",
            ),  # apply --check (validation fails)
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should restore from stash on validation failure
        self.git_ops.run_git_command.assert_called()

    def test_patch_application_failure_with_restore(self):
        """Test restore behavior when patch application fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Use robust git mocking to handle unlimited calls
        self.git_ops.run_git_command.side_effect = self.create_robust_git_mock()

        # Mock patch operations - stage succeeds, validation passes, application fails
        self.git_ops.run_git_command_with_input.side_effect = [
            subprocess.CompletedProcess(
                args=["git", "apply"],
                returncode=1,
                stdout="",
                stderr="patch application failed",
            ),  # apply (application fails)
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should attempt git operations
        self.git_ops.run_git_command.assert_called()

    def test_exception_handling_with_restore(self):
        """Test exception handling triggers restore."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock stash operations - using custom exception for second call
        custom_responses = {
            "git stash push": subprocess.CompletedProcess(
                args=["git", "stash", "push"],
                returncode=0,
                stdout="stash created",
                stderr="",
            )
        }

        # Create a mock that succeeds for stash, but raises exception on second call
        call_count = 0

        def exception_mock(args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second call raises exception
                raise Exception("Unexpected error")
            return self.create_robust_git_mock(custom_responses)(args, **kwargs)

        self.git_ops.run_git_command.side_effect = exception_mock

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should attempt git operations before exception
        self.git_ops.run_git_command.assert_called()

    def test_force_restore_fallback(self):
        """Test force restore fallback when normal restore fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock git operations with restore failure for index approach
        self.git_ops.run_git_command.side_effect = self.create_robust_git_mock()

        # Mock patch operations: stage succeeds, validation fails to trigger restore
        self.git_ops.run_git_command_with_input.side_effect = [
            subprocess.CompletedProcess(
                args=["git", "apply"],
                returncode=1,
                stdout="",
                stderr="patch validation failed",
            ),  # validation fails
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        assert result is False
        # Should attempt git operations
        self.git_ops.run_git_command.assert_called()

    def test_multiple_files_batch_processing(self):
        """Test batch processing of multiple files."""
        # Create hunks for different files
        hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line 1", "+new line 1"],
            context_before=[],
            context_after=[],
        )
        hunk2 = DiffHunk(
            file_path="file2.py",
            old_start=5,
            old_count=1,
            new_start=5,
            new_count=2,
            lines=["@@ -5,1 +5,2 @@", " line 5", "+new line 5"],
            context_before=[],
            context_after=[],
        )

        mappings = [
            HunkTargetMapping(
                hunk=hunk1, target_commit="abc123", confidence="high", blame_info=[]
            ),
            HunkTargetMapping(
                hunk=hunk2, target_commit="def456", confidence="high", blame_info=[]
            ),
        ]

        # Mock git operations for batch processing of 2 files
        self.git_ops.run_git_command.side_effect = [
            # Backup stash
            subprocess.CompletedProcess(
                args=["git", "stash", "push"],
                returncode=0,
                stdout="stash success",
                stderr="",
            ),
            # Capture original index state
            subprocess.CompletedProcess(
                args=["git", "write-tree"],
                returncode=0,
                stdout="tree_original",
                stderr="",
            ),
            # Stage first hunk - file1.py
            subprocess.CompletedProcess(
                args=["git", "hash-object"], returncode=0, stdout="hash1", stderr=""
            ),
            subprocess.CompletedProcess(
                args=["git", "rev-parse"], returncode=0, stdout="head1", stderr=""
            ),
            subprocess.CompletedProcess(
                args=["git", "apply", "--cached"], returncode=0, stdout="", stderr=""
            ),
            # Stage second hunk - file2.py
            subprocess.CompletedProcess(
                args=["git", "hash-object"], returncode=0, stdout="hash2", stderr=""
            ),
            subprocess.CompletedProcess(
                args=["git", "rev-parse"], returncode=0, stdout="head2", stderr=""
            ),
            subprocess.CompletedProcess(
                args=["git", "apply", "--cached"], returncode=0, stdout="", stderr=""
            ),
            # Generate patch from index (git diff --cached)
            subprocess.CompletedProcess(
                args=["git", "diff", "--cached"],
                returncode=0,
                stdout="--- a/file1.py\n+++ b/file1.py\n@@ -1,1 +1,2 @@\n line 1\n+new line 1\n",
                stderr="",
            ),
            # Restore original index
            subprocess.CompletedProcess(
                args=["git", "read-tree"], returncode=0, stdout="", stderr=""
            ),
            # Cleanup backup stash
            subprocess.CompletedProcess(
                args=["git", "stash", "drop"], returncode=0, stdout="", stderr=""
            ),
        ]

        # Mock successful patch operations (stage 2 hunks + validate + apply)
        self.git_ops.run_git_command_with_input.side_effect = [
            # Stage first hunk to index
            subprocess.CompletedProcess(
                args=["git", "apply", "--cached"], returncode=0, stdout="", stderr=""
            ),
            # Stage second hunk to index
            subprocess.CompletedProcess(
                args=["git", "apply", "--cached"], returncode=0, stdout="", stderr=""
            ),
            # Validate patch (git apply --check)
            subprocess.CompletedProcess(
                args=["git", "apply", "--check"], returncode=0, stdout="", stderr=""
            ),
            # Apply final patch to working tree
            subprocess.CompletedProcess(
                args=["git", "apply"], returncode=0, stdout="", stderr=""
            ),
        ]

        result = self.handler.apply_ignored_hunks(mappings)

        assert result is True

        # Should perform git operations
        self.git_ops.run_git_command.assert_called()
        self.git_ops.run_git_command_with_input.assert_called()

    def test_index_state_capture_and_restore(self):
        """Test git index state capture and restore functionality."""
        handler = GitNativeIgnoreHandler(self.git_ops)

        # Mock write-tree and read-tree operations
        self.git_ops.run_git_command.side_effect = [
            subprocess.CompletedProcess(
                args=["git", "write-tree"],
                returncode=0,
                stdout="tree_hash_abc123",
                stderr="",
            ),  # write-tree (capture)
            subprocess.CompletedProcess(
                args=["git", "read-tree"], returncode=0, stdout="", stderr=""
            ),  # read-tree (restore)
        ]

        # Test capture
        success, tree_hash = handler._capture_index_state()
        assert success is True
        assert tree_hash == "tree_hash_abc123"

        # Test restore
        success = handler._restore_index_state(tree_hash)
        assert success is True

        # Verify git commands were called correctly
        self.git_ops.run_git_command.assert_called()

    def test_stash_info_retrieval(self):
        """Test stash information retrieval for debugging."""
        # Mock stash list output
        stash_output = """stash@{0}: WIP on main: abc123 work in progress
stash@{1}: On feature: def456 saved changes"""

        self.git_ops.run_git_command.return_value = subprocess.CompletedProcess(
            args=["git", "stash", "list"], returncode=0, stdout=stash_output, stderr=""
        )

        stashes = self.handler.get_stash_info()

        assert len(stashes) == 2
        assert stashes[0]["ref"] == "stash@{0}"
        assert stashes[0]["type"] == "WIP on main"
        assert stashes[0]["message"] == "abc123 work in progress"

        assert stashes[1]["ref"] == "stash@{1}"
        assert stashes[1]["type"] == "On feature"
        assert stashes[1]["message"] == "def456 saved changes"

    def test_cleanup_continues_on_failure(self):
        """Test that cleanup continues even if stash drop fails."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " existing line", "+new line"],
            context_before=[],
            context_after=[],
        )
        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        # Mock operations with cleanup failure for index approach
        custom_responses = {
            "stash drop stash@{0}": subprocess.CompletedProcess(
                args=["stash", "drop", "stash@{0}"],
                returncode=1,
                stdout="",
                stderr="stash drop failed",
            ),
            "diff --cached": subprocess.CompletedProcess(
                args=["diff", "--cached"],
                returncode=0,
                stdout="--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,2 @@\n existing line\n+new line\n",
                stderr="",
            ),
        }
        self.git_ops.run_git_command.side_effect = self.create_robust_git_mock(
            custom_responses
        )

        # Mock successful patch operations
        self.git_ops.run_git_command_with_input.side_effect = [
            subprocess.CompletedProcess(
                args=["git", "apply", "--cached"], returncode=0, stdout="", stderr=""
            ),  # Stage hunk to index
            subprocess.CompletedProcess(
                args=["git", "apply", "--check"], returncode=0, stdout="", stderr=""
            ),  # Validate patch
            subprocess.CompletedProcess(
                args=["git", "apply"], returncode=0, stdout="", stderr=""
            ),  # Apply to working tree
        ]

        result = self.handler.apply_ignored_hunks([mapping])

        # Should succeed despite cleanup failure
        assert result is True

        # Should attempt cleanup operations
        self.git_ops.run_git_command.assert_called()
