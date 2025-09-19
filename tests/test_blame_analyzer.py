"""Tests for blame_analyzer module."""

from typing import List
from unittest.mock import Mock, patch

from git_autosquash.blame_analyzer import BlameAnalyzer, BlameInfo, HunkTargetMapping
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from tests.conftest import create_test_hunk


class TestBlameInfo:
    """Test cases for BlameInfo dataclass."""

    def test_blame_info_creation(self) -> None:
        """Test BlameInfo creation with all fields."""
        blame_info = BlameInfo(
            commit_hash="abc123456",
            author="John Doe",
            timestamp="2023-01-01 12:00:00 +0000",
            line_number=42,
            line_content="example line content",
        )

        assert blame_info.commit_hash == "abc123456"
        assert blame_info.author == "John Doe"
        assert blame_info.timestamp == "2023-01-01 12:00:00 +0000"
        assert blame_info.line_number == 42
        assert blame_info.line_content == "example line content"


class TestHunkTargetMapping:
    """Test cases for HunkTargetMapping dataclass."""

    def test_hunk_target_mapping_creation(self) -> None:
        """Test HunkTargetMapping creation."""
        hunk = Mock(spec=DiffHunk)
        blame_info: List[BlameInfo] = [Mock(spec=BlameInfo)]

        mapping = HunkTargetMapping(
            hunk=hunk,
            target_commit="def456789",
            confidence="high",
            blame_info=blame_info,
        )

        assert mapping.hunk is hunk
        assert mapping.target_commit == "def456789"
        assert mapping.confidence == "high"
        assert mapping.blame_info is blame_info


