"""Helper utilities for TUI integration testing."""

import re
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass

import pyte
from textual.pilot import Pilot


@dataclass
class WidgetBounds:
    """Represents the bounds of a widget on screen."""

    top: int
    left: int
    bottom: int
    right: int
    width: int
    height: int


class TextualAssertions:
    """Helper class for making assertions about Textual app state."""

    @staticmethod
    async def assert_widget_visible(
        pilot: Pilot, widget_id: str, timeout: float = 3.0
    ) -> None:
        """Assert that a widget with the given ID is visible on screen."""
        try:
            widget = pilot.app.screen.query_one(f"#{widget_id}")
        except Exception:
            # Fallback to app query if not found in screen
            widget = pilot.app.query_one(f"#{widget_id}")
        assert widget is not None, f"Widget with ID '{widget_id}' not found"
        assert widget.display, f"Widget '{widget_id}' is not displayed"

    @staticmethod
    async def assert_button_at_bottom(
        pilot: Pilot, button_text: str, tolerance: int = 5
    ) -> None:
        """Assert that a button is positioned near the bottom of the screen."""
        # Look for buttons in the current screen, not the root app
        buttons = pilot.app.screen.query("Button")
        target_button = None

        for button in buttons:
            if button_text in str(button.label):
                target_button = button
                break

        assert target_button is not None, f"Button with text '{button_text}' not found"

        screen_height = pilot.app.screen.size.height
        button_bottom = target_button.region.bottom

        assert button_bottom >= screen_height - tolerance, (
            f"Button '{button_text}' not at bottom. Bottom at: {button_bottom}, "
            f"Screen height: {screen_height}, Expected within {tolerance} of bottom"
        )

    @staticmethod
    async def assert_radio_selected(pilot: Pilot, radio_label_pattern: str) -> None:
        """Assert that a radio button matching the pattern is selected."""
        radio_buttons = pilot.app.screen.query("RadioButton")

        for radio in radio_buttons:
            if re.search(radio_label_pattern, str(radio.label)):
                assert radio.value, (
                    f"Radio button matching '{radio_label_pattern}' is not selected"
                )
                return

        assert False, f"No radio button found matching pattern '{radio_label_pattern}'"

    @staticmethod
    async def assert_text_in_screen(pilot: Pilot, text: str) -> None:
        """Assert that specific text appears somewhere on screen."""
        # Get all visible text widgets from current screen
        text_widgets = pilot.app.screen.query("Static")

        found = False
        for widget in text_widgets:
            if hasattr(widget, "renderable") and text in str(widget.renderable):
                found = True
                break

        assert found, f"Text '{text}' not found on screen"

    @staticmethod
    async def get_progress_text(pilot: Pilot) -> Optional[str]:
        """Extract the progress text from screen."""
        try:
            description_widget = pilot.app.screen.query_one("#screen-description")
        except Exception:
            description_widget = pilot.app.query_one("#screen-description")
        if description_widget and hasattr(description_widget, "renderable"):
            return str(description_widget.renderable)
        return None


class PyteScreenAnalyzer:
    """Helper class for analyzing terminal screen content using pyte."""

    def __init__(self, width: int = 80, height: int = 24):
        self.screen = pyte.Screen(width, height)
        self.stream = pyte.ByteStream(self.screen)

    def feed_terminal_output(self, output: bytes) -> None:
        """Feed terminal output to the screen."""
        self.stream.feed(output)

    def find_text_position(self, text: str) -> List[Tuple[int, int]]:
        """Find all positions where text appears on screen."""
        positions = []

        for row_idx, line in enumerate(self.screen.display):
            line_text = "".join(char.data for char in line)
            col_idx = 0
            while True:
                found_idx = line_text.find(text, col_idx)
                if found_idx == -1:
                    break
                positions.append((row_idx, found_idx))
                col_idx = found_idx + 1

        return positions

    def get_text_at_position(self, row: int, col: int, length: int = None) -> str:
        """Get text at a specific position."""
        if row >= len(self.screen.display) or row < 0:
            return ""

        line = self.screen.display[row]
        if col >= len(line) or col < 0:
            return ""

        if length is None:
            return "".join(char.data for char in line[col:])
        else:
            return "".join(char.data for char in line[col : col + length])

    def get_widget_bounds(self, widget_identifier: str) -> Optional[WidgetBounds]:
        """
        Get the bounds of a widget by identifying it on screen.

        Args:
            widget_identifier: Text that uniquely identifies the widget

        Returns:
            WidgetBounds if found, None otherwise
        """
        positions = self.find_text_position(widget_identifier)
        if not positions:
            return None

        # For simplicity, use the first occurrence
        # In a real implementation, you might want more sophisticated logic
        row, col = positions[0]

        # Try to determine bounds by looking for borders or spacing
        # This is a simplified implementation
        return WidgetBounds(
            top=row,
            left=col,
            bottom=row + 1,
            right=col + len(widget_identifier),
            width=len(widget_identifier),
            height=1,
        )

    def verify_no_overlap(self, widgets: List[str]) -> bool:
        """Verify that widgets don't overlap on screen."""
        bounds_list = []

        for widget in widgets:
            bounds = self.get_widget_bounds(widget)
            if bounds:
                bounds_list.append(bounds)

        # Check for overlaps
        for i, bounds1 in enumerate(bounds_list):
            for j, bounds2 in enumerate(bounds_list[i + 1 :], i + 1):
                if self._bounds_overlap(bounds1, bounds2):
                    return False

        return True

    def _bounds_overlap(self, bounds1: WidgetBounds, bounds2: WidgetBounds) -> bool:
        """Check if two widget bounds overlap."""
        return not (
            bounds1.right <= bounds2.left
            or bounds2.right <= bounds1.left
            or bounds1.bottom <= bounds2.top
            or bounds2.bottom <= bounds1.top
        )

    def get_screen_content(self) -> List[str]:
        """Get all screen content as list of strings."""
        return ["".join(char.data for char in line) for line in self.screen.display]

    def assert_text_at_position(self, row: int, col: int, expected_text: str) -> None:
        """Assert that specific text appears at given coordinates."""
        actual_text = self.get_text_at_position(row, col, len(expected_text))
        assert actual_text == expected_text, (
            f"Expected '{expected_text}' at position ({row}, {col}), "
            f"but found '{actual_text}'"
        )

    def get_color_at_position(self, row: int, col: int) -> Optional[str]:
        """Get ANSI color information at a specific position."""
        if (
            row >= len(self.screen.display)
            or row < 0
            or col >= len(self.screen.display[row])
            or col < 0
        ):
            return None

        char = self.screen.display[row][col]
        # Return simplified color info - in real implementation you'd parse ANSI codes
        if hasattr(char, "fg"):
            return f"fg_{char.fg}"
        return None


