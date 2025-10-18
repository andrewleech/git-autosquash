"""Tests for SourceNormalizer class."""

import pytest
from unittest.mock import Mock, MagicMock
from git_autosquash.source_normalizer import SourceNormalizer, SourceNormalizationError
from git_autosquash.git_ops import GitOps


class TestSourceNormalizer:
    """Test SourceNormalizer functionality."""

    @pytest.fixture
    def mock_git_ops(self):
        """Create mock GitOps instance."""
        mock = Mock(spec=GitOps)
        return mock

    @pytest.fixture
    def normalizer(self, mock_git_ops):
        """Create SourceNormalizer instance with mock GitOps."""
        return SourceNormalizer(mock_git_ops)

    def test_normalize_working_tree_with_changes(self, normalizer, mock_git_ops):
        """Test normalizing working tree to commit with changes."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git add -A
            MagicMock(returncode=0, stdout="", stderr=""),
            # git diff --cached --quiet (returns 1 = has changes)
            MagicMock(returncode=1, stdout="", stderr=""),
            # git rev-parse HEAD (get parent before commit)
            MagicMock(returncode=0, stdout="parent123\n", stderr=""),
            # git commit --no-verify
            MagicMock(returncode=0, stdout="", stderr=""),
            # git rev-parse HEAD (get new commit hash)
            MagicMock(returncode=0, stdout="abc123def456\n", stderr=""),
        ]

        commit_hash = normalizer.normalize_to_commit("working-tree")

        assert commit_hash == "abc123def456"
        assert normalizer.temp_commit_created is True
        assert normalizer.starting_commit == "abc123def456"
        assert normalizer.parent_commit == "parent123"

        # Verify git commands were called correctly
        assert mock_git_ops.run_git_command.call_count == 5
        mock_git_ops.run_git_command.assert_any_call(["add", "-A"])
        mock_git_ops.run_git_command.assert_any_call(["diff", "--cached", "--quiet"])
        mock_git_ops.run_git_command.assert_any_call(
            [
                "commit",
                "--no-verify",
                "-m",
                "TEMP: git-autosquash working tree snapshot",
            ]
        )

    def test_normalize_working_tree_no_changes(self, normalizer, mock_git_ops):
        """Test normalizing working tree falls back to HEAD when no changes."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git add -A
            MagicMock(returncode=0, stdout="", stderr=""),
            # git diff --cached --quiet (returns 0 = no changes)
            MagicMock(returncode=0, stdout="", stderr=""),
            # git reset HEAD (unstage files)
            MagicMock(returncode=0, stdout="", stderr=""),
            # git rev-parse HEAD
            MagicMock(returncode=0, stdout="abc123def456\n", stderr=""),
        ]

        commit_hash = normalizer.normalize_to_commit("working-tree")

        assert commit_hash == "abc123def456"
        assert normalizer.temp_commit_created is False
        assert normalizer.starting_commit == "abc123def456"

    def test_normalize_index_with_staged(self, normalizer, mock_git_ops):
        """Test normalizing index to commit with staged changes."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git diff --cached --quiet (returns 1 = has staged changes)
            MagicMock(returncode=1, stdout="", stderr=""),
            # git rev-parse HEAD (get parent before commit)
            MagicMock(returncode=0, stdout="parent456\n", stderr=""),
            # git commit --no-verify
            MagicMock(returncode=0, stdout="", stderr=""),
            # git rev-parse HEAD (get new commit hash)
            MagicMock(returncode=0, stdout="def456abc123\n", stderr=""),
        ]

        commit_hash = normalizer.normalize_to_commit("index")

        assert commit_hash == "def456abc123"
        assert normalizer.temp_commit_created is True
        assert normalizer.starting_commit == "def456abc123"
        assert normalizer.parent_commit == "parent456"

        # Verify git commands
        mock_git_ops.run_git_command.assert_any_call(["diff", "--cached", "--quiet"])
        mock_git_ops.run_git_command.assert_any_call(
            ["commit", "--no-verify", "-m", "TEMP: git-autosquash index snapshot"]
        )

    def test_normalize_index_no_staged(self, normalizer, mock_git_ops):
        """Test normalizing index falls back to HEAD when no staged changes."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git diff --cached --quiet (returns 0 = no staged changes)
            MagicMock(returncode=0, stdout="", stderr=""),
            # git rev-parse HEAD
            MagicMock(returncode=0, stdout="abc123def456\n", stderr=""),
        ]

        commit_hash = normalizer.normalize_to_commit("index")

        assert commit_hash == "abc123def456"
        assert normalizer.temp_commit_created is False

    def test_normalize_head(self, normalizer, mock_git_ops):
        """Test normalizing HEAD (no temp commit)."""
        # Mock git operations
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="1234567890abcdef\n", stderr=""
        )

        commit_hash = normalizer.normalize_to_commit("HEAD")

        assert commit_hash == "1234567890abcdef"
        assert normalizer.temp_commit_created is False
        assert normalizer.starting_commit == "1234567890abcdef"

        # Verify only rev-parse was called
        mock_git_ops.run_git_command.assert_called_once_with(["rev-parse", "HEAD"])

    def test_normalize_head_lowercase(self, normalizer, mock_git_ops):
        """Test normalizing 'head' (lowercase)."""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="1234567890abcdef\n", stderr=""
        )

        commit_hash = normalizer.normalize_to_commit("head")

        assert commit_hash == "1234567890abcdef"
        assert normalizer.temp_commit_created is False

    def test_normalize_commit_sha(self, normalizer, mock_git_ops):
        """Test normalizing specific commit SHA."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git rev-parse abc123
            MagicMock(returncode=0, stdout="abc123def456789\n", stderr=""),
            # git cat-file -t abc123def456789
            MagicMock(returncode=0, stdout="commit\n", stderr=""),
        ]

        commit_hash = normalizer.normalize_to_commit("abc123")

        assert commit_hash == "abc123def456789"
        assert normalizer.temp_commit_created is False
        assert normalizer.starting_commit == "abc123def456789"

        # Verify validation calls
        assert mock_git_ops.run_git_command.call_count == 2

    def test_normalize_commit_reference(self, normalizer, mock_git_ops):
        """Test normalizing commit reference like HEAD~1."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git rev-parse HEAD~1
            MagicMock(returncode=0, stdout="parent123456\n", stderr=""),
            # git cat-file -t parent123456
            MagicMock(returncode=0, stdout="commit\n", stderr=""),
        ]

        commit_hash = normalizer.normalize_to_commit("HEAD~1")

        assert commit_hash == "parent123456"
        assert normalizer.temp_commit_created is False

    def test_normalize_auto_clean(self, normalizer, mock_git_ops):
        """Test auto-detect with clean working tree."""
        # Mock status and git operations
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": True,
            "has_staged": False,
            "has_unstaged": False,
        }
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="clean123456\n", stderr=""
        )

        commit_hash = normalizer.normalize_to_commit("auto")

        assert commit_hash == "clean123456"
        assert normalizer.temp_commit_created is False

    def test_normalize_auto_staged_only(self, normalizer, mock_git_ops):
        """Test auto-detect with staged changes only."""
        # Mock status and git operations
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": True,
            "has_unstaged": False,
        }
        mock_git_ops.run_git_command.side_effect = [
            # git diff --cached --quiet (has staged)
            MagicMock(returncode=1, stdout="", stderr=""),
            # git rev-parse HEAD (get parent)
            MagicMock(returncode=0, stdout="parent_staged\n", stderr=""),
            # git commit --no-verify
            MagicMock(returncode=0, stdout="", stderr=""),
            # git rev-parse HEAD (get new commit)
            MagicMock(returncode=0, stdout="staged123456\n", stderr=""),
        ]

        commit_hash = normalizer.normalize_to_commit("auto")

        assert commit_hash == "staged123456"
        assert normalizer.temp_commit_created is True

    def test_normalize_auto_unstaged_only(self, normalizer, mock_git_ops):
        """Test auto-detect with unstaged changes only."""
        # Mock status and git operations
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": False,
            "has_unstaged": True,
        }
        mock_git_ops.run_git_command.side_effect = [
            # git add -A
            MagicMock(returncode=0, stdout="", stderr=""),
            # git diff --cached --quiet (has changes after add)
            MagicMock(returncode=1, stdout="", stderr=""),
            # git rev-parse HEAD (get parent)
            MagicMock(returncode=0, stdout="parent_unstaged\n", stderr=""),
            # git commit --no-verify
            MagicMock(returncode=0, stdout="", stderr=""),
            # git rev-parse HEAD (get new commit)
            MagicMock(returncode=0, stdout="unstaged123456\n", stderr=""),
        ]

        commit_hash = normalizer.normalize_to_commit("auto")

        assert commit_hash == "unstaged123456"
        assert normalizer.temp_commit_created is True

    def test_normalize_auto_both_staged_and_unstaged(self, normalizer, mock_git_ops):
        """Test auto-detect with both staged and unstaged (commits index)."""
        # Mock status and git operations
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": True,
            "has_unstaged": True,
        }
        mock_git_ops.run_git_command.side_effect = [
            # git diff --cached --quiet (has staged)
            MagicMock(returncode=1, stdout="", stderr=""),
            # git rev-parse HEAD (get parent)
            MagicMock(returncode=0, stdout="parent_both\n", stderr=""),
            # git commit --no-verify
            MagicMock(returncode=0, stdout="", stderr=""),
            # git rev-parse HEAD (get new commit)
            MagicMock(returncode=0, stdout="both123456\n", stderr=""),
        ]

        commit_hash = normalizer.normalize_to_commit("auto")

        assert commit_hash == "both123456"
        assert normalizer.temp_commit_created is True

    def test_cleanup_temp_commit(self, normalizer, mock_git_ops):
        """Test cleanup removes temp commit."""
        # Setup: simulate temp commit was created
        normalizer.temp_commit_created = True
        normalizer.starting_commit = "temp123456"

        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        normalizer.cleanup_temp_commit()

        assert normalizer.temp_commit_created is False

        # Verify soft reset was called
        mock_git_ops.run_git_command.assert_called_once_with(
            ["reset", "--soft", "temp123456~1"]
        )

    def test_cleanup_temp_commit_no_temp(self, normalizer, mock_git_ops):
        """Test cleanup does nothing when no temp commit."""
        normalizer.temp_commit_created = False
        normalizer.starting_commit = "abc123"

        normalizer.cleanup_temp_commit()

        # Verify no git commands called
        mock_git_ops.run_git_command.assert_not_called()

    def test_cleanup_temp_commit_failure(self, normalizer, mock_git_ops):
        """Test cleanup handles failure gracefully."""
        # Setup: simulate temp commit was created
        normalizer.temp_commit_created = True
        normalizer.starting_commit = "temp123456"

        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=1, stdout="", stderr="reset failed"
        )

        # Should not raise exception
        normalizer.cleanup_temp_commit()

        # temp_commit_created should remain True (cleanup failed)
        assert normalizer.temp_commit_created is True

    def test_normalize_invalid_commit(self, normalizer, mock_git_ops):
        """Test error handling for invalid commit reference."""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=1, stdout="", stderr="fatal: Not a valid object name"
        )

        with pytest.raises(SourceNormalizationError) as exc_info:
            normalizer.normalize_to_commit("invalid_ref")

        assert "Failed to normalize source 'invalid_ref'" in str(exc_info.value)

    def test_normalize_not_a_commit(self, normalizer, mock_git_ops):
        """Test error handling when reference is not a commit."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git rev-parse returns a tree object
            MagicMock(returncode=0, stdout="tree123456\n", stderr=""),
            # git cat-file -t returns "tree" not "commit"
            MagicMock(returncode=0, stdout="tree\n", stderr=""),
        ]

        with pytest.raises(SourceNormalizationError) as exc_info:
            normalizer.normalize_to_commit("tree123456")

        assert "Not a valid commit" in str(exc_info.value)

    def test_normalize_commit_failure(self, normalizer, mock_git_ops):
        """Test error handling when commit creation fails."""
        # Mock git operations
        mock_git_ops.run_git_command.side_effect = [
            # git add -A succeeds
            MagicMock(returncode=0, stdout="", stderr=""),
            # git diff --cached --quiet (has changes)
            MagicMock(returncode=1, stdout="", stderr=""),
            # git rev-parse HEAD (get parent)
            MagicMock(returncode=0, stdout="parent_fail\n", stderr=""),
            # git commit --no-verify fails
            MagicMock(returncode=1, stdout="", stderr="commit failed"),
            # git reset HEAD (cleanup on failure)
            MagicMock(returncode=0, stdout="", stderr=""),
        ]

        with pytest.raises(SourceNormalizationError) as exc_info:
            normalizer.normalize_to_commit("working-tree")

        assert "Failed to create temp commit" in str(exc_info.value)

    def test_normalize_detached_head(self, normalizer, mock_git_ops):
        """Test error handling for detached HEAD state."""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=1, stdout="", stderr="fatal: ref HEAD is not a symbolic ref"
        )

        with pytest.raises(SourceNormalizationError) as exc_info:
            normalizer.normalize_to_commit("HEAD")

        assert "Failed to get HEAD hash" in str(exc_info.value)

    def test_normalize_stage_failure(self, normalizer, mock_git_ops):
        """Test error handling when staging fails."""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=1, stdout="", stderr="fatal: unable to stage files"
        )

        with pytest.raises(SourceNormalizationError) as exc_info:
            normalizer.normalize_to_commit("working-tree")

        assert "Failed to stage changes" in str(exc_info.value)

    def test_starting_commit_attribute(self, normalizer, mock_git_ops):
        """Test that starting_commit attribute is set correctly."""
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="commit123456\n", stderr=""
        )

        commit_hash = normalizer.normalize_to_commit("HEAD")

        assert normalizer.starting_commit == commit_hash
        assert normalizer.starting_commit == "commit123456"

    def test_temp_commit_created_flag(self, normalizer, mock_git_ops):
        """Test temp_commit_created flag is set correctly."""
        # Test HEAD (no temp commit)
        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="head123\n", stderr=""
        )

        normalizer.normalize_to_commit("HEAD")
        assert normalizer.temp_commit_created is False

        # Reset and test working-tree (temp commit)
        normalizer = SourceNormalizer(mock_git_ops)
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # add
            MagicMock(returncode=1, stdout="", stderr=""),  # diff (has changes)
            MagicMock(
                returncode=0, stdout="parent_temp\n", stderr=""
            ),  # rev-parse (parent)
            MagicMock(returncode=0, stdout="", stderr=""),  # commit
            MagicMock(
                returncode=0, stdout="temp123\n", stderr=""
            ),  # rev-parse (new commit)
        ]

        normalizer.normalize_to_commit("working-tree")
        assert normalizer.temp_commit_created is True

    def test_cleanup_idempotency(self, normalizer, mock_git_ops):
        """Test that calling cleanup multiple times is safe."""
        # Setup: simulate temp commit was created
        normalizer.temp_commit_created = True
        normalizer.starting_commit = "temp123456"
        normalizer.parent_commit = "parent123"

        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        # First cleanup should work
        normalizer.cleanup_temp_commit()
        assert normalizer.temp_commit_created is False
        assert normalizer.parent_commit is None
        assert mock_git_ops.run_git_command.call_count == 1

        # Second cleanup should do nothing (no error)
        normalizer.cleanup_temp_commit()
        # Should not call git again
        assert mock_git_ops.run_git_command.call_count == 1

    def test_cleanup_with_stored_parent(self, normalizer, mock_git_ops):
        """Test cleanup uses stored parent SHA instead of ~1 notation."""
        normalizer.temp_commit_created = True
        normalizer.starting_commit = "temp123456"
        normalizer.parent_commit = "parent_sha_789"

        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        normalizer.cleanup_temp_commit()

        # Should use stored parent, not ~1 notation
        mock_git_ops.run_git_command.assert_called_once_with(
            ["reset", "--soft", "parent_sha_789"]
        )

    def test_cleanup_fallback_to_tilde_notation(self, normalizer, mock_git_ops):
        """Test cleanup falls back to ~1 when parent not stored."""
        normalizer.temp_commit_created = True
        normalizer.starting_commit = "temp123456"
        normalizer.parent_commit = None  # No parent stored

        mock_git_ops.run_git_command.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        normalizer.cleanup_temp_commit()

        # Should fall back to ~1 notation with warning
        mock_git_ops.run_git_command.assert_called_once_with(
            ["reset", "--soft", "temp123456~1"]
        )

    def test_cleanup_with_no_commit_info(self, normalizer, mock_git_ops):
        """Test cleanup handles missing commit information gracefully."""
        normalizer.temp_commit_created = True
        normalizer.starting_commit = None  # No starting commit
        normalizer.parent_commit = None  # No parent

        normalizer.cleanup_temp_commit()

        # Should not call git at all
        mock_git_ops.run_git_command.assert_not_called()
        # Flag should remain true (couldn't cleanup)
        assert normalizer.temp_commit_created is True

    def test_working_tree_commit_index_reset_on_failure(self, normalizer, mock_git_ops):
        """Test that index is reset when working tree commit fails."""
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # add -A succeeds
            MagicMock(returncode=1, stdout="", stderr=""),  # diff (has changes)
            MagicMock(
                returncode=0, stdout="parent123\n", stderr=""
            ),  # rev-parse parent
            MagicMock(returncode=1, stdout="", stderr="commit blocked"),  # commit fails
            MagicMock(returncode=0, stdout="", stderr=""),  # reset HEAD (cleanup)
        ]

        with pytest.raises(SourceNormalizationError) as exc_info:
            normalizer.normalize_to_commit("working-tree")

        assert "Failed to create temp commit" in str(exc_info.value)
        assert "commit blocked" in str(exc_info.value)

        # Verify reset was called to cleanup
        assert mock_git_ops.run_git_command.call_count == 5
        last_call = mock_git_ops.run_git_command.call_args_list[-1]
        assert last_call[0][0] == ["reset", "HEAD"]

    def test_concurrent_modification_detection(self, normalizer, mock_git_ops):
        """Test behavior when files modified during normalization."""
        # Simulate scenario where HEAD changes between parent read and commit
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),  # add -A
            MagicMock(returncode=1, stdout="", stderr=""),  # diff (has changes)
            MagicMock(
                returncode=0, stdout="parent_old\n", stderr=""
            ),  # rev-parse parent
            MagicMock(returncode=0, stdout="", stderr=""),  # commit succeeds
            MagicMock(
                returncode=0, stdout="new_commit_123\n", stderr=""
            ),  # rev-parse new
        ]

        commit_hash = normalizer.normalize_to_commit("working-tree")

        # Should succeed with new commit
        assert commit_hash == "new_commit_123"
        assert normalizer.parent_commit == "parent_old"
        # Parent stored before concurrent modification
        assert normalizer.temp_commit_created is True

    def test_index_commit_index_preserved_on_failure(self, normalizer, mock_git_ops):
        """Test that index is preserved when index commit fails."""
        mock_git_ops.run_git_command.side_effect = [
            MagicMock(returncode=1, stdout="", stderr=""),  # diff (has staged)
            MagicMock(
                returncode=0, stdout="parent123\n", stderr=""
            ),  # rev-parse parent
            MagicMock(returncode=1, stdout="", stderr="hook rejected"),  # commit fails
        ]

        with pytest.raises(SourceNormalizationError) as exc_info:
            normalizer.normalize_to_commit("index")

        assert "Failed to create temp commit" in str(exc_info.value)
        assert "hook rejected" in str(exc_info.value)

        # Note: index mode doesn't reset on failure because staged changes
        # should remain staged for user to fix
        assert normalizer.temp_commit_created is False

    def test_error_messages_preserve_stderr(self, normalizer, mock_git_ops):
        """Test that all error messages preserve git stderr output."""
        test_cases = [
            (
                "HEAD",
                MagicMock(returncode=1, stdout="", stderr="detached HEAD error"),
                "Failed to get HEAD hash",
                "detached HEAD error",
            ),
            (
                "invalid_ref",
                MagicMock(returncode=1, stdout="", stderr="not a valid object"),
                "Invalid commit reference",
                None,
            ),  # Caught in wrapper
        ]

        for source, mock_return, expected_msg, expected_stderr in test_cases:
            normalizer = SourceNormalizer(mock_git_ops)
            mock_git_ops.run_git_command.return_value = mock_return

            with pytest.raises(SourceNormalizationError) as exc_info:
                normalizer.normalize_to_commit(source)

            error_msg = str(exc_info.value)
            assert expected_msg in error_msg
            if expected_stderr:
                assert expected_stderr in error_msg
