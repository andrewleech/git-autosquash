"""Enhanced widgets for fallback target selection scenarios."""

from typing import List, Optional

from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Checkbox, RadioButton, RadioSet, Static, Select

from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
from git_autosquash.commit_history_analyzer import CommitInfo

# Constants
MAX_COMMIT_OPTIONS = 10
COMMIT_SUBJECT_TRUNCATE_LENGTH = 50


class FallbackHunkMappingWidget(Widget):
    """Enhanced hunk mapping widget that supports fallback target selection."""

    DEFAULT_CSS = """
    FallbackHunkMappingWidget {
        height: auto;
        margin: 1 0;
        border: round $primary;
    }
    
    FallbackHunkMappingWidget.selected {
        border: thick $accent;
    }
    
    FallbackHunkMappingWidget.fallback {
        border: round $warning;
    }
    
    FallbackHunkMappingWidget.fallback.selected {
        border: thick $warning;
    }
    
    FallbackHunkMappingWidget .hunk-header {
        background: $boost;
        color: $primary;
        text-style: bold;
        padding: 0 1;
    }
    
    FallbackHunkMappingWidget .fallback-header {
        background: $warning;
        color: $background;
        text-style: bold;
        padding: 0 1;
    }
    
    FallbackHunkMappingWidget .commit-info {
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    
    FallbackHunkMappingWidget .fallback-note {
        background: $surface;
        color: $text-muted;
        padding: 0 1;
        text-style: italic;
    }
    
    FallbackHunkMappingWidget .confidence-high {
        color: $success;
    }
    
    FallbackHunkMappingWidget .confidence-medium {
        color: $warning;
    }
    
    FallbackHunkMappingWidget .confidence-low {
        color: $error;
    }
    """

    selected = reactive(False)
    approved = reactive(False)
    ignored = reactive(False)

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

    class TargetSelected(Message):
        """Message sent when a fallback target is selected."""

        def __init__(self, mapping: HunkTargetMapping, target_commit: str) -> None:
            self.mapping = mapping
            self.target_commit = target_commit
            super().__init__()

    def __init__(
        self,
        mapping: HunkTargetMapping,
        commit_infos: Optional[List[CommitInfo]] = None,
        **kwargs,
    ) -> None:
        """Initialize fallback hunk mapping widget.

        Args:
            mapping: The hunk to commit mapping to display
            commit_infos: List of CommitInfo objects for fallback candidates
        """
        super().__init__(**kwargs)
        self.mapping = mapping
        self.commit_infos = commit_infos or []
        self.is_fallback = mapping.needs_user_selection

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        with Vertical():
            # Header with file and hunk info
            hunk_info = f"{self.mapping.hunk.file_path} @@ {self._format_hunk_range()}"

            if self.is_fallback:
                yield Static(hunk_info, classes="fallback-header")
                yield Static(self._get_fallback_description(), classes="fallback-note")
            else:
                yield Static(hunk_info, classes="hunk-header")

            # Target commit info or selection
            if self.is_fallback and self.commit_infos:
                yield self._create_target_selector()
            else:
                yield self._create_commit_info_display()

            # Action selection
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

    def _get_fallback_description(self) -> str:
        """Get description for fallback scenario."""
        if self.mapping.targeting_method == TargetingMethod.FALLBACK_NEW_FILE:
            return "New file - no git history to analyze"
        elif self.mapping.targeting_method == TargetingMethod.FALLBACK_EXISTING_FILE:
            return "No target found via blame analysis"
        elif self.mapping.targeting_method == TargetingMethod.FALLBACK_CONSISTENCY:
            return "Using same target as previous hunk from this file"
        else:
            return "Manual target selection required"

    def _create_commit_info_display(self) -> Static:
        """Create display for existing commit info."""
        if self.mapping.target_commit:
            commit_summary = f"→ {self.mapping.target_commit[:8]} "
            confidence_class = f"confidence-{self.mapping.confidence}"
            commit_info = f"{commit_summary} ({self.mapping.confidence} confidence)"
        else:
            commit_info = "→ No target commit found"
            confidence_class = "confidence-low"

        return Static(commit_info, classes=f"commit-info {confidence_class}")

    def _create_target_selector(self) -> Widget:
        """Create target selection widget for fallback scenarios."""

        class TargetSelectorWidget(Vertical):
            """Proper nested widget for target selection."""

            def __init__(self, commit_infos: List[CommitInfo]):
                super().__init__()
                self.commit_infos = commit_infos

            def compose(self) -> ComposeResult:
                yield Static("Select target commit:", classes="commit-info")

                with RadioSet(id="target-selector"):
                    yield RadioButton(
                        "Ignore (keep in working tree)", id="ignore-target"
                    )

                    for i, commit_info in enumerate(
                        self.commit_infos[:MAX_COMMIT_OPTIONS]
                    ):
                        label = self._format_commit_option(commit_info)
                        yield RadioButton(
                            label, id=f"commit-{i}", value=commit_info.commit_hash
                        )

            def _format_commit_option(self, commit_info: CommitInfo) -> str:
                """Format commit info for display in selection."""
                merge_marker = " (merge)" if commit_info.is_merge else ""
                subject = commit_info.subject
                if len(subject) > COMMIT_SUBJECT_TRUNCATE_LENGTH:
                    subject = subject[:COMMIT_SUBJECT_TRUNCATE_LENGTH] + "..."
                return f"{commit_info.short_hash}: {subject}{merge_marker}"

        return TargetSelectorWidget(self.commit_infos)

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

    @on(RadioSet.Changed)
    def on_target_selection_changed(self, event: RadioSet.Changed) -> None:
        """Handle target commit selection changes."""
        if not event.pressed:
            return

        if event.pressed.id == "ignore-target":
            self.ignored = True
            self.approved = False
            self.post_message(self.IgnoreChanged(self.mapping, True))
            self.post_message(self.ApprovalChanged(self.mapping, False))
        else:
            # Extract commit hash from radio button value
            target_commit = event.pressed.value
            if target_commit:
                self.mapping.target_commit = target_commit
                self.mapping.needs_user_selection = False
                self.approved = True
                self.ignored = False
                self.post_message(self.TargetSelected(self.mapping, target_commit))
                self.post_message(self.ApprovalChanged(self.mapping, True))
                self.post_message(self.IgnoreChanged(self.mapping, False))

    def watch_selected(self, selected: bool) -> None:
        """React to selection changes."""
        self.set_class(selected, "selected")
        if self.is_fallback:
            self.set_class(True, "fallback")


