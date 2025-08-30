#!/usr/bin/env python3
"""
Textual Border Quick Reference
Key techniques for creating styled borders with titles
"""

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Static
from textual.widget import Widget


class BorderShowcase(Widget):
    """Quick examples of different border styles with titles."""

    def compose(self) -> ComposeResult:
        with Vertical():
            # Example 1: Basic rounded border with title
            basic = Static("Content goes here\nMultiple lines supported")
            basic.border_title = "Changes to Review"
            basic.styles.border = ("round", "blue")
            basic.styles.padding = (1, 2)
            basic.styles.margin = 1
            yield basic

            # Example 2: Thick border with styled title
            thick = Static("Important content with thick border")
            thick.border_title = "Critical Section"
            thick.border_subtitle = "Handle with care"
            thick.styles.border = ("thick", "red")
            thick.styles.border_title_color = "yellow"
            thick.styles.border_title_style = "bold"
            thick.styles.padding = 1
            thick.styles.margin = (0, 0, 1, 0)
            yield thick

            # Example 3: Panel-style border
            panel = Static("Panel content with soft appearance")
            panel.border_title = "Settings Panel"
            panel.styles.border = ("solid", "gray")
            panel.styles.background = "#1e1e1e"
            panel.styles.color = "white"
            panel.styles.padding = 1
            panel.styles.margin = 1
            yield panel

            # Example 4: CSS-styled border (more complex)
            yield CSSStyledWidget()


class CSSStyledWidget(Static):
    """Widget using CSS for advanced border styling."""

    BORDER_TITLE = "Git Diff Preview"
    BORDER_SUBTITLE = "Press 'e' to edit"

    DEFAULT_CSS = """
    CSSStyledWidget {
        /* Rounded border with primary color */
        border: round $primary;
        
        /* Title styling */
        border-title-color: $accent;
        border-title-style: bold;
        border-title-align: center;
        
        /* Subtitle styling */
        border-subtitle-color: $text-muted;
        border-subtitle-style: italic;
        border-subtitle-align: right;
        
        /* Container styling */
        background: $surface;
        padding: 1 2;
        margin: 1;
        height: auto;
        min-height: 5;
    }
    
    CSSStyledWidget.focused {
        border: thick $accent;
        border-title-color: $success;
    }
    
    CSSStyledWidget.error {
        border: round $error;
        border-title-color: $error;
        background: $error-darken-3;
    }
    """

    def __init__(self):
        super().__init__(
            "@@ -10,3 +10,7 @@ def function():\n"
            "     return value\n"
            "+    # Added comment\n"
            "+    new_feature()\n"
            "+    return enhanced_value"
        )


class QuickReferenceApp(App):
    """Quick reference for Textual border techniques."""

    CSS = """
    App {
        background: $background;
    }
    """

    def compose(self) -> ComposeResult:
        yield BorderShowcase()

    def on_key(self, event) -> None:
        """Demonstrate dynamic styling changes."""
        if event.key == "f":
            # Toggle focus styling
            css_widget = self.query_one(CSSStyledWidget)
            css_widget.toggle_class("focused")
        elif event.key == "e":
            # Toggle error styling
            css_widget = self.query_one(CSSStyledWidget)
            css_widget.toggle_class("error")


if __name__ == "__main__":
    print("Textual Border Quick Reference")
    print("==============================")
    print()
    print("Key Border Techniques:")
    print("1. Set border_title on any widget")
    print("2. Use styles.border = ('round', 'color') for rounded corners")
    print("3. Apply border styling via CSS classes")
    print("4. Use border-title-color, border-title-style for title appearance")
    print()
    print("Press 'f' to toggle focus styling, 'e' to toggle error styling")
    print("Press Ctrl+C to exit")
    print()

    app = QuickReferenceApp()
    app.run()
