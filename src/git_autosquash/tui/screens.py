"""Screen implementations for git-autosquash TUI."""

from typing import Dict, List, Union

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Static

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.tui.state_controller import UIStateController
from git_autosquash.tui.widgets import DiffViewer, HunkMappingWidget, ProgressIndicator


class ApprovalScreen(Screen[Union[bool, Dict[str, List[HunkTargetMapping]]]]):
    """Screen for approving hunk to commit mappings."""

    BINDINGS = [
        Binding("enter", "approve_all", "Approve & Continue", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("a", "approve_all_toggle", "Toggle All", priority=False),
        Binding("i", "ignore_all_toggle", "Toggle All Ignore", priority=False),
        Binding("space", "toggle_current", "Toggle Current", priority=False),
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

        # Centralized state management
        self.state_controller = UIStateController(mappings)

        # O(1) lookup cache for widget selection performance
        self._mapping_to_widget: Dict[HunkTargetMapping, HunkMappingWidget] = {}
        self._mapping_to_index: Dict[HunkTargetMapping, int] = {}

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
                        for i, mapping in enumerate(self.mappings):
                            hunk_widget = HunkMappingWidget(mapping)
                            self.hunk_widgets.append(hunk_widget)
                            # Build O(1) lookup caches
                            self._mapping_to_widget[mapping] = hunk_widget
                            self._mapping_to_index[mapping] = i
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

        # Ensure the hunks list starts at the top
        try:
            hunk_list = self.query_one("#hunk-list")
            if hunk_list and hasattr(hunk_list, "scroll_to"):
                hunk_list.scroll_to(0, 0, animate=False)
        except Exception:
            # Gracefully handle if scroll container not found
            pass

        # Select first hunk if available
        if self.hunk_widgets:
            self._select_widget(self.hunk_widgets[0])

        # Update progress
        self._update_progress()

    @on(HunkMappingWidget.Selected)
    def on_hunk_selected(self, message: HunkMappingWidget.Selected) -> None:
        """Handle hunk selection using O(1) lookup."""
        # Use cached lookups for O(1) performance instead of O(n) iteration
        target_widget = self._mapping_to_widget.get(message.mapping)
        if target_widget:
            self.current_hunk_index = self._mapping_to_index[message.mapping]
            self._select_widget(target_widget)

    @on(HunkMappingWidget.ApprovalChanged)
    def on_approval_changed(self, message: HunkMappingWidget.ApprovalChanged) -> None:
        """Handle approval status changes."""
        self.state_controller.set_approved(message.mapping, message.approved)
        self._update_progress()

    @on(HunkMappingWidget.IgnoreChanged)
    def on_ignore_changed(self, message: HunkMappingWidget.IgnoreChanged) -> None:
        """Handle ignore status changes."""
        self.state_controller.set_ignored(message.mapping, message.ignored)
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
        self.state_controller.approve_all()
        self._sync_widgets_with_state()
        self._update_progress()

        result = {
            "approved": self.state_controller.get_approved_mappings(),
            "ignored": self.state_controller.get_ignored_mappings(),
        }
        self.dismiss(result)

    def action_approve_all_toggle(self) -> None:
        """Toggle approval status of all hunks."""
        self.state_controller.approve_all_toggle()
        self._sync_widgets_with_state()
        self._update_progress()

    def action_continue(self) -> None:
        """Continue with currently selected hunks."""
        if not self.state_controller.has_selections():
            # No hunks selected at all, cannot continue
            return

        result = {
            "approved": self.state_controller.get_approved_mappings(),
            "ignored": self.state_controller.get_ignored_mappings(),
        }
        self.dismiss(result)

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

    def action_ignore_all_toggle(self) -> None:
        """Toggle ignore status of all hunks."""
        self.state_controller.ignore_all_toggle()
        self._sync_widgets_with_state()
        self._update_progress()

    def action_toggle_current(self) -> None:
        """Toggle the approval state of the currently selected hunk (with checkbox model, just toggle approve)."""
        if not self.hunk_widgets or self.current_hunk_index >= len(self.hunk_widgets):
            return

        mapping = self.mappings[self.current_hunk_index]
        self.state_controller.toggle_approved(mapping)
        self._sync_widget_with_state(
            self.hunk_widgets[self.current_hunk_index], mapping
        )
        self._update_progress()

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
        stats = self.state_controller.get_progress_stats()
        progress = self.query_one("#progress", ProgressIndicator)
        progress.update_progress(stats["approved"], stats["ignored"])

    def _sync_widgets_with_state(self) -> None:
        """Synchronize all widgets with the centralized state."""
        for widget in self.hunk_widgets:
            self._sync_widget_with_state(widget, widget.mapping)

    def _sync_widget_with_state(
        self, widget: HunkMappingWidget, mapping: HunkTargetMapping
    ) -> None:
        """Synchronize a single widget with the centralized state.

        Args:
            widget: The widget to synchronize
            mapping: The mapping associated with the widget
        """
        # Update widget reactive properties
        widget.approved = self.state_controller.is_approved(mapping)
        widget.ignored = self.state_controller.is_ignored(mapping)

        # Update checkboxes to reflect new state
        try:
            approve_checkbox = widget.query_one("#approve-checkbox", Checkbox)
            ignore_checkbox = widget.query_one("#ignore-checkbox", Checkbox)
            approve_checkbox.value = widget.approved
            ignore_checkbox.value = widget.ignored
        except (AttributeError, ValueError):
            # Checkboxes might not be available during initial setup or widget composition
            pass
