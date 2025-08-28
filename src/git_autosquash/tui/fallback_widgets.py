"""Enhanced widgets for fallback target selection scenarios."""

import asyncio
from typing import Dict, List, Optional, Union

from .ui_controllers import UILifecycleManager

from rich.syntax import Syntax
from rich.text import Text
from textual import events, on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, RadioButton, RadioSet, Static, Select, Checkbox

from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
from git_autosquash.commit_history_analyzer import (
    CommitInfo,
    CommitSelectionStrategy,
)

# Constants
MAX_FILE_COMMIT_OPTIONS = 5  # File-specific commits (filtered view)
MAX_ALL_COMMIT_OPTIONS = 10  # All commits (unfiltered view)
COMMIT_SUBJECT_TRUNCATE_LENGTH = 40  # Compact display


class FallbackHunkMappingWidget(Widget):
    """Enhanced hunk mapping widget that supports fallback target selection."""

    DEFAULT_CSS = """
    FallbackHunkMappingWidget {
        height: auto;
        margin: 0 0 1 0;
        border: round $primary;
        padding: 0;
        width: 100%;
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
    
    FallbackHunkMappingWidget > Vertical {
        height: auto;
        padding: 0;
    }
    
    FallbackHunkMappingWidget .hunk-header {
        background: $boost;
        color: $primary;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }
    
    FallbackHunkMappingWidget .fallback-header {
        background: $warning;
        color: $background;
        text-style: bold;
        padding: 0 1;
        height: 1;
    }
    
    FallbackHunkMappingWidget .commit-info {
        background: $surface;
        color: $text;
        padding: 0 1;
        height: 1;
    }
    
    FallbackHunkMappingWidget .fallback-note {
        background: $surface;
        color: $text-muted;
        padding: 0 1;
        text-style: italic;
        height: 1;
    }
    
    FallbackHunkMappingWidget .action-buttons {
        padding: 0;
        height: auto;
        margin: 0;
    }
    
    FallbackHunkMappingWidget .diff-content {
        background: $surface;
        border: solid $primary;
        padding: 0 1;
        margin: 0;
        height: auto;
        max-height: 8;
        overflow: auto;
    }
    
    FallbackHunkMappingWidget RadioSet {
        height: auto;
        width: 100%;
        margin: 0;
        padding: 0;
    }
    
    FallbackHunkMappingWidget RadioButton {
        height: 1;
        width: 100%;
        margin: 0;
        padding: 0;
    }
    
    /* Visibility control for commit filtering */
    FallbackHunkMappingWidget RadioButton.file-commit {
        display: block;
    }
    
    FallbackHunkMappingWidget RadioButton.all-commit {
        display: none;  /* Hidden by default (filtered state) */
    }
    
    /* When show all commits is enabled, show all commits */
    FallbackHunkMappingWidget.show-all RadioButton.all-commit {
        display: block;
    }
    
    FallbackHunkMappingWidget Horizontal {
        height: auto;
        margin: 0;
        padding: 0;
    }
    
    FallbackHunkMappingWidget Checkbox {
        min-height: 1;
        width: auto;
        margin: 0 1 0 0;
        padding: 0;
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
        commit_analyzer=None,
        is_first_widget: bool = False,
        **kwargs,
    ) -> None:
        """Initialize fallback hunk mapping widget.

        Args:
            mapping: The hunk to commit mapping to display
            commit_infos: List of CommitInfo objects for fallback candidates
            commit_analyzer: CommitHistoryAnalyzer for getting different commit sets
            is_first_widget: True if this is the first widget (for initial focus)
        """
        super().__init__(**kwargs)
        self.mapping = mapping
        self.commit_analyzer = commit_analyzer
        self.is_fallback = mapping.needs_user_selection
        self.is_first_widget = is_first_widget
        self.show_all_commits = False  # Track filter state

        # Initialize UI lifecycle management
        self.ui_manager = UILifecycleManager(self)

        # Always get both filtered and all commits for visibility-based filtering
        self.file_commits: List[CommitInfo] = []
        self.all_commits: List[CommitInfo] = []

        if commit_analyzer:
            # Get file-specific commits (filtered)
            self.file_commits = commit_analyzer.get_commit_suggestions(
                CommitSelectionStrategy.FILE_RELEVANCE,
                target_file=mapping.hunk.file_path,
            )[:MAX_FILE_COMMIT_OPTIONS]

            # Get all recent commits (more commits for "show all" mode)
            self.all_commits = commit_analyzer.get_commit_suggestions(
                CommitSelectionStrategy.RECENCY
            )[:MAX_ALL_COMMIT_OPTIONS]
        elif commit_infos:
            # Use provided commits as file commits, limit all commits to same
            self.file_commits = commit_infos[:MAX_FILE_COMMIT_OPTIONS]
            self.all_commits = commit_infos[:MAX_ALL_COMMIT_OPTIONS]

        # Use file commits as initial display (default filtered state)
        self.commit_infos = self.file_commits

        # Create commit hash to index mapping for O(1) lookups
        self._commit_hash_to_id: Dict[str, str] = {}
        self._id_to_commit_hash: Dict[
            str, str
        ] = {}  # Reverse lookup for O(1) performance
        self._file_commit_hashes = {c.commit_hash for c in self.file_commits}
        self._current_commit_list = self.commit_infos

    async def on_mount(self) -> None:
        """Handle widget mounting using event-driven lifecycle management."""
        # Advance to mounted state
        self.ui_manager.advance_to_mounted()

        try:
            # Focus targets will be registered in _advance_ui_states after DOM is fully ready

            # Action selector registration will also happen in _advance_ui_states

            # Register cleanup for unmount
            self.ui_manager.register_cleanup_callback(self._cleanup_widget_resources)

            # Register focus sync callback to run after UI is fully assembled
            if not self.mapping.needs_user_selection:
                self.ui_manager.register_ready_callback(self._sync_focus_after_assembly)

            if self.is_first_widget:
                self.ui_manager.register_ready_callback(self._set_initial_focus)

            # Use call_after_refresh to ensure DOM is ready, then advance states
            self.call_after_refresh(self._advance_ui_states)

        except Exception as e:
            self.log.error(f"Error during widget mount: {e}")
            # Still advance states to prevent hanging
            self.call_after_refresh(self._advance_ui_states)

    def _advance_ui_states(self) -> None:
        """Advance UI states after DOM is ready."""
        try:
            # Register RadioSet targets for focus management after DOM is ready
            target_selector = self.query_one("#target-selector", RadioSet)
            if target_selector:
                self.ui_manager.focus_controller.register_focus_target(
                    "target-selector", target_selector
                )

            # Register action selector if present
            try:
                action_selector = self.query_one("#action-selector", RadioSet)
                if action_selector:
                    self.ui_manager.focus_controller.register_focus_target(
                        "action-selector", action_selector
                    )
            except (NoMatches, AttributeError):
                # Action selector might not exist in all scenarios - this is expected
                pass

            # Now advance to ready states
            self.ui_manager.advance_to_focus_ready()
            self.ui_manager.advance_to_scroll_ready()
        except Exception as e:
            self.log.error(f"Error advancing UI states: {e}")

    def _sync_focus_after_assembly(self) -> None:
        """Sync focus to selected RadioButton after UI is fully assembled."""

        async def sync_focus():
            try:
                # Wait for UI to be fully ready
                await self.ui_manager.focus_controller.wait_for_focus_ready()

                # Find the target selector
                target_selector = self.query_one("#target-selector", RadioSet)

                # Find the button marked as target (has _is_target attribute)
                all_buttons = target_selector.query("RadioButton").results()
                target_button = None

                for button in all_buttons:
                    if hasattr(button, "value") and button.value:
                        target_button = button
                        break

                if target_button:
                    # Focus FIRST (while value=False), then set value=True
                    target_button.value = False
                    target_button.focus()
                    target_button.value = True
                    self.log.debug(
                        f"Focused and selected target button: {target_button.id}"
                    )

            except Exception as e:
                self.log.error(f"Error syncing focus after assembly: {e}")

        asyncio.create_task(sync_focus())

    def _set_initial_focus(self) -> None:
        """Set initial focus for first widget."""

        async def set_focus():
            try:
                # Wait for focus system to be ready
                await self.ui_manager.focus_controller.wait_for_focus_ready()
                # Set focus to action selector or target selector (only for first widget)
                if self.is_first_widget:
                    action_selector = (
                        self.ui_manager.focus_controller.focus_targets.get(
                            "action-selector"
                        )
                    )
                    if action_selector and hasattr(action_selector, "focus"):
                        action_selector.focus()
                    else:
                        target_selector = (
                            self.ui_manager.focus_controller.focus_targets.get(
                                "target-selector"
                            )
                        )
                        if target_selector and hasattr(target_selector, "focus"):
                            target_selector.focus()
            except Exception as e:
                self.log.error(f"Error setting initial focus: {e}")

        # Create and run the async task
        asyncio.create_task(set_focus())

    def _cleanup_widget_resources(self) -> None:
        """Clean up widget-specific resources."""
        # Clear commit hash mappings
        self._commit_hash_to_id.clear()
        self._id_to_commit_hash.clear()
        self._file_commit_hashes.clear()

    def on_unmount(self) -> None:
        """Handle widget unmounting with proper cleanup."""
        if hasattr(self, "ui_manager"):
            self.ui_manager.cleanup()

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

            # Diff content - full width display
            yield self._create_diff_display()

            # Compact target selection header - only show if needed
            if self.mapping.needs_user_selection:
                yield Static("Select target:", classes="commit-info")
            elif not self.commit_infos:
                # Only show commit info if no selection UI will be shown
                commit_hash = self.mapping.target_commit or "unknown"
                yield Static(
                    f"→ {commit_hash[:8]} ({self.mapping.confidence})",
                    classes="commit-info",
                )

            # Compact checkbox for commit filter (only if analyzer available and we have commits)
            if self.commit_analyzer and (self.all_commits or self.file_commits):
                yield Checkbox(
                    "Show all commits", id="show-all-commits", value=False, compact=True
                )

            # RadioSet with commit options using proper Textual patterns
            with RadioSet(id="target-selector"):
                # Add ALL commits but use CSS classes to control visibility
                if self.all_commits:
                    target_hash = self.mapping.target_commit

                    for i, commit_info in enumerate(self.all_commits):
                        label = self._format_commit_option(commit_info)
                        commit_id = f"commit-{i}"

                        # Store hash mapping for event handling (maintain both directions for O(1) lookup)
                        self._commit_hash_to_id[commit_info.commit_hash] = commit_id
                        self._id_to_commit_hash[commit_id] = commit_info.commit_hash
                        self._id_to_commit_hash[commit_id] = commit_info.commit_hash

                        # Set value=True for target commit (proper Textual pattern)
                        is_target = (
                            commit_info.commit_hash == target_hash
                            and not self.mapping.needs_user_selection
                        )

                        # Add CSS class based on whether this commit is file-relevant
                        is_file_relevant = (
                            commit_info.commit_hash in self._file_commit_hashes
                        )
                        css_classes = (
                            "file-commit" if is_file_relevant else "all-commit"
                        )

                        yield RadioButton(
                            label, id=commit_id, value=is_target, classes=css_classes
                        )

                # If no commits at all, create fallback option
                elif self.commit_infos:
                    # Legacy fallback for when we have commit_infos but no all_commits
                    target_hash = self.mapping.target_commit
                    for i, commit_info in enumerate(
                        self.commit_infos[:MAX_FILE_COMMIT_OPTIONS]
                    ):
                        label = self._format_commit_option(commit_info)
                        commit_id = f"commit-{i}"
                        self._commit_hash_to_id[commit_info.commit_hash] = commit_id
                        self._id_to_commit_hash[commit_id] = commit_info.commit_hash
                        is_target = (
                            commit_info.commit_hash == target_hash
                            and not self.mapping.needs_user_selection
                        )
                        yield RadioButton(
                            label, id=commit_id, value=is_target, classes="file-commit"
                        )
                else:
                    # Absolute fallback option
                    existing_hash = self.mapping.target_commit or "existing"
                    self._commit_hash_to_id[existing_hash] = "existing"
                    self._id_to_commit_hash["existing"] = existing_hash
                    yield RadioButton(
                        "Use existing target commit",
                        id="existing",
                        value=not self.mapping.needs_user_selection,
                        classes="file-commit",
                    )

            # Separate accept/ignore buttons below the commit list
            with RadioSet(id="action-selector", classes="action-buttons"):
                # Default to accept for auto-detected targets
                default_accept = not self.mapping.needs_user_selection

                yield RadioButton(
                    "Accept selected commit", id="accept-action", value=default_accept
                )
                yield RadioButton(
                    "Ignore (keep in working tree)", id="ignore-action", value=False
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
        """Create display for existing commit info (legacy - now handled by target selector)."""
        if self.mapping.target_commit:
            commit_summary = f"→ {self.mapping.target_commit[:8]} "
            confidence_class = f"confidence-{self.mapping.confidence}"
            commit_info = f"{commit_summary} ({self.mapping.confidence} confidence)"
        else:
            commit_info = "→ No target commit found"
            confidence_class = "confidence-low"

        return Static(commit_info, classes=f"commit-info {confidence_class}")

    def _get_commit_hash_from_button_id(self, button_id: str) -> Optional[str]:
        """Get commit hash from button ID using O(1) lookup."""
        # Use reverse lookup for O(1) performance
        return self._id_to_commit_hash.get(button_id)

    def _format_commit_option(self, commit_info: CommitInfo) -> str:
        """Format commit info with dynamic width calculation."""
        available_width = self._calculate_available_width()

        merge_marker = " (merge)" if commit_info.is_merge else ""
        hash_prefix = f"{commit_info.short_hash}: "

        # Reserve space for hash, merge marker, and RadioButton UI chrome
        # Be more generous with space allocation
        ui_chrome_space = 2  # Reduced from 5 to give more space to text
        subject_space = (
            available_width - len(hash_prefix) - len(merge_marker) - ui_chrome_space
        )

        subject = commit_info.subject
        if len(subject) > subject_space and subject_space > 10:
            subject = subject[: subject_space - 3] + "..."

        return f"{hash_prefix}{subject}{merge_marker}"

    def _calculate_available_width(self) -> int:
        """Calculate available width for commit descriptions."""
        try:
            # Try multiple methods to get terminal width
            terminal_width = None

            # Method 1: Through app's console
            if hasattr(self.app, "console") and self.app.console:
                terminal_width = self.app.console.width

            # Method 2: Through screen size
            elif (
                hasattr(self, "screen") and self.screen and hasattr(self.screen, "size")
            ):
                terminal_width = self.screen.size.width

            # Method 3: Through app's screen
            elif (
                hasattr(self.app, "screen")
                and self.app.screen
                and hasattr(self.app.screen, "size")
            ):
                terminal_width = self.app.screen.size.width

            if terminal_width is None or terminal_width < 40:
                terminal_width = 80  # Default fallback

            # Be aggressive with space usage - only subtract minimal UI chrome
            available = max(60, terminal_width - 4)  # Increased minimum to 60

            return available
        except Exception:
            return 80  # Safe fallback

    def _create_diff_display(self) -> Static:
        """Create diff display widget showing the hunk content."""
        # Format diff content
        diff_lines = []
        for line in self.mapping.hunk.lines:
            diff_lines.append(line)

        diff_text = "\n".join(diff_lines)

        # Create syntax highlighted content
        try:
            # Use diff syntax highlighting for diff output
            syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
            content: Union[Syntax, Text] = syntax
        except (ImportError, ValueError, AttributeError):
            # Fallback to plain text if syntax highlighting fails
            content = Text(diff_text)

        return Static(content, classes="diff-content")

    def on_click(self, event: events.Click) -> None:
        """Handle click events."""
        self.selected = True
        self.post_message(self.Selected(self.mapping))

    @on(Checkbox.Changed, "#show-all-commits")
    def on_show_all_commits_changed(self, event: Checkbox.Changed) -> None:
        """Handle show all commits toggle by updating visibility."""
        self.show_all_commits = event.value

        # Toggle CSS class to control visibility of all-commit RadioButtons
        if self.show_all_commits:
            self.add_class("show-all")
        else:
            self.remove_class("show-all")

        # Force refresh to apply visibility changes
        self.refresh()

    @on(RadioSet.Changed)
    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle both commit selection and action selection."""
        if not event.pressed:
            return

        if event.radio_set.id == "target-selector":
            # Commit selection changed - get hash from button ID
            button_id = event.pressed.id or ""
            commit_hash = self._get_commit_hash_from_button_id(button_id)
            if commit_hash:
                self._handle_commit_selection(commit_hash)
        elif event.radio_set.id == "action-selector":
            # Accept/ignore selection changed - use button ID
            action_id = event.pressed.id or ""
            if action_id == "accept-action":
                self._handle_approve_selection()
            elif action_id == "ignore-action":
                self._handle_ignore_selection()

    def _handle_ignore_selection(self) -> None:
        """Handle ignore selection consistently."""
        self.ignored = True
        self.approved = False
        self.post_message(self.IgnoreChanged(self.mapping, True))
        self.post_message(self.ApprovalChanged(self.mapping, False))

    def _handle_approve_selection(self) -> None:
        """Handle approve selection for existing target."""
        self.approved = True
        self.ignored = False
        self.post_message(self.ApprovalChanged(self.mapping, True))
        self.post_message(self.IgnoreChanged(self.mapping, False))

    def _handle_commit_selection(self, commit_hash: str) -> None:
        """Handle commit selection - just update the target, don't auto-approve."""
        self.mapping.target_commit = commit_hash
        self.mapping.needs_user_selection = False
        self.post_message(self.TargetSelected(self.mapping, commit_hash))
        # Don't automatically approve - user must explicitly choose accept or ignore

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
            if (
                select_widget.value
                and select_widget.value != ""
                and isinstance(select_widget.value, str)
            ):
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
