"""Enhanced screen implementations with fallback target selection support."""

from typing import Dict, List, Union, Optional

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen, ModalScreen
from textual.widgets import Button, Footer, Header, Static

from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
from git_autosquash.commit_history_analyzer import (
    CommitInfo,
    CommitHistoryAnalyzer,
    CommitSelectionStrategy,
)
from git_autosquash.tui.state_controller import UIStateController
# DiffViewer no longer needed - diff is embedded in hunk widgets
from git_autosquash.tui.fallback_widgets import (
    FallbackHunkMappingWidget,
    BatchSelectionWidget,
    FallbackSectionSeparator,
)

# Configuration constants - centralized for easy adjustment
MAX_COMMIT_SUGGESTIONS = (
    10  # Maximum commits to show in suggestion lists (UI performance)
)
COMMIT_SUBJECT_TRUNCATE_LENGTH = 50  # Maximum length for commit subjects in UI
SAFE_PATH_MAX_LENGTH = 100  # Maximum length for sanitized paths in logs
SEPARATOR_FALLBACK_WIDTH = (
    80  # Fallback width for separator when terminal size unavailable
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
        **kwargs,
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
        self._diff_viewer = None  # No separate diff viewer in new single-pane layout
        self._batch_widget: BatchSelectionWidget | None = None

        # Categorize mappings
        self.blame_matches = [m for m in mappings if not m.needs_user_selection]
        self.fallback_mappings = [m for m in mappings if m.needs_user_selection]

        # Centralized state management
        self.state_controller = UIStateController(mappings)

        # O(1) lookup cache for widget selection performance (cleaned up on unmount)
        self._mapping_to_widget: Dict[HunkTargetMapping, FallbackHunkMappingWidget] = {}
        self._mapping_to_index: Dict[HunkTargetMapping, int] = {}
        self._cleanup_required = True

        # Generate commit info for fallback scenarios
        self.commit_infos = self._generate_commit_suggestions()

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header()

        with Container(id="main-container"):
            # Content wrapper for everything except buttons
            with Container(id="content-wrapper"):
                # Title and summary
                yield Static("Git patch -> target commit Review", id="screen-title")
                yield Static(
                    f"Progress Summary: {len(self.mappings)} hunks - "
                    f"{len(self.blame_matches)} automatic targets, "
                    f"{len(self.fallback_mappings)} manual selection",
                    id="screen-description",
                )

                # Horizontal rule separator - adapts to terminal width
                try:
                    terminal_width = (
                        self.app.console.width
                        if hasattr(self.app, "console")
                        else SEPARATOR_FALLBACK_WIDTH
                    )
                    separator_width = min(
                        terminal_width - 4, SEPARATOR_FALLBACK_WIDTH
                    )  # Leave margin
                except Exception:
                    separator_width = SEPARATOR_FALLBACK_WIDTH
                yield Static("─" * separator_width, id="separator")

                # Main content area - single scrollable pane
                with VerticalScroll(id="hunk-scroll-pane"):
                    # First section: Blame matches
                    if self.blame_matches:
                        yield Static(
                            "✓ Automatic Targets (Blame Analysis)",
                            classes="section-header",
                        )
                        for i, mapping in enumerate(self.blame_matches):
                            commit_suggestions = (
                                self._get_suggestions_for_mapping(mapping)
                            )
                            
                            # Target commit info is logged in FallbackHunkMappingWidget if needed
                            
                            hunk_widget = self._create_hunk_widget(
                                mapping, i, commit_suggestions
                            )
                            self.hunk_widgets.append(hunk_widget)
                            yield hunk_widget

                    # Separator if we have both types
                    if self.blame_matches and self.fallback_mappings:
                        yield FallbackSectionSeparator()

                    # Second section: Fallback scenarios
                    if self.fallback_mappings:
                        yield Static(
                            "⚠ Manual Selection Required (Press 'b' for batch operations)",
                            classes="section-header fallback",
                        )

                        start_index = len(self.blame_matches)
                        for i, mapping in enumerate(self.fallback_mappings):
                            commit_suggestions = (
                                self._get_suggestions_for_mapping(mapping)
                            )
                            hunk_widget = self._create_hunk_widget(
                                mapping, start_index + i, commit_suggestions
                            )
                            self.hunk_widgets.append(hunk_widget)
                            yield hunk_widget

            # Action buttons - now outside content-wrapper so they dock to bottom
            with Horizontal(id="action-buttons"):
                yield Button(
                    "Approve All & Continue", variant="success", id="approve-all"
                )
                yield Button("Continue with Selected", variant="primary", id="continue")
                yield Button("Cancel", variant="default", id="cancel")

        yield Footer()

    def on_mount(self) -> None:
        """Handle screen mounting."""
        # No separate diff viewer in new layout - diff is embedded in each hunk
        self._diff_viewer = None

        # Select first hunk if available
        if self.hunk_widgets:
            self._select_widget(self.hunk_widgets[0])

        # Update progress
        self._update_progress()

    def _create_hunk_widget(
        self,
        mapping: HunkTargetMapping,
        index: int,
        commit_suggestions: Optional[List[CommitInfo]] = None,
    ) -> FallbackHunkMappingWidget:
        """Create a hunk widget with appropriate configuration.

        Args:
            mapping: Mapping to create widget for
            index: Index in the full list
            commit_suggestions: Optional commit suggestions for fallback scenarios

        Returns:
            Configured FallbackHunkMappingWidget
        """
        hunk_widget = FallbackHunkMappingWidget(mapping, commit_suggestions, self.commit_history_analyzer)

        # Build O(1) lookup caches
        self._mapping_to_widget[mapping] = hunk_widget
        self._mapping_to_index[mapping] = index

        return hunk_widget

    def _get_suggestions_for_mapping(
        self, mapping: HunkTargetMapping
    ) -> List[CommitInfo]:
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

        # For blame matches, ensure the target commit is always included in suggestions
        if mapping.target_commit and not mapping.needs_user_selection:
            # Check if the target commit is already in the suggestions
            target_in_suggestions = any(
                commit.commit_hash == mapping.target_commit for commit in suggestions
            )

            if not target_in_suggestions:
                # Add the target commit in its natural chronological position
                try:
                    target_commit_info = self.commit_history_analyzer.git_ops.batch_ops.batch_load_commit_info(
                        [mapping.target_commit]
                    ).get(mapping.target_commit)

                    if target_commit_info:
                        from git_autosquash.commit_history_analyzer import CommitInfo

                        target_info = CommitInfo(
                            commit_hash=target_commit_info.commit_hash,
                            short_hash=target_commit_info.short_hash,
                            subject=target_commit_info.subject,
                            author=target_commit_info.author,
                            timestamp=target_commit_info.timestamp,
                            is_merge=target_commit_info.is_merge,
                            files_touched=None,
                        )
                        # Insert in chronological order (most recent first)
                        inserted = False
                        for i, existing_commit in enumerate(suggestions):
                            if target_info.timestamp > existing_commit.timestamp:
                                suggestions.insert(i, target_info)
                                inserted = True
                                break
                        
                        # If not inserted (oldest commit), append to end
                        if not inserted:
                            suggestions.append(target_info)
                except Exception as e:
                    self.log.warning(f"Failed to load target commit info: {e}")

        return suggestions[:MAX_COMMIT_SUGGESTIONS]  # Limit for UI performance

    def _safe_file_path(self, mapping: HunkTargetMapping) -> str:
        """Safely extract file path for logging, preventing path traversal issues.

        Args:
            mapping: The hunk mapping to extract path from

        Returns:
            Sanitized file path string
        """
        try:
            path = mapping.hunk.file_path
            # Basic sanitization - remove any path traversal attempts
            safe_path = (
                str(path).replace("..", "_").replace("\x00", "_")[:SAFE_PATH_MAX_LENGTH]
            )
            return safe_path
        except Exception:
            return "<unknown_file>"

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
        """Handle hunk selection using O(1) lookup with error boundary."""
        try:
            target_widget = self._mapping_to_widget.get(message.mapping)
            if target_widget:
                index = self._mapping_to_index.get(message.mapping)
                if index is not None:
                    self.current_hunk_index = index
                    self._select_widget(target_widget)
                else:
                    self.log.warning(
                        f"No index found for mapping: {self._safe_file_path(message.mapping)}"
                    )
            else:
                self.log.warning(
                    f"No widget found for mapping: {self._safe_file_path(message.mapping)}"
                )
        except Exception as e:
            self.log.error(f"Error handling hunk selection: {e}")
            # Continue gracefully without crashing the UI

    @on(FallbackHunkMappingWidget.ApprovalChanged)
    def on_approval_changed(
        self, message: FallbackHunkMappingWidget.ApprovalChanged
    ) -> None:
        """Handle approval status changes with error boundary."""
        try:
            self.state_controller.set_approved(message.mapping, message.approved)
            self._update_progress()
        except Exception as e:
            self.log.error(
                f"Error handling approval change for {self._safe_file_path(message.mapping)}: {e}"
            )
            # Continue gracefully without crashing the UI

    @on(FallbackHunkMappingWidget.IgnoreChanged)
    def on_ignore_changed(
        self, message: FallbackHunkMappingWidget.IgnoreChanged
    ) -> None:
        """Handle ignore status changes with error boundary."""
        try:
            self.state_controller.set_ignored(message.mapping, message.ignored)
            self._update_progress()
        except Exception as e:
            self.log.error(
                f"Error handling ignore change for {self._safe_file_path(message.mapping)}: {e}"
            )
            # Continue gracefully without crashing the UI

    @on(FallbackHunkMappingWidget.TargetSelected)
    def on_target_selected(
        self, message: FallbackHunkMappingWidget.TargetSelected
    ) -> None:
        """Handle target commit selection with error boundary."""
        try:
            # Update the mapping with the selected target
            message.mapping.target_commit = message.target_commit
            message.mapping.needs_user_selection = False
            message.mapping.confidence = (
                "medium"  # User-selected gets medium confidence
            )

            # Store the target for file consistency
            self.commit_history_analyzer.git_ops  # Access through analyzer for consistency
            # Note: We could add a method to set file consistency here if needed

            self._update_progress()
        except Exception as e:
            self.log.error(
                f"Error handling target selection for {self._safe_file_path(message.mapping)}: {e}"
            )
            # Continue gracefully without crashing the UI

    @on(BatchSelectionWidget.BatchTargetSelected)
    def on_batch_target_selected(
        self, message: BatchSelectionWidget.BatchTargetSelected
    ) -> None:
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
                        self.log.warning(
                            f"Widget not found for batch ignore operation: {mapping.hunk.file_path}"
                        )
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
                        self.log.warning(
                            f"Widget not found for batch approval operation: {mapping.hunk.file_path}"
                        )

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
        """Select a hunk widget with error boundary."""
        try:
            # Clear previous selection
            if self._selected_widget:
                self._selected_widget.selected = False

            # Set new selection
            self._selected_widget = widget
            widget.selected = True

            # No separate diff viewer - diff is embedded in each widget
        except Exception as e:
            self.log.error(f"Error selecting widget: {e}")
            # Continue gracefully without crashing the UI

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
        """Sync widget states with controller state - optimized to avoid O(n) when unnecessary."""
        if not hasattr(self, "_last_sync_state"):
            self._last_sync_state: Dict[HunkTargetMapping, Dict[str, bool]] = {}

        try:
            # Track which mappings actually changed to avoid unnecessary widget updates
            changed_mappings = []

            for mapping, widget in self._mapping_to_widget.items():
                current_approved = self.state_controller.is_approved(mapping)
                current_ignored = self.state_controller.is_ignored(mapping)
                last_state = self._last_sync_state.get(mapping, {})

                if (
                    last_state.get("approved") != current_approved
                    or last_state.get("ignored") != current_ignored
                ):
                    widget.approved = current_approved
                    widget.ignored = current_ignored
                    changed_mappings.append(mapping)

                    # Update tracking
                    self._last_sync_state[mapping] = {
                        "approved": current_approved,
                        "ignored": current_ignored,
                    }

            if changed_mappings:
                self.log.debug(f"Synced {len(changed_mappings)} widget states")

        except Exception as e:
            self.log.error(f"Error syncing widget states: {e}")
            # Fallback to simple sync
            self._simple_sync_widgets()

    def _simple_sync_widgets(self) -> None:
        """Simple fallback widget sync without optimization."""
        try:
            for mapping, widget in self._mapping_to_widget.items():
                widget.approved = self.state_controller.is_approved(mapping)
                widget.ignored = self.state_controller.is_ignored(mapping)
        except Exception as e:
            self.log.error(f"Error in simple widget sync: {e}")

    def action_show_batch_panel(self) -> None:
        """Show batch operations modal."""
        if self.fallback_mappings:  # Only show if there are fallback mappings
            modal = BatchOperationsModal(self.commit_infos)
            self.app.push_screen(modal, callback=self._handle_batch_selection)

    def _handle_batch_selection(self, result: Optional[str]) -> None:
        """Handle batch selection from modal with proper validation and error handling.

        Args:
            result: Selected target commit hash or "ignore", or None if cancelled
        """
        if result is None:
            return  # User cancelled

        try:
            if result == "ignore":
                self._apply_batch_ignore()
            else:
                self._apply_batch_target_selection(result)

            self._update_progress()
        except Exception as e:
            self.log.error(f"Failed to apply batch selection: {e}")
            # Could show user notification here

    def _apply_batch_ignore(self) -> None:
        """Apply ignore status to all fallback mappings."""
        updated_count = 0
        for mapping in self.fallback_mappings:
            if mapping.needs_user_selection:
                try:
                    self.state_controller.set_ignored(mapping, True)
                    widget = self._mapping_to_widget.get(mapping)
                    if widget:
                        widget.ignored = True
                    updated_count += 1
                except Exception as e:
                    self.log.error(
                        f"Failed to ignore mapping for {mapping.hunk.file_path}: {e}"
                    )

        self.log.info(f"Applied ignore status to {updated_count} mappings")

    def _apply_batch_target_selection(self, target_commit: str) -> None:
        """Apply target commit selection to all fallback mappings with validation.

        Args:
            target_commit: The commit hash to apply

        Raises:
            ValueError: If target_commit is invalid format
        """
        if not target_commit or not isinstance(target_commit, str):
            raise ValueError("Invalid target commit: must be non-empty string")

        # Basic commit hash validation (7-40 hex characters)
        if not (
            7 <= len(target_commit) <= 40
            and all(c in "0123456789abcdef" for c in target_commit.lower())
        ):
            raise ValueError(f"Invalid commit hash format: {target_commit}")

        updated_count = 0
        for mapping in self.fallback_mappings:
            if mapping.needs_user_selection:
                try:
                    mapping.target_commit = target_commit
                    mapping.needs_user_selection = False
                    mapping.confidence = "medium"
                    self.state_controller.set_approved(mapping, True)
                    widget = self._mapping_to_widget.get(mapping)
                    if widget:
                        widget.approved = True
                        widget.ignored = False
                    updated_count += 1
                except Exception as e:
                    self.log.error(
                        f"Failed to set target for mapping {mapping.hunk.file_path}: {e}"
                    )

        self.log.info(
            f"Applied target commit {target_commit} to {updated_count} mappings"
        )

    def on_unmount(self) -> None:
        """Handle screen unmounting with proper cleanup."""
        if self._cleanup_required:
            self._cleanup_resources()

    def _cleanup_resources(self) -> None:
        """Clean up widget references and caches to prevent memory leaks."""
        try:
            # Clear widget references
            for widget in self._mapping_to_widget.values():
                if hasattr(widget, "cleanup"):
                    widget.cleanup()

            self._mapping_to_widget.clear()
            self._mapping_to_index.clear()
            self.hunk_widgets.clear()

            # Clear references to prevent circular dependencies
            self._selected_widget = None
            self._diff_viewer = None
            self._batch_widget = None

            # Clear state tracking
            if hasattr(self, "_last_sync_state"):
                self._last_sync_state.clear()

            self._cleanup_required = False
            self.log.debug("Enhanced approval screen cleanup completed")
        except Exception as e:
            self.log.error(f"Error during screen cleanup: {e}")

    def __del__(self) -> None:
        """Ensure cleanup happens even if unmount isn't called."""
        if hasattr(self, "_cleanup_required") and self._cleanup_required:
            self._cleanup_resources()


class BatchOperationsModal(ModalScreen[Optional[str]]):
    """Modal screen for batch operations on fallback mappings with proper focus management."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("q", "cancel", "Cancel", priority=True),
        Binding("enter", "confirm_selection", "Confirm", priority=True),
        Binding("tab", "focus_next", "Focus Next", show=False),
        Binding("shift+tab", "focus_previous", "Focus Previous", show=False),
    ]

    def __init__(self, commit_infos: List[CommitInfo], **kwargs) -> None:
        """Initialize batch operations modal.

        Args:
            commit_infos: List of available commits for batch selection
        """
        super().__init__(**kwargs)
        self.commit_infos = commit_infos
        self._batch_widget: Optional[BatchSelectionWidget] = None
        self._focused_widget_index = 0

    def compose(self) -> ComposeResult:
        """Compose the modal layout."""
        with Container(id="modal-container"):
            yield Static("Batch Operations", id="modal-title")
            yield Static(
                "Apply the same action to all items requiring manual selection:",
                id="modal-description",
            )

            with Container(id="modal-content"):
                batch_widget = BatchSelectionWidget(
                    self.commit_infos, id="batch-widget"
                )
                self._batch_widget = batch_widget
                yield batch_widget

            with Horizontal(id="modal-buttons"):
                yield Button("Cancel", variant="default", id="modal-cancel")

    def on_mount(self) -> None:
        """Handle modal mounting with proper focus management."""
        try:
            # Set initial focus to the batch widget if available
            if self._batch_widget:
                self._batch_widget.focus()
            else:
                # Fallback to cancel button
                cancel_button = self.query_one("#modal-cancel", Button)
                cancel_button.focus()
        except Exception as e:
            self.log.error(f"Error setting initial modal focus: {e}")

    def on_unmount(self) -> None:
        """Handle modal unmounting with cleanup."""
        try:
            self._batch_widget = None
        except Exception as e:
            self.log.error(f"Error during modal cleanup: {e}")

    @on(BatchSelectionWidget.BatchTargetSelected)
    def on_batch_target_selected(
        self, message: BatchSelectionWidget.BatchTargetSelected
    ) -> None:
        """Handle batch target selection."""
        self.dismiss(message.target_commit)

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "modal-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        """Cancel the modal."""
        self.dismiss(None)

    def action_confirm_selection(self) -> None:
        """Confirm current selection in the batch widget."""
        try:
            if self._batch_widget and hasattr(
                self._batch_widget, "get_current_selection"
            ):
                selection = self._batch_widget.get_current_selection()
                if selection:
                    self.dismiss(selection)
            # If no selection available, treat as cancel
            self.dismiss(None)
        except Exception as e:
            self.log.error(f"Error confirming selection: {e}")
            self.dismiss(None)

    def action_focus_next(self) -> None:
        """Focus next focusable widget."""
        try:
            self.focus_next()
        except Exception as e:
            self.log.error(f"Error focusing next widget: {e}")

    def action_focus_previous(self) -> None:
        """Focus previous focusable widget."""
        try:
            self.focus_previous()
        except Exception as e:
            self.log.error(f"Error focusing previous widget: {e}")