class BatchSelectionWidget(Widget):
    """Widget for batch selection operations across multiple hunks."""

    DEFAULT_CSS = """
    BatchSelectionWidget {
        height: auto;
        margin: 1 0;
        padding: 1;
        border: round $surface;
        background: $surface;
    }
    
    BatchSelectionWidget .batch-title {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    class BatchTargetSelected(Message):
        """Message sent when a batch target is selected."""

        def __init__(self, target_commit: str, apply_to_all: bool = False) -> None:
            self.target_commit = target_commit
            self.apply_to_all = apply_to_all
            super().__init__()

    def __init__(self, commit_infos: List[CommitInfo], **kwargs) -> None:
        """Initialize batch selection widget.

        Args:
            commit_infos: List of available commit options
        """
        super().__init__(**kwargs)
        self.commit_infos = commit_infos

    def compose(self) -> ComposeResult:
        """Compose the widget layout."""
        yield Static("Batch Actions", classes="batch-title")

        with Horizontal():
            yield Button(
                "Ignore All Fallbacks", variant="default", id="ignore-all-fallbacks"
            )

        with Horizontal():
            yield Static("Assign all to: ", shrink=True)
            # Create select widget with commit options
            options = [("(Select target)", "")]
            for commit_info in self.commit_infos[:10]:
                label = f"{commit_info.short_hash} {commit_info.subject}"
                if commit_info.is_merge:
                    label += " (merge)"
                options.append((label, commit_info.commit_hash))

            yield Select(options, value="", id="batch-target-select")
            yield Button("Apply to All", variant="primary", id="apply-to-all")

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "ignore-all-fallbacks":
            self.post_message(self.BatchTargetSelected("ignore", apply_to_all=True))
        elif event.button.id == "apply-to-all":
            select_widget = self.query_one("#batch-target-select", Select)
            if select_widget.value and select_widget.value != "":
                self.post_message(
                    self.BatchTargetSelected(select_widget.value, apply_to_all=True)
                )


class FallbackSectionSeparator(Widget):
    """Visual separator between blame matches and fallback scenarios."""

    DEFAULT_CSS = """
    FallbackSectionSeparator {
        height: 3;
        margin: 2 0;
    }
    
    FallbackSectionSeparator .separator-line {
        background: $warning;
        color: $background;
        text-align: center;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the separator."""
        yield Static("", classes="separator-line")
        yield Static(
            "── Fallback Scenarios (Manual Selection Required) ──",
            classes="separator-line",
        )
        yield Static("", classes="separator-line")


class EnhancedProgressIndicator(Widget):
    """Enhanced progress indicator showing blame matches vs fallbacks."""

    DEFAULT_CSS = """
    EnhancedProgressIndicator {
        height: 3;
        margin: 1 0;
        padding: 0 1;
    }
    
    EnhancedProgressIndicator .progress-line {
        text-align: center;
    }
    
    EnhancedProgressIndicator .progress-blame {
        color: $success;
    }
    
    EnhancedProgressIndicator .progress-fallback {
        color: $warning;
    }
    """

    def __init__(
        self, total_hunks: int, blame_matches: int, fallback_count: int, **kwargs
    ) -> None:
        """Initialize enhanced progress indicator.

        Args:
            total_hunks: Total number of hunks
            blame_matches: Number of hunks with blame matches
            fallback_count: Number of hunks needing fallback selection
        """
        super().__init__(**kwargs)
        self.total_hunks = total_hunks
        self.blame_matches = blame_matches
        self.fallback_count = fallback_count

    def compose(self) -> ComposeResult:
        """Compose the progress display."""
        blame_text = Text(f"{self.blame_matches} blame matches", style="green")
        fallback_text = Text(f"{self.fallback_count} need selection", style="yellow")
        total_text = Text(f"of {self.total_hunks} total")

        progress_text = Text.assemble(
            blame_text, " • ", fallback_text, " • ", total_text
        )

        yield Static("Progress Summary", classes="progress-line")
        yield Static(progress_text, classes="progress-line")
        yield Static("", classes="progress-line")