class TestBlameAnalyzer:
    """Test cases for BlameAnalyzer class."""

    def test_init(self) -> None:
        """Test BlameAnalyzer initialization."""
        git_ops = Mock(spec=GitOps)
        merge_base = "abc123"

        analyzer = BlameAnalyzer(git_ops, merge_base)

        assert analyzer.git_ops is git_ops
        assert analyzer.merge_base == merge_base
        assert analyzer._branch_commits_cache is None

    @patch.object(BlameAnalyzer, "_analyze_single_hunk")
    def test_analyze_hunks(self, mock_analyze: Mock) -> None:
        """Test analyze_hunks processes all hunks."""
        git_ops = Mock(spec=GitOps)
        analyzer = BlameAnalyzer(git_ops, "merge_base")

        hunk1 = Mock(spec=DiffHunk)
        hunk2 = Mock(spec=DiffHunk)
        hunks: List[DiffHunk] = [hunk1, hunk2]

        mapping1 = Mock(spec=HunkTargetMapping)
        mapping2 = Mock(spec=HunkTargetMapping)
        mock_analyze.side_effect = [mapping1, mapping2]

        result = analyzer.analyze_hunks(hunks)

        assert len(result) == 2
        assert result[0] is mapping1
        assert result[1] is mapping2
        assert mock_analyze.call_count == 2

    @patch("git_autosquash.blame_analyzer.BatchGitOperations")
    @patch.object(BlameAnalyzer, "_get_commit_timestamp")
    @patch.object(BlameAnalyzer, "_get_branch_commits")
    @patch.object(BlameAnalyzer, "_get_blame_for_old_lines")
    def test_analyze_single_hunk_with_deletions(
        self,
        mock_blame_old: Mock,
        mock_branch_commits: Mock,
        mock_timestamp: Mock,
        mock_batch_ops_class: Mock,
    ) -> None:
        """Test analyzing hunk with deletions."""
        git_ops = Mock(spec=GitOps)

        # Mock BatchGitOperations
        mock_batch_ops = Mock()
        mock_batch_ops.get_new_files.return_value = set()
        mock_batch_ops_class.return_value = mock_batch_ops

        analyzer = BlameAnalyzer(git_ops, "merge_base")

        # Create a proper DiffHunk instead of Mock
        hunk = DiffHunk(
            file_path="test.py",
            old_start=10,
            old_count=2,
            new_start=10,
            new_count=3,
            lines=["@@ -10,2 +10,3 @@", "-deleted line", " existing line"],
            context_before=["context before"],
            context_after=["context after"],
        )

        blame_info = BlameInfo(
            commit_hash="commit1",
            author="author",
            timestamp="2023-01-01 12:00:00 +0000",
            line_number=1,
            line_content="content",
        )

        mock_blame_old.return_value = [blame_info]
        mock_branch_commits.return_value = {"commit1"}
        mock_timestamp.return_value = 1640995200  # 2022-01-01 timestamp

        result = analyzer._analyze_single_hunk(hunk)

        mock_blame_old.assert_called_once_with(hunk)
        assert result.hunk is hunk
        assert result.target_commit == "commit1"
        assert result.confidence == "high"  # 100% agreement
        assert len(result.blame_info) == 1

    @patch.object(BlameAnalyzer, "_get_commit_timestamp")
    @patch.object(BlameAnalyzer, "_get_branch_commits")
    @patch.object(BlameAnalyzer, "_get_blame_for_context")
    def test_analyze_single_hunk_additions_only(
        self,
        mock_blame_context: Mock,
        mock_branch_commits: Mock,
        mock_timestamp: Mock,
        blame_analyzer: BlameAnalyzer,
    ) -> None:
        """Test analyzing hunk with only additions."""
        analyzer = blame_analyzer

        hunk = create_test_hunk(additions=["new line"])

        blame_info = BlameInfo(
            commit_hash="commit2",
            author="author",
            timestamp="2023-01-01 12:00:00 +0000",
            line_number=1,
            line_content="content",
        )

        mock_blame_context.return_value = [blame_info]
        mock_branch_commits.return_value = {"commit2"}
        mock_timestamp.return_value = 1640995200

        result = analyzer._analyze_single_hunk(hunk)

        mock_blame_context.assert_called_once_with(hunk)
        assert result.target_commit == "commit2"

    @patch.object(BlameAnalyzer, "_get_blame_for_old_lines")
    def test_analyze_single_hunk_no_blame_info(
        self, mock_blame: Mock, blame_analyzer: BlameAnalyzer
    ) -> None:
        """Test analyzing hunk when no blame info is available."""
        analyzer = blame_analyzer

        hunk = create_test_hunk(deletions=["old line"])

        mock_blame.return_value = []

        result = analyzer._analyze_single_hunk(hunk)

        assert result.hunk is hunk
        assert result.target_commit is None
        assert result.confidence == "low"
        assert result.blame_info == []

    @patch.object(BlameAnalyzer, "_get_commit_timestamp")
    @patch.object(BlameAnalyzer, "_get_branch_commits")
    @patch.object(BlameAnalyzer, "_get_blame_for_old_lines")
    def test_analyze_single_hunk_no_branch_commits(
        self,
        mock_blame: Mock,
        mock_branch_commits: Mock,
        mock_timestamp: Mock,
        blame_analyzer: BlameAnalyzer,
    ) -> None:
        """Test analyzing hunk when no commits are in branch scope."""
        analyzer = blame_analyzer

        hunk = create_test_hunk(deletions=["old line"])

        blame_info = BlameInfo(
            commit_hash="old_commit",
            author="author",
            timestamp="2020-01-01 12:00:00 +0000",
            line_number=1,
            line_content="content",
        )

        mock_blame.return_value = [blame_info]
        mock_branch_commits.return_value = {"other_commit"}  # Different commit

        result = analyzer._analyze_single_hunk(hunk)

        assert result.target_commit is None
        assert result.confidence == "low"
        assert len(result.blame_info) == 1  # Original blame info preserved

    @patch.object(BlameAnalyzer, "_get_commit_timestamp")
    @patch.object(BlameAnalyzer, "_get_branch_commits")
    @patch.object(BlameAnalyzer, "_get_blame_for_old_lines")
    def test_analyze_single_hunk_confidence_levels(
        self,
        mock_blame: Mock,
        mock_branch_commits: Mock,
        mock_timestamp: Mock,
        blame_analyzer: BlameAnalyzer,
    ) -> None:
        """Test confidence calculation with multiple commits."""
        analyzer = blame_analyzer

        hunk = create_test_hunk(deletions=["line1", "line2", "line3", "line4"])

        # 3 lines from commit1, 1 line from commit2 (75% agreement)
        blame_infos = [
            BlameInfo("commit1", "author", "2023-01-01 12:00:00 +0000", 1, "line1"),
            BlameInfo("commit1", "author", "2023-01-01 12:00:00 +0000", 2, "line2"),
            BlameInfo("commit1", "author", "2023-01-01 12:00:00 +0000", 3, "line3"),
            BlameInfo("commit2", "author", "2023-01-02 12:00:00 +0000", 4, "line4"),
        ]

        mock_blame.return_value = blame_infos
        mock_branch_commits.return_value = {"commit1", "commit2"}

        # Make commit2 more recent (should be selected)
        def timestamp_side_effect(commit_hash: str) -> int:
            if commit_hash == "commit1":
                return 1640995200  # 2022-01-01
            else:  # commit2
                return 1641081600  # 2022-01-02

        mock_timestamp.side_effect = timestamp_side_effect

        result = analyzer._analyze_single_hunk(hunk)

        assert result.target_commit == "commit1"  # Most frequent (3/4 lines)
        assert result.confidence == "medium"  # 75% agreement (3/4)

    @patch.object(BlameAnalyzer, "_parse_blame_output")
    def test_get_blame_for_old_lines(self, mock_parse: Mock) -> None:
        """Test getting blame for deleted/modified lines."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "blame output")
        analyzer = BlameAnalyzer(git_ops, "merge_base")

        hunk = DiffHunk(
            file_path="test.py",
            old_start=5,
            old_count=3,
            new_start=5,
            new_count=2,
            lines=[],
            context_before=[],
            context_after=[],
        )

        blame_infos = [Mock(spec=BlameInfo)]
        mock_parse.return_value = blame_infos

        result = analyzer._get_blame_for_old_lines(hunk)

        git_ops._run_git_command.assert_called_once_with(
            "blame", "-L5,7", "HEAD", "--", "test.py"
        )
        mock_parse.assert_called_once_with("blame output")
        assert result is blame_infos

    def test_get_blame_for_old_lines_command_failure(
        self, blame_analyzer: BlameAnalyzer
    ) -> None:
        """Test get_blame_for_old_lines handles command failure."""
        analyzer = blame_analyzer
        analyzer.git_ops._run_git_command.return_value = (False, "error")  # type: ignore[attr-defined]

        hunk = create_test_hunk(file_path="test.py", deletions=["old line"])

        result = analyzer._get_blame_for_old_lines(hunk)
        assert result == []

    @patch.object(BlameAnalyzer, "_parse_blame_output")
    def test_get_blame_for_context(
        self, mock_parse: Mock, blame_analyzer: BlameAnalyzer
    ) -> None:
        """Test getting blame for context around additions."""
        analyzer = blame_analyzer
        analyzer.git_ops._run_git_command.return_value = (True, "blame output")  # type: ignore[attr-defined]

        hunk = DiffHunk(
            file_path="test.py",
            old_start=0,
            old_count=0,
            new_start=10,
            new_count=1,
            lines=[],
            context_before=[],
            context_after=[],
        )

        blame_infos = [Mock(spec=BlameInfo)]
        mock_parse.return_value = blame_infos

        result = analyzer._get_blame_for_context(hunk)

        # Should get context from lines 1-3 (max(1, 0-3) to 0+3)
        # The algorithm uses old_start for context calculation
        analyzer.git_ops._run_git_command.assert_called_once_with(  # type: ignore[attr-defined]
            "blame", "-L1,3", "HEAD", "--", "test.py"
        )
        assert result is blame_infos

    def test_get_blame_for_context_at_file_start(
        self, blame_analyzer: BlameAnalyzer
    ) -> None:
        """Test get_blame_for_context when addition is at file start."""
        analyzer = blame_analyzer
        analyzer.git_ops._run_git_command.return_value = (True, "")  # type: ignore[attr-defined]

        hunk = create_test_hunk(
            file_path="test.py", new_start=1, additions=["new line"]
        )

        analyzer._get_blame_for_context(hunk)

        # Should start from line 1 (max(1, 1-3))
        analyzer.git_ops._run_git_command.assert_called_once_with(  # type: ignore[attr-defined]
            "blame", "-L1,4", "HEAD", "--", "test.py"
        )

    def test_parse_blame_output(self, blame_analyzer: BlameAnalyzer) -> None:
        """Test parsing git blame output."""
        analyzer = blame_analyzer

        blame_output = """abc123456 (John Doe 2023-01-15 10:30:00 +0000 42) example line content
