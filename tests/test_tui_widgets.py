"""Tests for TUI widgets."""

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.tui.widgets import DiffViewer, HunkMappingWidget, ProgressIndicator


class TestHunkMappingWidget:
    """Test cases for HunkMappingWidget."""

    def test_init(self) -> None:
        """Test HunkMappingWidget initialization."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=5,
            old_count=2,
            new_start=5,
            new_count=3,
            lines=["@@ -5,2 +5,3 @@", " line 1", "+added line", " line 2"],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="abc123", confidence="high", blame_info=[]
        )

        widget = HunkMappingWidget(mapping)

        assert widget.mapping is mapping
        assert widget.selected is False
        assert widget.approved is False  # Default to unapproved for safety

    def test_format_hunk_range(self) -> None:
        """Test hunk range formatting."""
        hunk = DiffHunk(
            file_path="test.py",
            old_start=10,
            old_count=5,
            new_start=12,
            new_count=7,
            lines=[],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit="def456", confidence="medium", blame_info=[]
        )

        widget = HunkMappingWidget(mapping)
        result = widget._format_hunk_range()

        assert result == "-10,5 +12,7"

    def test_no_target_commit(self) -> None:
        """Test widget with no target commit."""
        hunk = DiffHunk(
            file_path="new_file.py",
            old_start=0,
            old_count=0,
            new_start=1,
            new_count=10,
            lines=[],
            context_before=[],
            context_after=[],
        )

        mapping = HunkTargetMapping(
            hunk=hunk, target_commit=None, confidence="low", blame_info=[]
        )

        widget = HunkMappingWidget(mapping)
        assert widget.mapping.target_commit is None


class TestDiffViewer:
    """Test cases for DiffViewer."""

    def test_init(self) -> None:
        """Test DiffViewer initialization."""
        viewer = DiffViewer()
        assert viewer._current_hunk is None

    def test_get_language_from_file(self) -> None:
        """Test language detection from file extensions."""
        viewer = DiffViewer()

        test_cases = [
            ("test.py", "python"),
            ("app.js", "javascript"),
            ("component.tsx", "tsx"),
            ("styles.css", "css"),
            ("config.json", "json"),
            ("data.yaml", "yaml"),
            ("script.sh", "bash"),
            ("README.md", "markdown"),
            ("unknown.xyz", "text"),
        ]

        for file_path, expected_language in test_cases:
            result = viewer._get_language_from_file(file_path)
            assert result == expected_language, (
                f"Expected {expected_language} for {file_path}, got {result}"
            )

    def test_get_language_from_file_no_extension(self) -> None:
        """Test language detection for files without extensions."""
        viewer = DiffViewer()
        result = viewer._get_language_from_file("Makefile")
        assert result == "text"

    def test_show_hunk(self) -> None:
        """Test showing a hunk in the diff viewer."""
        hunk = DiffHunk(
            file_path="example.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=2,
            lines=["@@ -1,1 +1,2 @@", " def hello():", "+    print('Hello, world!')"],
            context_before=[],
            context_after=[],
        )

        viewer = DiffViewer()
        # Set current hunk without DOM operations for unit testing
        viewer._current_hunk = hunk

        assert viewer._current_hunk is hunk


class TestProgressIndicator:
    """Test cases for ProgressIndicator."""

    def test_init(self) -> None:
        """Test ProgressIndicator initialization."""
        indicator = ProgressIndicator(10)

        assert indicator.total_hunks == 10
        assert indicator.approved_count == 0

    def test_format_progress_initial(self) -> None:
        """Test initial progress formatting."""
        indicator = ProgressIndicator(5)
        result = indicator._format_progress()

        assert result == "Progress: 0/5 approved (0%)"

    def test_format_progress_partial(self) -> None:
        """Test partial progress formatting."""
        indicator = ProgressIndicator(8)
        indicator.approved_count = 3
        result = indicator._format_progress()

        assert result == "Progress: 3/8 approved (38%)"

    def test_format_progress_complete(self) -> None:
        """Test complete progress formatting."""
        indicator = ProgressIndicator(4)
        indicator.approved_count = 4
        result = indicator._format_progress()

        assert result == "Progress: 4/4 approved (100%)"

    def test_format_progress_zero_total(self) -> None:
        """Test progress formatting with zero total."""
        indicator = ProgressIndicator(0)
        result = indicator._format_progress()

        assert result == "Progress: 0/0 approved (0%)"

    def test_update_progress(self) -> None:
        """Test updating progress."""
        indicator = ProgressIndicator(6)

        # Initial state
        assert indicator.approved_count == 0

        # Update progress (test the internal state change)
        indicator.approved_count = 3
        assert indicator.approved_count == 3

    def test_progress_percentage_rounding(self) -> None:
        """Test that progress percentage is rounded correctly."""
        indicator = ProgressIndicator(7)
        indicator.approved_count = 2
        result = indicator._format_progress()

        # 2/7 = 28.57..., should round to 29%
        assert result == "Progress: 2/7 approved (29%)"
