"""Modern Textual application implementing the 3-panel workflow from the mock."""

from typing import List, Dict, Any

from textual.app import App

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.commit_history_analyzer import CommitHistoryAnalyzer
from git_autosquash.tui.modern_screens import ModernApprovalScreen


class ModernAutoSquashApp(App[bool]):
    """Modern 3-panel Textual application for git-autosquash.

    This application implements a completely different workflow from the enhanced app:

    1. **Selection-based workflow**: Select changes → Review targets → Choose → Continue
    2. **Clean interface**: No inline checkboxes or approval widgets
    3. **Dynamic panels**: Right panel updates based on left panel selection
    4. **Live preview**: Bottom panel shows diff content in real-time

    This matches the workflow shown in the hero_screenshot.png mock.
    """

    TITLE = "Git Autosquash"

    # Modern CSS styling will be defined in modern_screens.py
    CSS = """
    /* Base modern layout CSS - specific styling in screens */
    Screen {
        background: $surface;
    }
    """

    def __init__(
        self,
        mappings: List[HunkTargetMapping],
        commit_history_analyzer: CommitHistoryAnalyzer,
        **kwargs,
    ) -> None:
        """Initialize the modern git-autosquash app.

        Args:
            mappings: List of hunk to commit mappings to review
            commit_history_analyzer: Analyzer for generating commit suggestions
        """
        super().__init__(**kwargs)
        self.mappings = mappings
        self.commit_history_analyzer = commit_history_analyzer

        # Final selections - different from enhanced app's approach
        self.selected_targets: Dict[HunkTargetMapping, str] = {}
        self.ignored_mappings: List[HunkTargetMapping] = []

    def on_mount(self) -> None:
        """Handle app mounting."""
        # Launch the modern approval screen with 3-panel layout
        screen = ModernApprovalScreen(self.mappings, self.commit_history_analyzer)
        self.push_screen(screen, callback=self._on_approval_complete)

    def _on_approval_complete(self, result: Any) -> None:
        """Handle completion of approval screen.

        Args:
            result: Result from approval screen - either False (cancelled) or dict with selections
        """
        if result:
            # Modern workflow: result contains target assignments and ignored items
            self.selected_targets = result.get("targets", {})
            self.ignored_mappings = result.get("ignored", [])
            self.exit(True)
        else:
            self.exit(False)

    @property
    def approved_mappings(self) -> List[HunkTargetMapping]:
        """Get approved mappings (those with selected targets).

        Returns:
            List of mappings that have target commits assigned
        """
        approved = []
        for mapping in self.mappings:
            if mapping in self.selected_targets:
                # Update the mapping with selected target
                mapping.target_commit = self.selected_targets[mapping]
                mapping.needs_user_selection = False
                approved.append(mapping)
        return approved
