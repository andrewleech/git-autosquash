"""Tests for SquashContext abstraction."""

import pytest
from unittest.mock import Mock

from git_autosquash.squash_context import SquashContext
from git_autosquash.git_ops import GitOps


class TestSquashContextCreation:
    """Test SquashContext creation and initialization."""

    def test_direct_instantiation(self):
        """Test creating SquashContext directly."""
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        assert context.blame_ref == "HEAD"
        assert context.source_commit is None
        assert context.is_historical_commit is False
        assert context.working_tree_clean is True

    def test_immutability(self):
        """Test that SquashContext is immutable."""
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        # Should not be able to modify attributes
        with pytest.raises(AttributeError):
            context.blame_ref = "HEAD~1"  # type: ignore

        with pytest.raises(AttributeError):
            context.source_commit = "abc123"  # type: ignore


class TestFromSourceFactory:
    """Test SquashContext.from_source() factory method."""

    @pytest.fixture
    def mock_git_ops(self):
        """Mock GitOps for testing."""
        mock = Mock(spec=GitOps)
        return mock

    def test_from_source_head(self, mock_git_ops):
        """Test creating context from --source HEAD."""
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": True,
            "has_staged": False,
            "has_unstaged": False,
        }

        context = SquashContext.from_source("HEAD", mock_git_ops)

        assert context.blame_ref == "HEAD~1"
        assert context.source_commit is None
        assert context.is_historical_commit is False
        assert context.working_tree_clean is True

    def test_from_source_head_lowercase(self, mock_git_ops):
        """Test creating context from --source head (lowercase)."""
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": True,
            "has_staged": False,
            "has_unstaged": False,
        }

        context = SquashContext.from_source("head", mock_git_ops)

        assert context.blame_ref == "HEAD~1"
        assert context.source_commit is None
        assert context.is_historical_commit is False

    def test_from_source_commit_sha(self, mock_git_ops):
        """Test creating context from --source <commit-sha>."""
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": True,
            "has_staged": False,
            "has_unstaged": False,
        }

        commit_sha = "abc123def456"
        context = SquashContext.from_source(commit_sha, mock_git_ops)

        assert context.blame_ref == f"{commit_sha}~1"
        assert context.source_commit == commit_sha
        assert context.is_historical_commit is True
        assert context.working_tree_clean is True

    def test_from_source_auto(self, mock_git_ops):
        """Test creating context from --source auto."""
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": True,
            "has_unstaged": False,
        }

        context = SquashContext.from_source("auto", mock_git_ops)

        assert context.blame_ref == "HEAD"
        assert context.source_commit is None
        assert context.is_historical_commit is False
        assert context.working_tree_clean is False

    def test_from_source_working_tree(self, mock_git_ops):
        """Test creating context from --source working-tree."""
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": False,
            "has_unstaged": True,
        }

        context = SquashContext.from_source("working-tree", mock_git_ops)

        assert context.blame_ref == "HEAD"
        assert context.source_commit is None
        assert context.is_historical_commit is False
        assert context.working_tree_clean is False

    def test_from_source_index(self, mock_git_ops):
        """Test creating context from --source index."""
        mock_git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": True,
            "has_unstaged": False,
        }

        context = SquashContext.from_source("index", mock_git_ops)

        assert context.blame_ref == "HEAD"
        assert context.source_commit is None
        assert context.is_historical_commit is False


