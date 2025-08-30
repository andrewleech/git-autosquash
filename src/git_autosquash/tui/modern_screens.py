"""Modern screen implementations with 3-panel layout matching the hero screenshot."""

from typing import Any, Dict, List, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static, ListItem, ListView

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.commit_history_analyzer import (
    CommitHistoryAnalyzer,
    CommitInfo,
    CommitSelectionStrategy,
)


class ModernApprovalScreen(Screen[Dict[str, Any]]):
    """Modern 3-panel approval screen matching the hero screenshot workflow.

    Layout:
    ┌─────────────────────────────────────────────────────────────┐
    │                        Header                               │
    ├─────────────────────┬───────────────────────────────────────┤
    │   Changes to Review │          Target Commits               │
    │   (Green border)    │          (Cyan border)                │
    │                     │                                       │
    │ • file1.py:10-15   │  ○ commit abc123 Fix typo              │
    │ • file2.js:5-8     │  ○ commit def456 Update logic          │
    │ • file3.py:20-25   │  ○ commit ghi789 Refactor              │
    │                     │                                       │
    ├─────────────────────┴───────────────────────────────────────┤
    │                     Preview                                 │
    │                   (White border)                            │
    │                                                             │
    │  @@ -10,3 +10,3 @@                                         │
    │  -    old line                                              │
    │  +    new line                                              │
    │                                                             │
    ├─────────────────────────────────────────────────────────────┤
    │            [Ignore Selected] [Continue] [Cancel]            │
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
        Binding("i", "ignore_selected", "Ignore Selected", priority=False),
        Binding("j,down", "next_change", "Next Change", show=False),
        Binding("k,up", "prev_change", "Previous Change", show=False),
    ]

    # Modern layout CSS with proper bordered panels
    CSS = """
    /* Modern 3-panel layout */
    #main-container {
        layout: vertical;
        height: 100%;
    }

    #panels-row {
        layout: horizontal;
        height: 60%;
    }

    #changes-panel {
        width: 50%;
        height: 100%;
        margin: 0 1 0 0;
        border: round green;
        border-title-style: bold;
        border-title-color: white;
        padding: 1;
    }

    #targets-panel {
        width: 50%;
        height: 100%;
        margin: 0 0 0 1;
        border: round cyan;
        border-title-style: bold;
        border-title-color: white;
        padding: 1;
    }

    #preview-panel {
        height: 35%;
        margin: 1 0;
        border: round white;
        border-title-style: bold;
        border-title-color: white;
        padding: 1;
    }

    #action-buttons {
        height: 5%;
        layout: horizontal;
        align: center middle;
    }

    #action-buttons Button {
        margin: 0 1;
        min-width: 15;
    }

    /* Changes list styling */
    #changes-list {
        height: 100%;
    }

    #changes-list ListItem {
        padding: 0 1;
        height: 3;
    }

    #changes-list ListItem.--highlight {
        background: $primary 10%;
        border-left: thick $primary;
    }

    /* Target commits styling */
    #targets-list {
        height: 100%;
    }

    #targets-list ListItem {
        padding: 0 1;
        height: 3;
    }

    #targets-list ListItem.--highlight {
        background: $accent 10%;
        border-left: thick $accent;
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
        """Initialize modern approval screen.

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
        """Compose the modern 3-panel layout."""
        yield Header()

        with Container(id="main-container"):
            with Horizontal(id="panels-row"):
                # Left panel: Changes to Review (green border)
                with Container(id="changes-panel") as changes_container:
                    changes_container.border_title = "Changes to Review"
                    changes_list = ListView(id="changes-list")
                    # Populate with change items
                    for mapping in self.mappings:
                        hunk = mapping.hunk
                        # Format: "file.py:lines"
                        change_text = f"{hunk.file_path}:{hunk.new_start}-{hunk.new_start + hunk.new_count - 1}"
                        item = ChangeListItem(change_text, mapping)
                        changes_list.append(item)
                    yield changes_list

                # Right panel: Target Commits (cyan border)
                with Container(id="targets-panel") as targets_container:
                    targets_container.border_title = "Target Commits"
                    targets_list = ListView(id="targets-list")
                    yield targets_list

            # Bottom panel: Preview (white border)
            with Container(id="preview-panel") as preview_container:
                preview_container.border_title = "Preview"
                yield Static("Select a change to view diff preview", id="diff-preview")

            # Action buttons
            with Horizontal(id="action-buttons"):
                yield Button("Ignore Selected", variant="default", id="ignore-btn")
                yield Button("Continue", variant="success", id="continue-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

        yield Footer()

    async def on_mount(self) -> None:
        """Handle screen mounting."""
        # Auto-select first change if available
        if self.mappings:
            changes_list = self.query_one("#changes-list", ListView)
            if changes_list.children:
                changes_list.index = 0
                await self._handle_change_selection(0)

    @on(ListView.Highlighted)
    async def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle list item highlighting."""
        if event.list_view.id == "changes-list":
            await self._handle_change_selection(event.list_view.index)
        elif event.list_view.id == "targets-list":
            await self._handle_target_selection(event.list_view.index)

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
        )[:10]  # Limit to 10 for UI performance

        # Update the targets list
        targets_list = self.query_one("#targets-list", ListView)
        targets_list.clear()

        for commit_info in self.current_targets:
            # Format: "abc1234 Commit subject"
            commit_text = f"{commit_info.commit_hash[:7]} {commit_info.subject[:50]}"
            item = TargetListItem(commit_text, commit_info)
            targets_list.append(item)

        # Pre-select existing target if available
        if mapping in self.target_assignments:
            target_hash = self.target_assignments[mapping]
            for i, commit_info in enumerate(self.current_targets):
                if commit_info.commit_hash == target_hash:
                    targets_list.index = i
                    break
        elif mapping.target_commit:
            # Pre-existing target from blame
            for i, commit_info in enumerate(self.current_targets):
                if commit_info.commit_hash == mapping.target_commit:
                    targets_list.index = i
                    break

    async def _handle_target_selection(self, index: int) -> None:
        """Handle selection of a target commit from the right panel."""
        if not self.selected_mapping or not (0 <= index < len(self.current_targets)):
            return

        selected_commit = self.current_targets[index]
        self.target_assignments[self.selected_mapping] = selected_commit.commit_hash

        # Visual feedback could be added here (e.g., marking the change as assigned)

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

            content = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
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
        self.dismiss(False)

    def action_ignore_selected(self) -> None:
        """Ignore the currently selected change."""
        if self.selected_mapping and self.selected_mapping not in self.ignored_mappings:
            self.ignored_mappings.append(self.selected_mapping)
            # Remove from target assignments if present
            if self.selected_mapping in self.target_assignments:
                del self.target_assignments[self.selected_mapping]

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
        elif event.button.id == "ignore-btn":
            self.action_ignore_selected()


class ChangeListItem(ListItem):
    """List item for changes in the left panel."""

    def __init__(self, text: str, mapping: HunkTargetMapping) -> None:
        super().__init__()
        self.mapping = mapping
        # Simple text display without checkboxes
        self._text = Static(text)

    def compose(self) -> ComposeResult:
        yield self._text


class TargetListItem(ListItem):
    """List item for target commits in the right panel."""

    def __init__(self, text: str, commit_info: CommitInfo) -> None:
        super().__init__()
        self.commit_info = commit_info
        # Simple text display
        self._text = Static(text)

    def compose(self) -> ComposeResult:
        yield self._text
