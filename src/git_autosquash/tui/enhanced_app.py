"""Enhanced Textual application with fallback target selection support."""

from typing import List, Dict, Any

from textual.app import App

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.commit_history_analyzer import CommitHistoryAnalyzer
from git_autosquash.tui.enhanced_screens import EnhancedApprovalScreen


class EnhancedAutoSquashApp(App[bool]):
    """Enhanced Textual application for git-autosquash with fallback support.

    This application provides an interactive interface for reviewing and approving
    hunk-to-commit mappings, with support for fallback target selection when
    automatic blame analysis fails.
    """

    TITLE = "Git Autosquash"

    # CSS for widget styling and proper screen height allocation
    CSS = """
    /* Main container takes full screen height minus header/footer */
    #main-container {
        height: 1fr;
        layout: vertical;
    }
    
    /* Scroll pane expands to fill available space above buttons */
    #hunk-scroll-pane {
        height: 1fr;
        overflow: auto;
        padding: 0 1;
    }
    
    /* Section headers */
    .section-header {
        background: $boost;
        color: $text;
        text-style: bold;
        padding: 0 1;
        margin: 1 0;
        text-align: left;
    }

    .section-header.fallback {
        background: $warning;
        color: $background;
    }

    /* Hunk mapping widgets */
    FallbackHunkMappingWidget {
        height: auto;
        margin: 1 0;
        border: round $primary;
    }

    FallbackHunkMappingWidget.selected {
        border: thick $accent;
    }

    FallbackHunkMappingWidget.approved {
        border-left: thick $success;
    }

    FallbackHunkMappingWidget.ignored {
        opacity: 0.6;
        border-left: thick $warning;
    }

    /* Diff viewer */
    DiffViewer {
        border: round $primary;
        padding: 1;
    }

    DiffViewer .diff-header {
        color: $text-muted;
        text-style: bold;
    }

    DiffViewer .diff-added {
        color: $success;
    }

    DiffViewer .diff-removed {
        color: $error;
    }
    """

    def __init__(
        self,
        mappings: List[HunkTargetMapping],
        commit_history_analyzer: CommitHistoryAnalyzer,
        **kwargs,
    ) -> None:
        """Initialize the enhanced git-autosquash app.

        Args:
            mappings: List of hunk to commit mappings to review
            commit_history_analyzer: Analyzer for generating commit suggestions
        """
        super().__init__(**kwargs)
        self.mappings = mappings
        self.commit_history_analyzer = commit_history_analyzer
        self.approved_mappings: List[HunkTargetMapping] = []
        self.ignored_mappings: List[HunkTargetMapping] = []

    def on_mount(self) -> None:
        """Handle app mounting."""
        # Launch the enhanced approval screen
        screen = EnhancedApprovalScreen(self.mappings, self.commit_history_analyzer)
        self.push_screen(screen, callback=self._on_approval_complete)

    def _on_approval_complete(self, result: Any) -> None:
        """Handle completion of approval screen.

        Args:
            result: Result from approval screen - either False (cancelled) or dict with selections
        """
        if result is False:
            # User cancelled
            self.approved_mappings = []
            self.ignored_mappings = []
            self.exit(False)
        else:
            # User made selections
            self.approved_mappings = result.get("approved", [])
            self.ignored_mappings = result.get("ignored", [])
            self.exit(True)

    def get_approved_mappings(self) -> List[HunkTargetMapping]:
        """Get list of approved mappings.

        Returns:
            List of approved HunkTargetMapping objects
        """
        return self.approved_mappings

    def get_ignored_mappings(self) -> List[HunkTargetMapping]:
        """Get list of ignored mappings.

        Returns:
            List of ignored HunkTargetMapping objects
        """
        return self.ignored_mappings

    def get_selection_summary(self) -> Dict[str, Any]:
        """Get summary of user selections.

        Returns:
            Dictionary with selection statistics
        """
        total_mappings = len(self.mappings)
        approved_count = len(self.approved_mappings)
        ignored_count = len(self.ignored_mappings)
        unprocessed_count = total_mappings - approved_count - ignored_count

        return {
            "total": total_mappings,
            "approved": approved_count,
            "ignored": ignored_count,
            "unprocessed": unprocessed_count,
            "approval_rate": approved_count / total_mappings
            if total_mappings > 0
            else 0,
        }

    def validate_selections(self) -> bool:
        """Validate that user selections are consistent.

        Returns:
            True if selections are valid
        """
        # Check for overlapping selections (shouldn't happen with proper UI)
        approved_set = set(id(m) for m in self.approved_mappings)
        ignored_set = set(id(m) for m in self.ignored_mappings)

        if approved_set & ignored_set:
            return False  # Overlap detected

        # Check that all approved mappings have valid targets
        for mapping in self.approved_mappings:
            if not mapping.target_commit:
                return False

        return True
