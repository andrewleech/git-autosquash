"""Custom widgets for git-autosquash TUI."""

from typing import Optional, Union

from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Checkbox, Static

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk


class HunkMappingWidget(Widget):
    """Widget displaying a single hunk to commit mapping."""

    DEFAULT_CSS = """
    HunkMappingWidget {
        height: auto;
        margin: 1 0;
        border: round $primary;
    }
    
    HunkMappingWidget.selected {
        border: thick $accent;
    }
    
    HunkMappingWidget .hunk-header {
        background: $primary-background;
        color: $primary;
        text-style: bold;
        padding: 0 1;
    }
    
    HunkMappingWidget .commit-info {
        background: $secondary-background;
        color: $text;
        padding: 0 1;
    }
    
    HunkMappingWidget .confidence-high {
        color: $success;
    }
    
    HunkMappingWidget .confidence-medium {
        color: $warning;
    }
    
    HunkMappingWidget .confidence-low {
        color: $error;
    }
    """

    selected = reactive(False)
    approved = reactive(False)  # Default to unapproved for safety
    ignored = reactive(False)  # New state for ignoring hunks

    class Selected(Message):
        """Message sent when hunk is selected."""

        def __init__(self, mapping: HunkTargetMapping) -> None:
            self.mapping = mapping
            super().__init__()

    class ApprovalChanged(Message):
        """Message sent when approval status changes."""

        def __init__(self, mapping: HunkTargetMapping, approved: bool) -> None:
            self.mapping = mapping
            self.approved = approved
            super().__init__()

    class IgnoreChanged(Message):
        """Message sent when ignore status changes."""

        def __init__(self, mapping: HunkTargetMapping, ignored: bool) -> None:
            self.mapping = mapping
            self.ignored = ignored
            super().__init__()

    def __init__(self, mapping: HunkTargetMapping, **kwargs) -> None:
        """Initialize hunk mapping widget.

        Args:
            mapping: The hunk to commit mapping to display
        """
        super().__init__(**kwargs)
        self.mapping = mapping

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        with Vertical():
            # Header with file and hunk info
            hunk_info = f"{self.mapping.hunk.file_path} @@ {self._format_hunk_range()}"
            yield Static(hunk_info, classes="hunk-header")

            # Target commit info
            if self.mapping.target_commit:
                commit_summary = f"→ {self.mapping.target_commit[:8]} "
                confidence_class = f"confidence-{self.mapping.confidence}"
                commit_info = f"{commit_summary} ({self.mapping.confidence} confidence)"
            else:
                commit_info = "→ No target commit found"
                confidence_class = "confidence-low"

            yield Static(commit_info, classes=f"commit-info {confidence_class}")

            # Action selection with separate concerns
            with Horizontal():
                yield Checkbox(
                    "Approve for squashing", value=self.approved, id="approve-checkbox"
                )
                yield Checkbox(
                    "Ignore (keep in working tree)",
                    value=self.ignored,
                    id="ignore-checkbox",
                )

    def _format_hunk_range(self) -> str:
        """Format hunk line range for display."""
        hunk = self.mapping.hunk
        return f"-{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count}"

    def on_click(self, event: events.Click) -> None:
        """Handle click events."""
        self.selected = True
        self.post_message(self.Selected(self.mapping))

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes."""
        if event.checkbox.id == "approve-checkbox":
            self.approved = event.value
            self.post_message(self.ApprovalChanged(self.mapping, event.value))
        elif event.checkbox.id == "ignore-checkbox":
            self.ignored = event.value
            self.post_message(self.IgnoreChanged(self.mapping, event.value))

    def watch_selected(self, selected: bool) -> None:
        """React to selection changes."""
        self.set_class(selected, "selected")


class DiffViewer(Widget):
    """Widget for displaying diff content with syntax highlighting."""

    DEFAULT_CSS = """
    DiffViewer {
        border: round $primary;
        padding: 1;
    }
    
    DiffViewer .diff-header {
        color: $text-muted;
        text-style: bold;
    }
    """

    def __init__(self, **kwargs) -> None:
        """Initialize diff viewer."""
        super().__init__(**kwargs)
        self._current_hunk: Optional[DiffHunk] = None

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        yield Static("Select a hunk to view diff", id="diff-content")

    def show_hunk(self, hunk: DiffHunk) -> None:
        """Display diff content for a hunk.

        Args:
            hunk: The hunk to display
        """
        self._current_hunk = hunk

        # Format diff content
        diff_lines = []
        for line in hunk.lines:
            diff_lines.append(line)

        diff_text = "\n".join(diff_lines)

        # Create syntax highlighted content
        try:
            # Use diff syntax highlighting regardless of file extension
            # since we're showing diff output, not the original file
            syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
            content: Union[Syntax, Text] = syntax
        except (ImportError, ValueError, AttributeError):
            # Fallback to plain text if syntax highlighting fails or is unavailable
            content = Text(diff_text)

        # Update the display
        diff_widget = self.query_one("#diff-content", Static)
        diff_widget.update(content)

    def _get_language_from_file(self, file_path: str) -> str:
        """Get language identifier from file extension.

        Args:
            file_path: Path to the file

        Returns:
            Language identifier for syntax highlighting
        """
        extension = file_path.split(".")[-1].lower()

        language_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "jsx": "jsx",
            "tsx": "tsx",
            "java": "java",
            "c": "c",
            "cpp": "cpp",
            "cc": "cpp",
            "h": "c",
            "hpp": "cpp",
            "rs": "rust",
            "go": "go",
            "rb": "ruby",
            "php": "php",
            "sh": "bash",
            "bash": "bash",
            "zsh": "bash",
            "fish": "bash",
            "ps1": "powershell",
            "html": "html",
            "css": "css",
            "scss": "scss",
            "sass": "sass",
            "less": "less",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "xml": "xml",
            "md": "markdown",
            "sql": "sql",
        }

        return language_map.get(extension, "text")


class ProgressIndicator(Widget):
    """Widget showing progress through hunk approvals."""

    DEFAULT_CSS = """
    ProgressIndicator {
        height: 1;
        background: $panel;
        color: $text;
        text-align: center;
    }
    """

    def __init__(self, total_hunks: int, **kwargs) -> None:
        """Initialize progress indicator.

        Args:
            total_hunks: Total number of hunks to process
        """
        super().__init__(**kwargs)
        self.total_hunks = total_hunks
        self.approved_count = 0
        self.ignored_count = 0

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        yield Static(self._format_progress(), id="progress-text")

    def update_progress(self, approved_count: int, ignored_count: int = 0) -> None:
        """Update the progress display.

        Args:
            approved_count: Number of hunks approved so far
            ignored_count: Number of hunks ignored so far
        """
        self.approved_count = approved_count
        self.ignored_count = ignored_count
        progress_widget = self.query_one("#progress-text", Static)
        progress_widget.update(self._format_progress())

    def _format_progress(self) -> str:
        """Format progress text."""
        total_processed = self.approved_count + self.ignored_count
        percentage = (
            (total_processed / self.total_hunks * 100) if self.total_hunks > 0 else 0
        )
        status_parts = []
        if self.approved_count > 0:
            status_parts.append(f"{self.approved_count} squash")
        if self.ignored_count > 0:
            status_parts.append(f"{self.ignored_count} ignore")

        if status_parts:
            status = f"({', '.join(status_parts)})"
        else:
            status = ""

        return f"Progress: {total_processed}/{self.total_hunks} selected {status} ({percentage:.0f}%)"
