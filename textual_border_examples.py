#!/usr/bin/env python3
"""
Textual Framework Border Examples
Demonstrates how to create styled borders with rounded corners and inline titles
"""

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Button
from textual.widget import Widget


class BorderedContainer(Static):
    """Container widget with styled border and title."""

    BORDER_TITLE = "Changes to Review"  # Class-level title

    DEFAULT_CSS = """
    BorderedContainer {
        border: round $primary;
        padding: 1;
        margin: 1;
        height: auto;
        min-height: 10;
    }
    
    BorderedContainer.highlighted {
        border: thick $accent;
    }
    
    BorderedContainer.warning {
        border: round $warning;
    }
    """


class TitledPanel(Widget):
    """Panel with inline title in the border."""

    def __init__(self, title: str, content: str, **kwargs):
        super().__init__(**kwargs)
        self.border_title = title  # Instance-level title
        self.content = content

    DEFAULT_CSS = """
    TitledPanel {
        border: round $surface;
        padding: 1;
        margin: 1 0;
        height: auto;
        background: $boost;
    }
    
    TitledPanel.selected {
        border: thick $success;
        border-title-color: $success;
    }
    
    TitledPanel.error {
        border: round $error;
        border-title-color: $error;
        border-title-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(self.content, classes="panel-content")


class StyledBorderWidget(Widget):
    """Demonstrates various border styling options."""

    BORDER_TITLE = "Hunk Analysis"
    BORDER_SUBTITLE = "Press Enter to edit"

    DEFAULT_CSS = """
    StyledBorderWidget {
        border: round $primary;
        border-title-align: center;
        border-title-color: $primary;
        border-title-style: bold;
        border-subtitle-color: $text-muted;
        border-subtitle-style: italic;
        padding: 2;
        margin: 1;
        height: auto;
        min-height: 8;
        background: $surface;
    }
    
    StyledBorderWidget.focused {
        border: thick $accent;
        border-title-color: $accent;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("File: src/example.py", classes="file-name")
            yield Static("@@ -15,7 +15,9 @@ def example():", classes="diff-header")
            yield Static("+ Added line 1", classes="diff-added")
            yield Static("+ Added line 2", classes="diff-added")
            yield Static("- Removed line", classes="diff-removed")


class ResponsiveContainer(Widget):
    """Container that adapts border style based on content."""

    def __init__(self, title: str, items: list[str], **kwargs):
        super().__init__(**kwargs)
        self.border_title = title
        self.items = items

        # Dynamic subtitle based on content
        self.border_subtitle = f"{len(items)} items"

    DEFAULT_CSS = """
    ResponsiveContainer {
        border: round $primary;
        border-title-align: left;
        border-title-color: $primary;
        border-title-style: bold;
        border-subtitle-align: right;
        border-subtitle-color: $text-muted;
        padding: 1;
        margin: 1 0;
        height: auto;
        background: $panel;
    }
    
    ResponsiveContainer.many-items {
        border: thick $warning;
        border-title-color: $warning;
    }
    
    ResponsiveContainer.empty {
        border: dashed $error;
        border-title-color: $error;
        opacity: 0.7;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            for item in self.items:
                yield Static(f"• {item}", classes="list-item")

    def on_mount(self) -> None:
        # Apply dynamic styling based on content
        if len(self.items) == 0:
            self.add_class("empty")
        elif len(self.items) > 5:
            self.add_class("many-items")


class NestedBordersExample(Widget):
    """Shows nested containers with different border styles."""

    BORDER_TITLE = "Git Operations"

    DEFAULT_CSS = """
    NestedBordersExample {
        border: round $primary;
        padding: 1;
        margin: 1;
        height: auto;
        background: $surface;
    }
    
    NestedBordersExample .inner-container {
        border: solid $secondary;
        padding: 1;
        margin: 1 0;
        background: $panel;
    }
    
    NestedBordersExample .action-group {
        border: dashed $accent;
        border-title-color: $accent;
        border-title-style: underline;
        padding: 1;
        margin: 0 0 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            # Nested container with its own border
            inner = Static("Staging Area", classes="inner-container")
            inner.border_title = "Current Changes"
            yield inner

            # Action buttons in bordered container
            actions = Horizontal(classes="action-group")
            actions.border_title = "Actions"
            with actions:
                yield Button("Commit", variant="primary")
                yield Button("Reset", variant="warning")
                yield Button("Stash", variant="default")
            yield actions


class BorderExamplesApp(App):
    """Main app demonstrating various border styling techniques."""

    CSS = """
    /* Global color scheme */
    App {
        background: $background;
    }
    
    /* Content styling */
    .file-name {
        color: $primary;
        text-style: bold;
    }
    
    .diff-header {
        color: $text-muted;
        text-style: italic;
    }
    
    .diff-added {
        color: $success;
    }
    
    .diff-removed {
        color: $error;
    }
    
    .panel-content {
        padding: 0;
        margin: 0;
    }
    
    .list-item {
        padding: 0;
        margin: 0;
        height: 1;
    }
    
    /* Button styling within borders */
    Button {
        margin: 0 1;
        min-width: 10;
    }
    """

    def compose(self) -> ComposeResult:
        with Container():
            # Basic bordered container with class-level title
            yield BorderedContainer(
                "This is content within a rounded border container."
            )

            # Panel with instance-level title
            yield TitledPanel(
                "File Status", "Modified: 3 files\nAdded: 1 file\nDeleted: 0 files"
            )

            # Styled border widget with title and subtitle
            yield StyledBorderWidget()

            # Responsive container with dynamic styling
            yield ResponsiveContainer(
                "Commit History",
                ["feat: add new feature", "fix: resolve bug", "docs: update README"],
            )

            # Empty container example
            yield ResponsiveContainer("Empty List", [])

            # Nested borders example
            yield NestedBordersExample()

    def on_mount(self) -> None:
        # Demonstrate dynamic border title changes
        titled_panel = self.query_one(TitledPanel)
        titled_panel.border_subtitle = "Last updated: now"

        # Add selection styling to one panel
        titled_panel.add_class("selected")


if __name__ == "__main__":
    app = BorderExamplesApp()
    app.run()
