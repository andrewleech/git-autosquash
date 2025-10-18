"""Tests for hunk_parser module."""

from unittest.mock import Mock, patch

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk, HunkParser


class TestDiffHunk:
    """Test cases for DiffHunk dataclass."""

    def test_affected_lines_property(self) -> None:
        """Test affected_lines returns correct range."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=10,
            old_count=3,
            new_start=15,
            new_count=5,
            lines=[],
            context_before=[],
            context_after=[],
        )

        assert hunk.affected_lines == range(15, 20)

    def test_has_additions_true(self) -> None:
        """Test has_additions returns True for additions."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=0,
            new_start=1,
            new_count=2,
            lines=["@@ -1,0 +1,2 @@", "+new line 1", "+new line 2"],
            context_before=[],
            context_after=[],
        )

        assert hunk.has_additions is True
        assert hunk.has_deletions is False

    def test_has_deletions_true(self) -> None:
        """Test has_deletions returns True for deletions."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=2,
            new_start=1,
            new_count=0,
            lines=["@@ -1,2 +1,0 @@", "-old line 1", "-old line 2"],
            context_before=[],
            context_after=[],
        )

        assert hunk.has_additions is False
        assert hunk.has_deletions is True

    def test_mixed_changes(self) -> None:
        """Test hunk with both additions and deletions."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=2,
            new_start=1,
            new_count=3,
            lines=[
                "@@ -1,2 +1,3 @@",
                "-old line",
                "+new line 1",
                "+new line 2",
                " context line",
            ],
            context_before=[],
            context_after=[],
        )

        assert hunk.has_additions is True
        assert hunk.has_deletions is True

    def test_ignores_file_headers(self) -> None:
        """Test that file headers (--- and +++) are ignored."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=[
                "--- a/test.py",
                "+++ b/test.py",
                "@@ -1,1 +1,1 @@",
                " context line",
            ],
            context_before=[],
            context_after=[],
        )

        assert hunk.has_additions is False
        assert hunk.has_deletions is False


class TestHunkParser:
    """Test cases for HunkParser class."""

    def test_init(self) -> None:
        """Test HunkParser initialization."""
        git_ops = Mock(spec=GitOps)
        parser = HunkParser(git_ops)
        assert parser.git_ops is git_ops

    @patch.object(HunkParser, "_parse_diff_output")
    def test_get_diff_hunks_clean_working_tree(self, mock_parse: Mock) -> None:
        """Test get_diff_hunks with clean working tree."""
        git_ops = Mock(spec=GitOps)
        git_ops.get_working_tree_status.return_value = {
            "is_clean": True,
            "has_staged": False,
            "has_unstaged": False,
        }
        git_ops._run_git_command.return_value = (True, "diff output")
        mock_parse.return_value = []

        parser = HunkParser(git_ops)
        result = parser.get_diff_hunks()

        git_ops._run_git_command.assert_called_once_with("show", "--format=", "HEAD")
        mock_parse.assert_called_once_with("diff output")
        assert result == []

    @patch.object(HunkParser, "_parse_diff_output")
    def test_get_diff_hunks_staged_only(self, mock_parse: Mock) -> None:
        """Test get_diff_hunks with only staged changes."""
        git_ops = Mock(spec=GitOps)
        git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": True,
            "has_unstaged": False,
        }
        git_ops._run_git_command.return_value = (True, "diff output")
        mock_parse.return_value = []

        parser = HunkParser(git_ops)
        parser.get_diff_hunks()

        git_ops._run_git_command.assert_called_once_with("diff", "--cached")
        mock_parse.assert_called_once_with("diff output")

    @patch.object(HunkParser, "_parse_diff_output")
    def test_get_diff_hunks_unstaged_only(self, mock_parse: Mock) -> None:
        """Test get_diff_hunks with only unstaged changes."""
        git_ops = Mock(spec=GitOps)
        git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": False,
            "has_unstaged": True,
        }
        git_ops._run_git_command.return_value = (True, "diff output")
        mock_parse.return_value = []

        parser = HunkParser(git_ops)
        parser.get_diff_hunks()

        git_ops._run_git_command.assert_called_once_with("diff")
        mock_parse.assert_called_once_with("diff output")

    @patch.object(HunkParser, "_parse_diff_output")
    def test_get_diff_hunks_mixed_changes(self, mock_parse: Mock) -> None:
        """Test get_diff_hunks with both staged and unstaged changes.

        When both staged and unstaged changes exist, git-autosquash processes
        the staged changes only. Unstaged changes are stashed temporarily.
        """
        git_ops = Mock(spec=GitOps)
        git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": True,
            "has_unstaged": True,
        }
        git_ops._run_git_command.return_value = (True, "diff output")
        mock_parse.return_value = []

        parser = HunkParser(git_ops)
        parser.get_diff_hunks()

        # Should process staged changes (--cached) when both staged and unstaged exist
        git_ops._run_git_command.assert_called_once_with("diff", "--cached")
        mock_parse.assert_called_once_with("diff output")

    def test_get_diff_hunks_command_failure(self) -> None:
        """Test get_diff_hunks handles git command failure."""
        git_ops = Mock(spec=GitOps)
        git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": False,
            "has_unstaged": True,
        }
        git_ops._run_git_command.return_value = (False, "error")

        parser = HunkParser(git_ops)
        result = parser.get_diff_hunks()

        assert result == []

    @patch.object(HunkParser, "_split_hunks_line_by_line")
    @patch.object(HunkParser, "_parse_diff_output")
    def test_get_diff_hunks_line_by_line(
        self, mock_parse: Mock, mock_split: Mock
    ) -> None:
        """Test get_diff_hunks with line_by_line=True."""
        git_ops = Mock(spec=GitOps)
        git_ops.get_working_tree_status.return_value = {
            "is_clean": False,
            "has_staged": False,
            "has_unstaged": True,
        }
        git_ops._run_git_command.return_value = (True, "diff output")

        original_hunks = [Mock(spec=DiffHunk)]
        split_hunks = [Mock(spec=DiffHunk), Mock(spec=DiffHunk)]

        mock_parse.return_value = original_hunks
        mock_split.return_value = split_hunks

        parser = HunkParser(git_ops)
        result = parser.get_diff_hunks(line_by_line=True)

        mock_parse.assert_called_once_with("diff output")
        mock_split.assert_called_once_with(original_hunks)
        assert result == split_hunks

    def test_parse_diff_output_empty(self) -> None:
        """Test parsing empty diff output."""
        git_ops = Mock(spec=GitOps)
        parser = HunkParser(git_ops)

        result = parser._parse_diff_output("")
        assert result == []

        result = parser._parse_diff_output("   \n  \n  ")
        assert result == []

    def test_parse_diff_output_single_hunk(self) -> None:
        """Test parsing diff output with single hunk."""
        git_ops = Mock(spec=GitOps)
        parser = HunkParser(git_ops)

        diff_output = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 line 1
+new line
 line 2
 line 3"""

        result = parser._parse_diff_output(diff_output)

        assert len(result) == 1
        hunk = result[0]
        assert hunk.file_path == "test.py"
        assert hunk.old_start == 1
        assert hunk.old_count == 3
        assert hunk.new_start == 1
        assert hunk.new_count == 4
        assert len(hunk.lines) == 5  # @@ line + 4 content lines

    def test_parse_diff_output_multiple_hunks(self) -> None:
        """Test parsing diff output with multiple hunks."""
        git_ops = Mock(spec=GitOps)
        parser = HunkParser(git_ops)

        diff_output = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,2 +1,3 @@
 line 1
