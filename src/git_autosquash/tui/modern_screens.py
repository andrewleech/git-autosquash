"""Screen implementations with 3-panel layout."""

from typing import Any, Dict, List, Optional, Union

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Static,
    ListItem,
    ListView,
    RadioButton,
    RadioSet,
)

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.commit_history_analyzer import (
    CommitHistoryAnalyzer,
    CommitInfo,
    CommitSelectionStrategy,
)


class ModernApprovalScreen(Screen[Dict[str, Any]]):
    """3-panel approval screen.

    Layout:
    ┌─────────────────────────────────────────────────────────────┐
    │                        Header                               │
    ├─────────────────────┬───────────────────────────────────────┤
    │   Changes to Review │          Target Commits               │
    │   (Green border)    │          (Cyan border)                │
    │                     │                                       │
    │ • file1.py:10-15    │  ○ commit abc123 Fix typo             │
    │ • file2.js:5-8      │  ○ commit def456 Update logic         │
    │ • file3.py:20-25    │  ○ commit ghi789 Refactor             │
    │                     │                                       │
    ├─────────────────────┴───────────────────────────────────────┤
    │                     Preview                                 │
    │                   (White border)                            │
    │                                                             │
    │  @@ -10,3 +10,3 @@                                          │
    │  -    old line                                              │
    │  +    new line                                              │
    │                                                             │
    ├─────────────────────────────────────────────────────────────┤
    │                    [Continue] [Cancel]                     │
    └─────────────────────────────────────────────────────────────┘

    Workflow:
    1. User selects a change from left panel
    2. Right panel shows suggested target commits for that change
    3. Bottom panel shows diff preview of the selected change
    4. User can select a target commit from right panel (updates the mapping)
    5. User continues to next change or clicks Continue when done
    """

    BINDINGS = [
        Binding("enter", "continue", "Continue", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("j,down", "next_change", "Next Change", show=False),
        Binding("k,up", "prev_change", "Previous Change", show=False),
    ]

    # layout CSS with proper bordered panels
    CSS = """
    /* 3-panel layout */
    #main-container {
        layout: vertical;
        height: 100%;
    }

    #panels-row {
        layout: horizontal;
        height: 1fr;
    }

    #changes-panel {
        width: 40%;
        height: 100%;
        margin: 0 1 0 0;
        border: round green;
        border-title-style: bold;
        border-title-color: white;
        padding: 1;
    }

    #targets-panel {
        width: 60%;
        height: 100%;
        margin: 0 0 0 1;
        border: round cyan;
        border-title-style: bold;
        border-title-color: white;
        padding: 1;
        overflow: auto scroll;
    }

    #preview-panel {
        height: 1fr;
        margin: 1 0;
        border: round white;
        border-title-style: bold;
        border-title-color: white;
        padding: 1;
    }

    #action-buttons {
        height: 3;
        layout: horizontal;
        align: center middle;
        margin-bottom: 1;
    }

    #action-buttons Button {
        margin: 0 1;
        min-width: 15;
    }

    /* Changes list styling */
    #changes-list {
        height: 100%;
        width: 100%;
    }

    #changes-list ListItem {
        padding: 0 1;
        height: 1;
        width: 100%;
        min-width: 100%;
        text-wrap: nowrap;
    }

    #changes-list ListItem.--highlight {
        background: $surface-lighten-1;
        border-left: thick $primary;
        color: $text;
    }

    #changes-list ListItem Static {
        width: 100%;
        height: 1;
    }

    /* Target commits styling */
    #targets-container {
        height: 100%;
        width: 100%;
    }

    #targets-container RadioSet {
        height: 100%;
        width: 100%;
    }

    #targets-container RadioButton {
        padding: 0 1;
        height: 1;
        width: 100%;
        text-wrap: nowrap;
    }

    /* Auto-target styling */
    #targets-container RadioButton.auto-target {
        color: $success;
        text-style: bold;
    }
    
    /* Ignore option styling */
    #targets-container RadioButton.ignore-option {
        color: $warning;
        height: 2;
        margin-bottom: 1;
        padding: 0 1;
        border-bottom: thick $warning-muted;
        text-style: bold;
        text-wrap: wrap;
    }

    /* Preview panel styling */
    #diff-preview {
        height: 100%;
        width: 100%;
        overflow: auto;
    }
    """

    def __init__(
        self,
        mappings: List[HunkTargetMapping],
        commit_history_analyzer: CommitHistoryAnalyzer,
        **kwargs,
    ) -> None:
        """Initialize approval screen.

        Args:
            mappings: List of hunk to commit mappings to review
            commit_history_analyzer: Analyzer for generating commit suggestions
        """
        super().__init__(**kwargs)
        self.mappings = mappings
        self.commit_history_analyzer = commit_history_analyzer

        # Current state
        self.selected_mapping: Optional[HunkTargetMapping] = None
        self.current_targets: List[CommitInfo] = []

        # Final selections
        self.target_assignments: Dict[HunkTargetMapping, str] = {}
        self.ignored_mappings: List[HunkTargetMapping] = []

    def compose(self) -> ComposeResult:
        """Compose the 3-panel layout."""
        yield Header()

        with Container(id="main-container"):
            with Horizontal(id="panels-row"):
                # Left panel: Changes to Review (green border)
                with Container(id="changes-panel") as changes_container:
                    changes_container.border_title = "Changes to Review"
                    yield ListView(id="changes-list")

                # Right panel: Target Commits (cyan border)
                with Container(id="targets-panel") as targets_container:
                    targets_container.border_title = "Target Commits"
                    yield Vertical(id="targets-container")

            # Bottom panel: Preview (white border)
            with Container(id="preview-panel") as preview_container:
                preview_container.border_title = "Preview"
                yield Static("Select a change to view diff preview", id="diff-preview")

            # Action buttons
            with Horizontal(id="action-buttons"):
                yield Button("Continue", variant="success", id="continue-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

        yield Footer()

    async def on_mount(self) -> None:
        """Handle screen mounting."""
        # Populate changes list
        changes_list = self.query_one("#changes-list", ListView)
        for mapping in self.mappings:
            hunk = mapping.hunk
            # Format: "file.py:lines"
            change_text = f"{hunk.file_path}:{hunk.new_start}-{hunk.new_start + hunk.new_count - 1}"
            item = ChangeListItem(change_text, mapping)
            await changes_list.append(item)

        # Auto-select first change if available
        if self.mappings:
            changes_list.index = 0
            if changes_list.index is not None:
                await self._handle_change_selection(changes_list.index)

    @on(ListView.Highlighted)
    async def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle list item highlighting."""
        if event.list_view.id == "changes-list" and event.list_view.index is not None:
            await self._handle_change_selection(event.list_view.index)

    @on(RadioSet.Changed)
    async def on_radio_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio button selection in targets panel."""
        if event.radio_set.id == "targets-radio" and event.pressed:
            # Get the commit hash from the custom attribute
            if hasattr(event.pressed, "commit_hash"):
                selected_hash = event.pressed.commit_hash
                if self.selected_mapping:
                    if selected_hash == "ignore-hunk":
                        # Handle ignore selection
                        if self.selected_mapping not in self.ignored_mappings:
                            self.ignored_mappings.append(self.selected_mapping)
                        # Remove from target assignments if present
                        if self.selected_mapping in self.target_assignments:
                            del self.target_assignments[self.selected_mapping]
                    else:
                        # Handle commit selection
                        self.target_assignments[self.selected_mapping] = selected_hash
                        # Remove from ignored if present
                        if self.selected_mapping in self.ignored_mappings:
                            self.ignored_mappings.remove(self.selected_mapping)

    async def _handle_change_selection(self, index: int) -> None:
        """Handle selection of a change from the left panel."""
        if 0 <= index < len(self.mappings):
            self.selected_mapping = self.mappings[index]

            # Update targets panel
            await self._update_targets_panel()

            # Update preview panel
            await self._update_preview_panel()

    async def _update_targets_panel(self) -> None:
        """Update the targets panel with commits for the selected change."""
        if not self.selected_mapping:
            return

        # Get commit suggestions for this hunk
        mapping = self.selected_mapping
        if mapping.target_commit and not mapping.needs_user_selection:
            # Blame match - show the target commit plus suggestions
            strategy = CommitSelectionStrategy.FILE_RELEVANCE
        else:
            # Fallback case - show general suggestions
            strategy = CommitSelectionStrategy.RECENCY

        self.current_targets = self.commit_history_analyzer.get_commit_suggestions(
            strategy, mapping.hunk.file_path
        )[:20]  # Limit to 20 for UI performance

        # Update the targets container - recreate RadioSet each time
        targets_container = self.query_one("#targets-container", Vertical)

        # Clear existing RadioSet
        await targets_container.remove_children()

        # Create radio buttons for each commit
        radio_buttons = []
        selected_value: Optional[str] = None

        # Add ignore option at the top
        ignore_btn = RadioButton("🚫 Ignore (keep in working tree)")
        # Store commit hash as custom attribute for event handling (same pattern as commits)
        ignore_btn.commit_hash = "ignore-hunk"  # type: ignore[attr-defined]
        ignore_btn.add_class("ignore-option")

        # Check if this hunk is already ignored
        if mapping in self.ignored_mappings:
            ignore_btn._should_be_selected = True  # type: ignore[attr-defined]
            selected_value = "ignore-hunk"

        radio_buttons.append(ignore_btn)

        for commit_info in self.current_targets:
            # Check if this is the automatic blame target
            is_auto_target = (
                mapping.target_commit
                and commit_info.commit_hash == mapping.target_commit
            )

            # Format with confidence indicators at the end to maintain alignment
            if is_auto_target:
                confidence = getattr(mapping, "confidence", "unknown")
                if confidence == "high":
                    confidence_text = " ✓HIGH"
                elif confidence == "medium":
                    confidence_text = " ~MED"
                else:
                    confidence_text = " ?LOW"
            else:
                confidence_text = ""

            # Don't truncate - let the panel handle text wrapping and sizing
            subject = commit_info.subject
            commit_text = f"{commit_info.commit_hash[:7]} {subject}{confidence_text}"

            # Create radio button - always start unselected, let RadioSet manage selection
            radio_btn = RadioButton(commit_text)
            # Store commit hash as custom attribute for event handling
            radio_btn.commit_hash = commit_info.commit_hash  # type: ignore[attr-defined]

            if is_auto_target:
                radio_btn.add_class("auto-target")

            # Determine if this should be the selected one and mark it
            should_select = False

            # Priority 1: Existing user assignment (always takes precedence)
            if mapping in self.target_assignments:
                if self.target_assignments[mapping] == commit_info.commit_hash:
                    should_select = True
            # Priority 2: Auto-target (if no user assignment exists)
            elif mapping not in self.target_assignments and is_auto_target:
                should_select = True

            if should_select:
                # Mark this button for post-mount selection
                radio_btn._should_be_selected = True  # type: ignore[attr-defined]
                selected_value = commit_info.commit_hash

            radio_buttons.append(radio_btn)

        # Create new RadioSet with all buttons
        targets_radio = RadioSet(*radio_buttons, id="targets-radio")

        # Mount the RadioSet
        await targets_container.mount(targets_radio)

        # Apply selection after mounting if we have something to select
        if selected_value is not None:
            # Only record in target_assignments if it's not the ignore option
            if (
                selected_value != "ignore-hunk"
                and mapping not in self.target_assignments
            ):
                self.target_assignments[mapping] = selected_value

            # Use call_after_refresh to ensure proper timing for selection
            # self.call_after_refresh(self._sync_radio_selection)
            self._sync_radio_selection()

    def _sync_radio_selection(self) -> None:
        """Sync focus to selected RadioButton after mounting."""
        try:
            # Find the target RadioSet
            targets_radio = self.query_one("#targets-radio", RadioSet)

            # Find the button marked for selection
            all_buttons = targets_radio.query(RadioButton).results()
            target_button = None

            for button in all_buttons:
                if (
                    hasattr(button, "_should_be_selected")
                    and button._should_be_selected
                ):
                    target_button = button
                    break

            if target_button:
                # Let RadioSet handle the selection properly
                # target_button.pressed = target_button
                target_button.value = False
                target_button.focus()
                target_button.value = True

        except Exception:
            # Log error but don't fail - selection is not critical for basic functionality
            pass

    async def _update_preview_panel(self) -> None:
        """Update the preview panel with diff content for the selected change."""
        if not self.selected_mapping:
            return

        # Format diff similar to the enhanced app
        hunk = self.selected_mapping.hunk
        diff_lines = []

        # Add file header
        diff_lines.append(f"--- {hunk.file_path}")
        diff_lines.append(f"+++ {hunk.file_path}")
        diff_lines.append(
            f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
        )

        # Add context before if available
        for line in hunk.context_before:
            diff_lines.append(f" {line}")

        # Add hunk lines
        for line in hunk.lines:
            diff_lines.append(line)

        # Add context after if available
        for line in hunk.context_after:
            diff_lines.append(f" {line}")

        diff_text = "\n".join(diff_lines)

        # Update preview with syntax highlighting
        try:
            from rich.syntax import Syntax
            from rich.text import Text

            content: Union["Syntax", "Text"] = Syntax(
                diff_text, "diff", theme="monokai", line_numbers=False
            )
        except (ImportError, ValueError):
            from rich.text import Text

            content = Text(diff_text)

        preview = self.query_one("#diff-preview", Static)
        preview.update(content)

    def action_continue(self) -> None:
        """Continue with current selections."""
        result = {"targets": self.target_assignments, "ignored": self.ignored_mappings}
        self.dismiss(result)

    def action_cancel(self) -> None:
        """Cancel the operation."""
        self.dismiss(None)

    def action_next_change(self) -> None:
        """Navigate to next change."""
        changes_list = self.query_one("#changes-list", ListView)
        if (
            changes_list.index is not None
            and changes_list.index < len(self.mappings) - 1
        ):
            changes_list.index += 1

    def action_prev_change(self) -> None:
        """Navigate to previous change."""
        changes_list = self.query_one("#changes-list", ListView)
        if changes_list.index is not None and changes_list.index > 0:
            changes_list.index -= 1

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "continue-btn":
            self.action_continue()
        elif event.button.id == "cancel-btn":
            self.action_cancel()


class ChangeListItem(ListItem):
    """List item for changes in the left panel."""

    def __init__(self, text: str, mapping: HunkTargetMapping) -> None:
        super().__init__()
        self.mapping = mapping
        # Single-line text that doesn't wrap
        self._text = Static(text, expand=True)

    def compose(self) -> ComposeResult:
        yield self._text