def789012 (Jane Smith 2023-01-16 14:45:00 +0000 43) another line"""

        result = analyzer._parse_blame_output(blame_output)

        assert len(result) == 2

        # First blame info
        assert result[0].commit_hash == "abc123456"
        assert result[0].author == "John Doe"
        assert result[0].timestamp == "2023-01-15 10:30:00 +0000"
        assert result[0].line_number == 42
        assert result[0].line_content == "example line content"

        # Second blame info
        assert result[1].commit_hash == "def789012"
        assert result[1].author == "Jane Smith"
        assert result[1].timestamp == "2023-01-16 14:45:00 +0000"
        assert result[1].line_number == 43
        assert result[1].line_content == "another line"

    def test_parse_blame_output_empty(self, blame_analyzer: BlameAnalyzer) -> None:
        """Test parsing empty blame output."""
        analyzer = blame_analyzer

        result = analyzer._parse_blame_output("")
        assert result == []

        result = analyzer._parse_blame_output("   \n  \n  ")
        assert result == []

    def test_parse_blame_output_malformed_line(
        self, blame_analyzer: BlameAnalyzer
    ) -> None:
        """Test parsing blame output with malformed lines."""
        analyzer = blame_analyzer

        blame_output = """abc123456 (John Doe 2023-01-15 10:30:00 +0000 42) good line
