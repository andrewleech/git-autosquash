"""Screen implementations for git-autosquash TUI."""

from typing import List, Union

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Static

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.tui.widgets import DiffViewer, HunkMappingWidget, ProgressIndicator


class ApprovalScreen(Screen[Union[bool, List[HunkTargetMapping]]]):
    """Screen for approving hunk to commit mappings."""

    BINDINGS = [
        Binding("enter", "approve_all", "Approve & Continue", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("a", "approve_all_toggle", "Toggle All", priority=False),
        Binding("j", "next_hunk", "Next Hunk", show=False),
        Binding("k", "prev_hunk", "Prev Hunk", show=False),
        Binding("down", "next_hunk", "Next Hunk", show=False),
        Binding("up", "prev_hunk", "Prev Hunk", show=False),
    ]

    def __init__(self, mappings: List[HunkTargetMapping], **kwargs) -> None:
        """Initialize approval screen.

        Args:
            mappings: List of hunk to commit mappings to review
        """
        super().__init__(**kwargs)
        self.mappings = mappings
        self.current_hunk_index = 0
        self.hunk_widgets: List[HunkMappingWidget] = []
        self._selected_widget: HunkMappingWidget | None = None
        self._diff_viewer: DiffViewer | None = None

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header()

        with Container(id="main-container"):
            # Title and summary
            yield Static("Hunk to Commit Mapping Review", id="screen-title")
            yield Static(
                f"Review {len(self.mappings)} hunks and their target commits. "
                "Use checkboxes to approve/reject individual hunks.",
                id="screen-description",
            )

            # Progress indicator
            yield ProgressIndicator(len(self.mappings), id="progress")

            # Main content area
            with Horizontal(id="content-area"):
                # Left panel: Hunk list
                with Vertical(id="hunk-list-panel"):
                    yield Static("Hunks", id="hunk-list-title")
                    with VerticalScroll(id="hunk-list"):
                        for mapping in self.mappings:
                            hunk_widget = HunkMappingWidget(mapping)
                            self.hunk_widgets.append(hunk_widget)
                            yield hunk_widget

                # Right panel: Diff viewer
                with Vertical(id="diff-panel"):
                    yield Static("Diff Preview", id="diff-title")
                    yield DiffViewer(id="diff-viewer")

            # Action buttons
            with Horizontal(id="action-buttons"):
                yield Button(
                    "Approve All & Continue", variant="success", id="approve-all"
                )
                yield Button("Continue with Selected", variant="primary", id="continue")
                yield Button("Cancel", variant="default", id="cancel")

        yield Footer()

    def on_mount(self) -> None:
        """Handle screen mounting."""
        # Cache diff viewer reference
        self._diff_viewer = self.query_one("#diff-viewer", DiffViewer)

        # Select first hunk if available
        if self.hunk_widgets:
            self._select_widget(self.hunk_widgets[0])

        # Update progress
        self._update_progress()

    @on(HunkMappingWidget.Selected)
    def on_hunk_selected(self, message: HunkMappingWidget.Selected) -> None:
        """Handle hunk selection."""
        # Find the clicked widget (optimized: avoid full iteration when possible)
        target_widget = None
        for i, widget in enumerate(self.hunk_widgets):
            if widget.mapping == message.mapping:
                target_widget = widget
                self.current_hunk_index = i
                break

        if target_widget:
            self._select_widget(target_widget)

    @on(HunkMappingWidget.ApprovalChanged)
    def on_approval_changed(self, message: HunkMappingWidget.ApprovalChanged) -> None:
        """Handle approval status changes."""
        self._update_progress()

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "approve-all":
            self.action_approve_all()
        elif event.button.id == "continue":
            self.action_continue()
        elif event.button.id == "cancel":
            self.action_cancel()

    def action_approve_all(self) -> None:
        """Approve all hunks and continue."""
        for widget in self.hunk_widgets:
            widget.approved = True
            checkbox = widget.query_one("#approval", Checkbox)
            checkbox.value = True

        self._update_progress()
        approved_mappings = self.get_approved_mappings()
        self.dismiss(approved_mappings)

    def action_approve_all_toggle(self) -> None:
        """Toggle approval status of all hunks."""
        # Check if all are currently approved
        all_approved = all(widget.approved for widget in self.hunk_widgets)
        new_state = not all_approved

        for widget in self.hunk_widgets:
            widget.approved = new_state
            checkbox = widget.query_one("#approval", Checkbox)
            checkbox.value = new_state

        self._update_progress()

    def action_continue(self) -> None:
        """Continue with currently selected hunks."""
        approved_mappings = self.get_approved_mappings()
        if not approved_mappings:
            # No hunks approved, cannot continue
            return

        self.dismiss(approved_mappings)

    def action_cancel(self) -> None:
        """Cancel the approval process."""
        self.dismiss(False)

    def action_next_hunk(self) -> None:
        """Select next hunk."""
        if self.current_hunk_index < len(self.hunk_widgets) - 1:
            self.current_hunk_index += 1
            self._select_hunk_by_index(self.current_hunk_index)

    def action_prev_hunk(self) -> None:
        """Select previous hunk."""
        if self.current_hunk_index > 0:
            self.current_hunk_index -= 1
            self._select_hunk_by_index(self.current_hunk_index)

    def _select_widget(self, widget: HunkMappingWidget) -> None:
        """Select a specific widget, optimized to avoid O(n) operations.

        Args:
            widget: The widget to select
        """
        # Deselect previous widget (O(1) operation)
        if self._selected_widget and self._selected_widget != widget:
            self._selected_widget.selected = False

        # Select new widget
        widget.selected = True
        self._selected_widget = widget

        # Update diff viewer (cached reference)
        if self._diff_viewer:
            self._diff_viewer.show_hunk(widget.mapping.hunk)

        # Scroll to selected widget
        widget.scroll_visible()

    def _select_hunk_by_index(self, index: int) -> None:
        """Select hunk by index."""
        if 0 <= index < len(self.hunk_widgets):
            self.current_hunk_index = index
            self._select_widget(self.hunk_widgets[index])

    def _update_progress(self) -> None:
        """Update the progress indicator."""
        approved_count = sum(1 for widget in self.hunk_widgets if widget.approved)
        progress = self.query_one("#progress", ProgressIndicator)
        progress.update_progress(approved_count)

    def get_approved_mappings(self) -> List[HunkTargetMapping]:
        """Get list of approved mappings.

        Returns:
            List of mappings that user approved
        """
        return [widget.mapping for widget in self.hunk_widgets if widget.approved]