class TestNormalizedBlameRef:
    """Test normalized_blame_ref property."""

    def test_normalized_blame_ref_uppercase(self):
        """Test that blame_ref is normalized to uppercase."""
        context = SquashContext(
            blame_ref="head",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        assert context.normalized_blame_ref == "HEAD"

    def test_normalized_blame_ref_with_tilde(self):
        """Test normalization of blame_ref with tilde."""
        context = SquashContext(
            blame_ref="HEAD~1",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        assert context.normalized_blame_ref == "HEAD~1"

    def test_normalized_blame_ref_commit_sha(self):
        """Test normalization of commit SHA blame_ref."""
        context = SquashContext(
            blame_ref="abc123~1",
            source_commit="abc123",
            is_historical_commit=True,
            working_tree_clean=True,
        )

        assert context.normalized_blame_ref == "ABC123~1"


class TestIsProcessingHeadCommit:
    """Test is_processing_head_commit property."""

    def test_processing_head_commit_clean_tree(self):
        """Test is_processing_head_commit when HEAD with clean tree."""
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        assert context.is_processing_head_commit is True

    def test_not_processing_head_commit_dirty_tree(self):
        """Test is_processing_head_commit when HEAD with dirty tree."""
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=False,
        )

        assert context.is_processing_head_commit is False

    def test_not_processing_head_commit_historical(self):
        """Test is_processing_head_commit when processing historical commit."""
        context = SquashContext(
            blame_ref="abc123~1",
            source_commit="abc123",
            is_historical_commit=True,
            working_tree_clean=True,
        )

        assert context.is_processing_head_commit is False

    def test_not_processing_head_commit_head_tilde(self):
        """Test is_processing_head_commit when blame_ref is HEAD~1."""
        context = SquashContext(
            blame_ref="HEAD~1",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        assert context.is_processing_head_commit is False


class TestShouldExcludeHeadFromBlame:
    """Test should_exclude_head_from_blame() method."""

    def test_exclude_head_when_processing_head_clean(self):
        """Test HEAD excluded when blame_ref=HEAD and tree clean."""
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        assert context.should_exclude_head_from_blame() is True

    def test_include_head_when_processing_head_dirty(self):
        """Test HEAD included when blame_ref=HEAD but tree dirty."""
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=False,
        )

        assert context.should_exclude_head_from_blame() is False

    def test_include_head_when_processing_historical(self):
        """Test HEAD included when processing historical commit."""
        context = SquashContext(
            blame_ref="abc123~1",
            source_commit="abc123",
            is_historical_commit=True,
            working_tree_clean=True,
        )

        assert context.should_exclude_head_from_blame() is False

    def test_include_head_when_blame_ref_head_tilde(self):
        """Test HEAD included when blame_ref=HEAD~1."""
        context = SquashContext(
            blame_ref="HEAD~1",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        assert context.should_exclude_head_from_blame() is False


class TestShouldExcludeHeadFromFallback:
    """Test should_exclude_head_from_fallback() method."""

    def test_exclude_head_consistent_with_blame(self):
        """Test fallback exclusion matches blame exclusion."""
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        # Should match blame exclusion
        assert (
            context.should_exclude_head_from_fallback()
            == context.should_exclude_head_from_blame()
        )
        assert context.should_exclude_head_from_fallback() is True

    def test_include_head_consistent_with_blame_dirty(self):
        """Test fallback inclusion matches blame when dirty."""
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=False,
        )

        assert (
            context.should_exclude_head_from_fallback()
            == context.should_exclude_head_from_blame()
        )
        assert context.should_exclude_head_from_fallback() is False

    def test_include_head_consistent_for_historical(self):
        """Test fallback inclusion matches blame for historical commits."""
        context = SquashContext(
            blame_ref="abc123~1",
            source_commit="abc123",
            is_historical_commit=True,
            working_tree_clean=True,
        )

        assert (
            context.should_exclude_head_from_fallback()
            == context.should_exclude_head_from_blame()
        )
        assert context.should_exclude_head_from_fallback() is False


class TestValidateSourceCommit:
    """Test validate_source_commit() method."""

    @pytest.fixture
    def mock_git_ops(self):
        """Mock GitOps for testing."""
        mock = Mock(spec=GitOps)
        return mock

    def test_validate_none_source_commit(self, mock_git_ops):
        """Test validation with no source commit."""
        context = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        errors = context.validate_source_commit(mock_git_ops)

        assert errors == []

    def test_validate_with_valid_source_commit(self, mock_git_ops):
        """Test validation with valid source commit."""
        context = SquashContext(
            blame_ref="abc123def456~1",
            source_commit="abc123def456",
            is_historical_commit=True,
            working_tree_clean=True,
        )

        # Mock cat-file to return "commit"
        cat_file_result = Mock()
        cat_file_result.returncode = 0
        cat_file_result.stdout = "commit\n"

        # Mock merge-base --is-ancestor to succeed
        ancestor_result = Mock()
        ancestor_result.returncode = 0

        # Mock rev-parse HEAD
        head_result = Mock()
        head_result.returncode = 0
        head_result.stdout = "different123\n"

        # Mock rev-parse for source commit
        source_result = Mock()
        source_result.returncode = 0
        source_result.stdout = "abc123def456789012345678901234567890abcd\n"

        mock_git_ops.run_git_command.side_effect = [
            cat_file_result,
            ancestor_result,
            head_result,
            source_result,
        ]

        errors = context.validate_source_commit(mock_git_ops)

        assert errors == []

    def test_validate_invalid_sha_format(self, mock_git_ops):
        """Test validation with invalid SHA format."""
        context = SquashContext(
            blame_ref="invalid_sha!~1",
            source_commit="invalid_sha!",
            is_historical_commit=True,
            working_tree_clean=True,
        )

        errors = context.validate_source_commit(mock_git_ops)

        assert len(errors) == 1
        assert "Invalid commit format" in errors[0]

    def test_validate_nonexistent_commit(self, mock_git_ops):
        """Test validation with nonexistent commit."""
        context = SquashContext(
            blame_ref="abcd1234~1",
            source_commit="abcd1234",
            is_historical_commit=True,
            working_tree_clean=True,
        )

        # Mock cat-file to fail (commit doesn't exist)
        cat_file_result = Mock()
        cat_file_result.returncode = 1
        cat_file_result.stderr = "fatal: Not a valid object name"

        mock_git_ops.run_git_command.return_value = cat_file_result

        errors = context.validate_source_commit(mock_git_ops)

        assert len(errors) == 1
        assert "does not exist" in errors[0]


class TestSquashContextEquality:
    """Test SquashContext equality and hashing."""

    def test_equality_same_values(self):
        """Test equality with same values."""
        context1 = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )
        context2 = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        assert context1 == context2

    def test_inequality_different_blame_ref(self):
        """Test inequality with different blame_ref."""
        context1 = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )
        context2 = SquashContext(
            blame_ref="HEAD~1",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        assert context1 != context2

    def test_hashable(self):
        """Test that SquashContext is hashable (can be used in sets/dicts)."""
        context1 = SquashContext(
            blame_ref="HEAD",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )
        context2 = SquashContext(
            blame_ref="HEAD~1",
            source_commit=None,
            is_historical_commit=False,
            working_tree_clean=True,
        )

        # Should be able to use in set
        context_set = {context1, context2}
        assert len(context_set) == 2

        # Should be able to use as dict key
        context_dict = {context1: "value1", context2: "value2"}
        assert context_dict[context1] == "value1"