malformed line without proper format
def789012 (Jane Smith 2023-01-16 14:45:00 +0000 43) another good line"""

        result = analyzer._parse_blame_output(blame_output)

        # Should parse only the well-formed lines
        assert len(result) == 2
        assert result[0].commit_hash == "abc123456"
        assert result[1].commit_hash == "def789012"

    def test_get_branch_commits_caching(self) -> None:
        """Test that branch commits are cached."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "commit1\ncommit2\ncommit3")
        analyzer = BlameAnalyzer(git_ops, "merge_base")

        # First call
        result1 = analyzer._get_branch_commits()
        assert result1 == {"commit1", "commit2", "commit3"}

        # Second call should use cache
        result2 = analyzer._get_branch_commits()
        assert result2 == {"commit1", "commit2", "commit3"}

        # Should only call git command once
        git_ops._run_git_command.assert_called_once()

    def test_get_branch_commits_command_failure(self) -> None:
        """Test get_branch_commits handles command failure."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (False, "error")
        analyzer = BlameAnalyzer(git_ops, "merge_base")

        result = analyzer._get_branch_commits()
        assert result == set()

    def test_get_branch_commits_empty_output(self) -> None:
        """Test get_branch_commits handles empty output."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "")
        analyzer = BlameAnalyzer(git_ops, "merge_base")

        result = analyzer._get_branch_commits()
        assert result == set()

    def test_get_commit_timestamp(self, blame_analyzer: BlameAnalyzer) -> None:
        """Test getting commit timestamp."""
        analyzer = blame_analyzer
        # The method now uses batch operations, so we test the result directly
        result = analyzer._get_commit_timestamp("abc123")

        # Should return the timestamp from the mocked batch operations
        assert result == 1640995200

    def test_get_commit_timestamp_command_failure(self) -> None:
        """Test get_commit_timestamp handles command failure."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (False, "error")
        analyzer = BlameAnalyzer(git_ops, "merge_base")

        result = analyzer._get_commit_timestamp("abc123")
        assert result == 0

    def test_get_commit_timestamp_invalid_output(self) -> None:
        """Test get_commit_timestamp handles invalid output."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "not-a-number")
        analyzer = BlameAnalyzer(git_ops, "merge_base")

        result = analyzer._get_commit_timestamp("abc123")
        assert result == 0

    def test_get_commit_summary(self, blame_analyzer: BlameAnalyzer) -> None:
        """Test getting commit summary."""
        analyzer = blame_analyzer
        # The method now uses batch operations, so we test the result directly
        result = analyzer.get_commit_summary("abc123456")

        # Should return the summary from the mocked batch operations
        assert result == "abc1234 Add new feature"

    def test_get_commit_summary_command_failure(self) -> None:
        """Test get_commit_summary handles command failure."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (False, "error")
        analyzer = BlameAnalyzer(git_ops, "merge_base")

        result = analyzer.get_commit_summary("abc123456")
        assert result == "abc12345"  # First 8 chars as fallback
