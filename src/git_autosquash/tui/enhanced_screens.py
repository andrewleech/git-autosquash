"""Enhanced screen implementations with fallback target selection support."""

from typing import Dict, List, Union, Optional

# Constants
MAX_COMMIT_SUGGESTIONS = 10

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
from git_autosquash.commit_history_analyzer import CommitInfo, CommitHistoryAnalyzer, CommitSelectionStrategy
from git_autosquash.tui.state_controller import UIStateController
from git_autosquash.tui.widgets import DiffViewer
from git_autosquash.tui.fallback_widgets import (
    FallbackHunkMappingWidget,
    BatchSelectionWidget,
    FallbackSectionSeparator,
    EnhancedProgressIndicator
)


class EnhancedApprovalScreen(Screen[Union[bool, List[HunkTargetMapping]]]):
    """Enhanced approval screen with fallback target selection support."""

    BINDINGS = [
        Binding("enter", "approve_all", "Approve & Continue", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("a", "approve_all_toggle", "Toggle All", priority=False),
        Binding("i", "ignore_all_toggle", "Toggle All Ignore", priority=False),
        Binding("b", "show_batch_panel", "Batch Actions", priority=False),
        Binding("space", "toggle_current", "Toggle Current", priority=False),
        Binding("j", "next_hunk", "Next Hunk", show=False),
        Binding("k", "prev_hunk", "Prev Hunk", show=False),
        Binding("down", "next_hunk", "Next Hunk", show=False),
        Binding("up", "prev_hunk", "Prev Hunk", show=False),
    ]

    def __init__(
        self, 
        mappings: List[HunkTargetMapping],
        commit_history_analyzer: CommitHistoryAnalyzer,
        **kwargs
    ) -> None:
        """Initialize enhanced approval screen.

        Args:
            mappings: List of hunk to commit mappings to review
            commit_history_analyzer: Analyzer for generating commit suggestions
        """
        super().__init__(**kwargs)
        self.mappings = mappings
        self.commit_history_analyzer = commit_history_analyzer
        self.current_hunk_index = 0
        self.hunk_widgets: List[FallbackHunkMappingWidget] = []
        self._selected_widget: FallbackHunkMappingWidget | None = None
        self._diff_viewer: DiffViewer | None = None
        self._batch_widget: BatchSelectionWidget | None = None

        # Categorize mappings
        self.blame_matches = [m for m in mappings if not m.needs_user_selection]
        self.fallback_mappings = [m for m in mappings if m.needs_user_selection]

        # Centralized state management
        self.state_controller = UIStateController(mappings)

        # O(1) lookup cache for widget selection performance
        self._mapping_to_widget: Dict[HunkTargetMapping, FallbackHunkMappingWidget] = {}
        self._mapping_to_index: Dict[HunkTargetMapping, int] = {}

        # Generate commit info for fallback scenarios
        self.commit_infos = self._generate_commit_suggestions()

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header()

        with Container(id="main-container"):
            # Title and summary
            yield Static("Enhanced Hunk to Commit Mapping Review", id="screen-title")
            yield Static(
                f"Review {len(self.mappings)} hunks. "
                f"{len(self.blame_matches)} have automatic targets, "
                f"{len(self.fallback_mappings)} need manual selection.",
                id="screen-description",
            )

            # Enhanced progress indicator
            yield EnhancedProgressIndicator(
                len(self.mappings), 
                len(self.blame_matches), 
                len(self.fallback_mappings),
                id="progress"
            )

            # Main content area
            with Horizontal(id="content-area"):
                # Left panel: Hunk list with sections
                with Vertical(id="hunk-list-panel"):
                    yield Static("Hunks", id="hunk-list-title")
                    with VerticalScroll(id="hunk-list"):
                        # First section: Blame matches
                        if self.blame_matches:
                            yield Static("✓ Automatic Targets (Blame Analysis)", classes="section-header")
                            for i, mapping in enumerate(self.blame_matches):
                                hunk_widget = self._create_hunk_widget(mapping, i)
                                self.hunk_widgets.append(hunk_widget)
                                yield hunk_widget

                        # Separator if we have both types
                        if self.blame_matches and self.fallback_mappings:
                            yield FallbackSectionSeparator()

                        # Second section: Fallback scenarios
                        if self.fallback_mappings:
                            # Batch selection panel
                            batch_widget = BatchSelectionWidget(self.commit_infos)
                            self._batch_widget = batch_widget
                            yield batch_widget

                            yield Static("⚠ Manual Selection Required", classes="section-header fallback")
                            
                            start_index = len(self.blame_matches)
                            for i, mapping in enumerate(self.fallback_mappings):
                                commit_suggestions = self._get_suggestions_for_mapping(mapping)
                                hunk_widget = self._create_hunk_widget(
                                    mapping, 
                                    start_index + i, 
                                    commit_suggestions
                                )
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

    def _create_hunk_widget(
        self, 
        mapping: HunkTargetMapping, 
        index: int, 
        commit_suggestions: Optional[List[CommitInfo]] = None
    ) -> FallbackHunkMappingWidget:
        """Create a hunk widget with appropriate configuration.
        
        Args:
            mapping: Mapping to create widget for
            index: Index in the full list
            commit_suggestions: Optional commit suggestions for fallback scenarios
            
        Returns:
            Configured FallbackHunkMappingWidget
        """
        hunk_widget = FallbackHunkMappingWidget(mapping, commit_suggestions)
        
        # Build O(1) lookup caches
        self._mapping_to_widget[mapping] = hunk_widget
        self._mapping_to_index[mapping] = index
        
        return hunk_widget

    def _get_suggestions_for_mapping(self, mapping: HunkTargetMapping) -> List[CommitInfo]:
        """Get commit suggestions for a specific mapping.
        
        Args:
            mapping: Mapping to get suggestions for
            
        Returns:
            List of CommitInfo objects for suggestions
        """
        if mapping.targeting_method == TargetingMethod.FALLBACK_NEW_FILE:
            strategy = CommitSelectionStrategy.RECENCY
        else:
            strategy = CommitSelectionStrategy.FILE_RELEVANCE
        
        suggestions = self.commit_history_analyzer.get_commit_suggestions(
            strategy, mapping.hunk.file_path
        )
        
        return suggestions[:MAX_COMMIT_SUGGESTIONS]  # Limit for UI performance

    def _generate_commit_suggestions(self) -> List[CommitInfo]:
        """Generate general commit suggestions for batch operations.
        
        Returns:
            List of CommitInfo objects for general use
        """
        return self.commit_history_analyzer.get_commit_suggestions(
            CommitSelectionStrategy.RECENCY
        )

    @on(FallbackHunkMappingWidget.Selected)
    def on_hunk_selected(self, message: FallbackHunkMappingWidget.Selected) -> None:
        """Handle hunk selection using O(1) lookup."""
        target_widget = self._mapping_to_widget.get(message.mapping)
        if target_widget:
            index = self._mapping_to_index.get(message.mapping)
            if index is not None:
                self.current_hunk_index = index
                self._select_widget(target_widget)
        else:
            self.log.error(f"No widget found for mapping: {message.mapping.hunk.file_path}")

    @on(FallbackHunkMappingWidget.ApprovalChanged)
    def on_approval_changed(self, message: FallbackHunkMappingWidget.ApprovalChanged) -> None:
        """Handle approval status changes."""
        self.state_controller.set_approved(message.mapping, message.approved)
        self._update_progress()

    @on(FallbackHunkMappingWidget.IgnoreChanged)
    def on_ignore_changed(self, message: FallbackHunkMappingWidget.IgnoreChanged) -> None:
        """Handle ignore status changes."""
        self.state_controller.set_ignored(message.mapping, message.ignored)
        self._update_progress()

    @on(FallbackHunkMappingWidget.TargetSelected)
    def on_target_selected(self, message: FallbackHunkMappingWidget.TargetSelected) -> None:
        """Handle target commit selection."""
        # Update the mapping with the selected target
        message.mapping.target_commit = message.target_commit
        message.mapping.needs_user_selection = False
        message.mapping.confidence = "medium"  # User-selected gets medium confidence
        
        # Store the target for file consistency
        self.commit_history_analyzer.git_ops  # Access through analyzer for consistency
        # Note: We could add a method to set file consistency here if needed
        
        self._update_progress()

    @on(BatchSelectionWidget.BatchTargetSelected)
    def on_batch_target_selected(self, message: BatchSelectionWidget.BatchTargetSelected) -> None:
        """Handle batch target selection."""
        if message.target_commit == "ignore":
            # Set all fallback mappings to ignored
            for mapping in self.fallback_mappings:
                if mapping.needs_user_selection:
                    self.state_controller.set_ignored(mapping, True)
                    widget = self._mapping_to_widget.get(mapping)
                    if widget:
                        widget.ignored = True
                    else:
                        self.log.warning(f"Widget not found for batch ignore operation: {mapping.hunk.file_path}")
        else:
            # Set all fallback mappings to the selected target
            for mapping in self.fallback_mappings:
                if mapping.needs_user_selection:
                    mapping.target_commit = message.target_commit
                    mapping.needs_user_selection = False
                    mapping.confidence = "medium"
                    self.state_controller.set_approved(mapping, True)
                    widget = self._mapping_to_widget.get(mapping)
                    if widget:
                        widget.approved = True
                        widget.ignored = False
                    else:
                        self.log.warning(f"Widget not found for batch approval operation: {mapping.hunk.file_path}")

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

    def _select_widget(self, widget: FallbackHunkMappingWidget) -> None:
        """Select a hunk widget and update diff display."""
        # Clear previous selection
        if self._selected_widget:
            self._selected_widget.selected = False

        # Set new selection
        self._selected_widget = widget
        widget.selected = True

        # Update diff viewer
        if self._diff_viewer:
            self._diff_viewer.show_hunk(widget.mapping.hunk)

    def _update_progress(self) -> None:
        """Update progress indicators."""
        # This could be enhanced to show real-time progress
        pass

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

    def action_continue(self) -> None:
        """Continue with current selections."""
        result = {
            "approved": self.state_controller.get_approved_mappings(),
            "ignored": self.state_controller.get_ignored_mappings(),
        }
        self.dismiss(result)

    def action_cancel(self) -> None:
        """Cancel the operation."""
        self.dismiss(False)

    def action_approve_all_toggle(self) -> None:
        """Toggle approve all hunks."""
        # Check if all are currently approved
        all_approved = all(
            self.state_controller.is_approved(mapping) for mapping in self.mappings
        )

        if all_approved:
            # Uncheck all
            for mapping in self.mappings:
                self.state_controller.set_approved(mapping, False)
        else:
            # Check all
            for mapping in self.mappings:
                self.state_controller.set_approved(mapping, True)

        self._sync_widgets_with_state()
        self._update_progress()

    def action_ignore_all_toggle(self) -> None:
        """Toggle ignore all hunks."""
        # Check if all are currently ignored
        all_ignored = all(
            self.state_controller.is_ignored(mapping) for mapping in self.mappings
        )

        if all_ignored:
            # Uncheck all
            for mapping in self.mappings:
                self.state_controller.set_ignored(mapping, False)
        else:
            # Check all
            for mapping in self.mappings:
                self.state_controller.set_ignored(mapping, True)

        self._sync_widgets_with_state()
        self._update_progress()

    def action_next_hunk(self) -> None:
        """Navigate to next hunk."""
        if self.current_hunk_index < len(self.hunk_widgets) - 1:
            self.current_hunk_index += 1
            self._select_widget(self.hunk_widgets[self.current_hunk_index])

    def action_prev_hunk(self) -> None:
        """Navigate to previous hunk."""
        if self.current_hunk_index > 0:
            self.current_hunk_index -= 1
            self._select_widget(self.hunk_widgets[self.current_hunk_index])

    def action_toggle_current(self) -> None:
        """Toggle current hunk approval."""
        if self._selected_widget:
            mapping = self._selected_widget.mapping
            current_approved = self.state_controller.is_approved(mapping)
            self.state_controller.set_approved(mapping, not current_approved)
            self._selected_widget.approved = not current_approved
            self._update_progress()

    def _sync_widgets_with_state(self) -> None:
        """Sync widget states with controller state."""
        for mapping, widget in self._mapping_to_widget.items():
            widget.approved = self.state_controller.is_approved(mapping)
            widget.ignored = self.state_controller.is_ignored(mapping)