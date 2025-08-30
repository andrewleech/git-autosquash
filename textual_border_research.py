#!/usr/bin/env python3
"""Research and demonstrate Textual's border capabilities.

This script shows how to create the exact border styling seen in the mock
screenshot: rounded corners with inline titles like "Changes to Review".
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static, Header, Footer
from textual.widget import Widget


class MockChangesPanel(Widget):
    """Panel showing changes to review, matching the mock layout."""

    DEFAULT_CSS = """
    MockChangesPanel {
        border: round green;
        border-title-color: white;
        border-title-style: bold;
        padding: 1 2;
        height: 10;
        width: 1fr;
        background: $surface;
    }
    """

    def __init__(self):
        super().__init__()
        self.border_title = "Changes to Review"

    def compose(self) -> ComposeResult:
        yield Static("◦ src/auth.py:45-52     [HIGH 95%]", classes="file-entry")
        yield Static("◦ src/dashboard.py:15-23 [HIGH 89%]", classes="file-entry")
        yield Static("◦ tests/test_auth.py:67-70 [MED 76%]", classes="file-entry")
        yield Static("◦ src/utils.py:12-18    [FALLBACK]", classes="fallback-entry")


class MockTargetPanel(Widget):
    """Panel showing target commits, matching the mock layout."""

    DEFAULT_CSS = """
    MockTargetPanel {
        border: round cyan;
        border-title-color: white;
        border-title-style: bold;
        padding: 1 2;
        height: 10;
        width: 1fr;
        background: $surface;
    }
    """

    def __init__(self):
        super().__init__()
        self.border_title = "Target Commits"

    def compose(self) -> ComposeResult:
        yield Static("abc123 Fix login validation (2 days ago)", classes="commit-entry")
        yield Static("def456 Add user dashboard (3 days ago)", classes="commit-entry")
        yield Static("ghi012 Update auth tests (4 days ago)", classes="commit-entry")
        yield Static("❓ No clear target - needs review", classes="needs-review")


class MockPreviewPanel(Widget):
    """Panel showing diff preview, matching the mock layout."""

    DEFAULT_CSS = """
    MockPreviewPanel {
        border: round white;
        border-title-color: white;  
        border-title-style: bold;
        padding: 1 2;
        height: 12;
        width: 1fr;
        background: $surface;
        margin-top: 1;
    }
    """

    def __init__(self):
        super().__init__()
        self.border_title = "Preview: src/auth.py:45-52"

    def compose(self) -> ComposeResult:
        yield Static(
            " 44     def validate_login(self, email, password):", classes="diff-context"
        )
        yield Static(
            " 45 -       if not email or not password:", classes="diff-removed"
        )
        yield Static(
            " 45 +       if not email or not password or len(password) < 8:",
            classes="diff-added",
        )
        yield Static(
            " 46 +           raise ValueError('Invalid credentials')",
            classes="diff-added",
        )
        yield Static(
            " 47 -       return self.check_user(email, password)",
            classes="diff-removed",
        )
        yield Static(
            " 47 +       return self.check_user(email.lower(), password)",
            classes="diff-added",
        )
        yield Static(" 48     def logout_user(self):", classes="diff-context")


class BorderResearchApp(App):
    """Demo app showing Textual border capabilities matching the mock."""

    TITLE = "git-autosquash - Interactive Hunk Target Selection"

    CSS = """
    Screen {
        background: $background;
        color: $text;
    }
    
    .file-entry {
        color: $success;
        margin: 0 0 0 1;
    }
    
    .fallback-entry {
        color: $warning;
        margin: 0 0 0 1;
    }
    
    .commit-entry {
        color: $primary;
        margin: 0 0 0 1;
    }
    
    .needs-review {
        color: $error;
        margin: 0 0 0 1;
    }
    
    .diff-context {
        color: $text-muted;
    }
    
    .diff-added {
        color: $success;
    }
    
    .diff-removed {
        color: $error;
    }
    
    #top-panels {
        height: 12;
    }
    
    #controls {
        height: 3;
        border: round $primary;
        border-title-color: white;
        border-title-style: bold;
        padding: 1 2;
        background: $surface;
        margin-top: 1;
        text-align: center;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()

        with Container():
            # Top row: Changes and Target panels side by side
            with Horizontal(id="top-panels"):
                yield MockChangesPanel()
                yield MockTargetPanel()

            # Bottom: Diff preview panel
            yield MockPreviewPanel()

            # Controls panel with border and title
            with Static(
                "[Space] Toggle approval  [Enter] Apply changes  [Tab] Switch panels  [q] Quit",
                id="controls",
            ) as controls:
                controls.border_title = "Controls"

        yield Footer()


def main():
    """Run the border research demo."""
    print("🔬 Textual Border Research Demo")
    print(
        "This demonstrates rounded corners with inline titles like the mock screenshot."
    )
    print("Press Ctrl+C to exit.")
    print()

    app = BorderResearchApp()
    app.run()


if __name__ == "__main__":
    main()