class MockDataGenerator:
    """Helper class for generating mock test data."""

    @staticmethod
    def create_mock_mappings(
        blame_count: int, fallback_count: int
    ) -> List[Dict[str, Any]]:
        """Create mock HunkTargetMapping data."""
        from git_autosquash.hunk_parser import DiffHunk
        from git_autosquash.hunk_target_resolver import (
            HunkTargetMapping,
            TargetingMethod,
        )

        mappings = []

        # Create blame matches
        for i in range(blame_count):
            hunk = DiffHunk(
                file_path=f"file_{i}.py",
                old_start=i + 10,
                old_count=3,
                new_start=i + 10,
                new_count=3,
                lines=[
                    f"@@ -{i + 10},3 +{i + 10},3 @@",
                    f"- old_line_{i}",
                    f"+ new_line_{i}",
                ],
                context_before=[],
                context_after=[],
            )

            mapping = HunkTargetMapping(
                hunk=hunk,
                target_commit=f"commit_hash_{i:08d}",
                confidence="high" if i % 2 == 0 else "medium",
                blame_info=[],
                targeting_method=TargetingMethod.BLAME_MATCH,
                needs_user_selection=False,
            )
            mappings.append(mapping)

        # Create fallback mappings
        for i in range(fallback_count):
            hunk = DiffHunk(
                file_path=f"fallback_file_{i}.py",
                old_start=i + 50,
                old_count=2,
                new_start=i + 50,
                new_count=4,
                lines=[
                    f"@@ -{i + 50},2 +{i + 50},4 @@",
                    f"+ added_line_{i}",
                    f"+ another_line_{i}",
                ],
                context_before=[],
                context_after=[],
            )

            mapping = HunkTargetMapping(
                hunk=hunk,
                target_commit=None,
                confidence="low",
                blame_info=[],
                targeting_method=TargetingMethod.FALLBACK_EXISTING_FILE,
                fallback_candidates=[f"candidate_{j:08d}" for j in range(3)],
                needs_user_selection=True,
            )
            mappings.append(mapping)

        return mappings

    @staticmethod
    def create_mock_commit_history(num_commits: int) -> List[Dict[str, Any]]:
        """Create mock commit history data."""
        commits = []

        for i in range(num_commits):
            commit = {
                "commit_hash": f"commit_hash_{i:040d}",
                "short_hash": f"commit_{i:08d}",
                "subject": f"Commit message {i}: Fix issue in component",
                "author": f"Author {i % 5}",  # Cycle through 5 authors
                "timestamp": 1756174372 - (i * 3600),  # One hour apart
                "is_merge": i % 10 == 0,  # Every 10th commit is a merge
                "files_touched": [f"file_{i % 3}.py", f"test_{i % 3}.py"],
            }
            commits.append(commit)

        return commits


def capture_textual_output(app_output: str) -> bytes:
    """Convert Textual app output to bytes for pyte processing."""
    # In practice, you'd capture the actual terminal escape sequences
    # This is a simplified version for demonstration
    return app_output.encode("utf-8")


async def simulate_user_workflow(pilot: Pilot, actions: List[Dict[str, Any]]) -> None:
    """
    Simulate a complete user workflow with the TUI.

    Args:
        pilot: Textual pilot for controlling the app
        actions: List of actions to perform, each with 'type' and parameters
    """
    for action in actions:
        action_type = action["type"]

        if action_type == "key":
            await pilot.press(action["key"])
        elif action_type == "click":
            await pilot.click(action["selector"])
        elif action_type == "wait":
            await pilot.pause(action.get("duration", 0.1))
        elif action_type == "assert_text":
            await TextualAssertions.assert_text_in_screen(pilot, action["text"])
        elif action_type == "assert_visible":
            await TextualAssertions.assert_widget_visible(pilot, action["widget_id"])

        # Small pause between actions for realism
        await pilot.pause(0.05)