+added line
 line 2
@@ -10,2 +11,2 @@
-old line
+new line
 context"""

        result = parser._parse_diff_output(diff_output)

        assert len(result) == 2

        # First hunk
        hunk1 = result[0]
        assert hunk1.old_start == 1
        assert hunk1.old_count == 2
        assert hunk1.new_start == 1
        assert hunk1.new_count == 3

        # Second hunk
        hunk2 = result[1]
        assert hunk2.old_start == 10
        assert hunk2.old_count == 2
        assert hunk2.new_start == 11
        assert hunk2.new_count == 2

    def test_parse_diff_output_multiple_files(self) -> None:
        """Test parsing diff output with multiple files."""
        git_ops = Mock(spec=GitOps)
        parser = HunkParser(git_ops)

        diff_output = """diff --git a/file1.py b/file1.py
index 1234567..abcdefg 100644
--- a/file1.py
+++ b/file1.py
@@ -1,1 +1,2 @@
 line 1
+added to file1
diff --git a/file2.py b/file2.py
index 7890abc..defghij 100644
--- a/file2.py
+++ b/file2.py
@@ -1,1 +1,2 @@
 line 1
+added to file2"""

        result = parser._parse_diff_output(diff_output)

        assert len(result) == 2
        assert result[0].file_path == "file1.py"
        assert result[1].file_path == "file2.py"

    def test_split_hunks_line_by_line_simple(self) -> None:
        """Test splitting a simple hunk line by line."""
        git_ops = Mock(spec=GitOps)
        parser = HunkParser(git_ops)

        original_hunk = DiffHunk(
            file_path="test.py",
            old_start=5,
            old_count=2,
            new_start=5,
            new_count=3,
            lines=["@@ -5,2 +5,3 @@", " context line", "+addition 1", "+addition 2"],
            context_before=[],
            context_after=[],
        )

        result = parser._split_hunks_line_by_line([original_hunk])

        # Should create 2 separate hunks for the 2 additions
        assert len(result) == 2

        # First addition
        assert result[0].file_path == "test.py"
        assert result[0].new_start == 6  # After context line
        assert result[0].new_count == 1
        assert "+addition 1" in result[0].lines

        # Second addition
        assert result[1].new_start == 7  # After first addition
        assert result[1].new_count == 1
        assert "+addition 2" in result[1].lines

    def test_split_hunks_line_by_line_single_change(self) -> None:
        """Test that single line changes are not split further."""
        git_ops = Mock(spec=GitOps)
        parser = HunkParser(git_ops)

        original_hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "+single addition"],
            context_before=[],
            context_after=[],
        )

        result = parser._split_hunks_line_by_line([original_hunk])

        # Should keep the original hunk unchanged
        assert len(result) == 1
        assert result[0] is original_hunk

    def test_get_file_content_at_lines(self) -> None:
        """Test getting file content at specific line range."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (
            True,
            "line 1\nline 2\nline 3\nline 4\nline 5",
        )

        parser = HunkParser(git_ops)
        result = parser.get_file_content_at_lines("test.py", 2, 4)

        git_ops._run_git_command.assert_called_once_with("show", "HEAD:test.py")
        assert result == ["line 2", "line 3", "line 4"]

    def test_get_file_content_at_lines_command_failure(self) -> None:
        """Test get_file_content_at_lines handles command failure."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (False, "file not found")

        parser = HunkParser(git_ops)
        result = parser.get_file_content_at_lines("test.py", 1, 3)

        assert result == []

    def test_get_file_content_at_lines_bounds_checking(self) -> None:
        """Test get_file_content_at_lines handles bounds correctly."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "line 1\nline 2\nline 3")

        parser = HunkParser(git_ops)

        # Test start before beginning
        result = parser.get_file_content_at_lines("test.py", -1, 2)
        assert result == ["line 1", "line 2"]

        # Test end after end of file
        result = parser.get_file_content_at_lines("test.py", 2, 10)
        assert result == ["line 2", "line 3"]

    @patch.object(HunkParser, "_parse_diff_output")
    def test_get_diff_hunks_from_commit_success(self, mock_parse: Mock) -> None:
        """Test get_diff_hunks with from_commit parameter."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "diff output from commit")
        mock_parse.return_value = []

        parser = HunkParser(git_ops)
        result = parser.get_diff_hunks(from_commit="abc123")

        git_ops._run_git_command.assert_called_once_with("show", "--format=", "abc123")
        mock_parse.assert_called_once_with("diff output from commit")
        assert result == []

    @patch.object(HunkParser, "_parse_diff_output")
    def test_get_diff_hunks_from_commit_failure(self, mock_parse: Mock) -> None:
        """Test get_diff_hunks handles git command failure with from_commit."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (False, "fatal: bad commit")

        parser = HunkParser(git_ops)
        result = parser.get_diff_hunks(from_commit="badcommit")

        git_ops._run_git_command.assert_called_once_with(
            "show", "--format=", "badcommit"
        )
        mock_parse.assert_not_called()
        assert result == []

    @patch.object(HunkParser, "_parse_diff_output")
    @patch.object(HunkParser, "_split_hunks_line_by_line")
    def test_get_diff_hunks_from_commit_line_by_line(
        self, mock_split: Mock, mock_parse: Mock
    ) -> None:
        """Test get_diff_hunks with from_commit and line_by_line=True."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "diff output")

        original_hunks = [Mock(spec=DiffHunk)]
        split_hunks = [Mock(spec=DiffHunk), Mock(spec=DiffHunk)]

        mock_parse.return_value = original_hunks
        mock_split.return_value = split_hunks

        parser = HunkParser(git_ops)
        result = parser.get_diff_hunks(from_commit="abc123", line_by_line=True)

        git_ops._run_git_command.assert_called_once_with("show", "--format=", "abc123")
        mock_parse.assert_called_once_with("diff output")
        mock_split.assert_called_once_with(original_hunks)
        assert result == split_hunks

    @patch.object(HunkParser, "_get_hunks_from_source")
    def test_get_diff_hunks_from_commit_ignores_source(
        self, mock_get_source: Mock
    ) -> None:
        """Test that from_commit parameter takes precedence over source."""
        git_ops = Mock(spec=GitOps)
        git_ops._run_git_command.return_value = (True, "")

        parser = HunkParser(git_ops)
        parser.get_diff_hunks(from_commit="abc123", source="working-tree")

        # from_commit should be used, source should be ignored
        git_ops._run_git_command.assert_called_once_with("show", "--format=", "abc123")
        mock_get_source.assert_not_called()
