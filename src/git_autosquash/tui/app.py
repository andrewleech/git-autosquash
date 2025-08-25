"""Main Textual application for hunk approval workflow."""

from typing import List

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.tui.screens import ApprovalScreen


class AutoSquashApp(App[bool]):
    """Main application for git-autosquash TUI."""

    TITLE = "git-autosquash"
    SUB_TITLE = "Interactive hunk approval"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, mappings: List[HunkTargetMapping]) -> None:
        """Initialize the application.

        Args:
            mappings: List of hunk to target commit mappings to review
        """
        super().__init__()
        self.mappings = mappings
        self.approved_mappings: List[HunkTargetMapping] = []
        self.ignored_mappings: List[HunkTargetMapping] = []

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header()
        yield Footer()

    def on_mount(self) -> None:
        """Handle application startup."""
        if not self.mappings:
            # No mappings to review, exit immediately
            self.exit(False)
            return

        # Push approval screen with mappings
        self.push_screen(ApprovalScreen(self.mappings), self._handle_approval_result)

    def _handle_approval_result(
        self, result: bool | dict | List[HunkTargetMapping] | None
    ) -> None:
        """Handle result from approval screen.

        Args:
            result: Dict with 'approved' and 'ignored' keys containing mappings,
                   List of approved mappings (legacy format),
                   Boolean True/False for success/cancel
        """
        if isinstance(result, dict):
            # New format with both approved and ignored mappings
            self.approved_mappings = result.get("approved", [])
            self.ignored_mappings = result.get("ignored", [])
            self.exit(True)
        elif isinstance(result, list):
            # Legacy format - just approved mappings
            self.approved_mappings = result
            self.ignored_mappings = []
            self.exit(True)
        elif result:
            # Boolean True (should not happen with new implementation)
            self.exit(True)
        else:
            # User cancelled
            self.exit(False)

    async def action_quit(self) -> None:
        """Handle quit action."""
        self.exit(False)


class WelcomeScreen(Screen[None]):
    """Welcome screen showing project information."""

    def compose(self) -> ComposeResult:
        """Compose the welcome screen."""
        with Container():
            yield Static("Welcome to git-autosquash", id="title")
            yield Static(
                "This tool will help you automatically distribute changes "
                "back to the commits where they belong.",
                id="description",
            )
            with Horizontal():
                yield Button("Continue", variant="primary", id="continue")
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "continue":
            self.dismiss(None)
        else:
            self.dismiss(None)
