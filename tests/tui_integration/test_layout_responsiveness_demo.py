"""Demonstration test showing current layout responsiveness works correctly."""

import pytest

from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp
from tests.tui_integration.helpers import MockDataGenerator


class TestLayoutResponsivenessDemo:
    """Demonstrate that the current layout is already properly responsive."""

    @pytest.mark.asyncio
    async def test_responsiveness_summary(self, mock_commit_history_analyzer):
        """Comprehensive test showing layout responsiveness across different sizes."""
        mappings = MockDataGenerator.create_mock_mappings(3, 2)

        # Test various terminal sizes
        test_sizes = [
            (40, 12, "tiny"),
            (60, 20, "small"),
            (80, 24, "medium"),
            (120, 30, "large"),
        ]

        results = []

        for width, height, label in test_sizes:
            app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
            async with app.run_test(size=(width, height)) as pilot:
                await pilot.pause(0.1)

                # Get key components
                main_container = pilot.app.screen.query_one("#main-container")
                content_area = pilot.app.screen.query_one("#content-area")
                action_buttons = pilot.app.screen.query_one("#action-buttons")
                hunk_panel = pilot.app.screen.query_one("#hunk-list-panel")
                diff_panel = pilot.app.screen.query_one("#diff-panel")

                # Collect measurements
                result = {
                    "size": f"{width}x{height}",
                    "label": label,
                    "container_height": main_container.region.height,
                    "content_height": content_area.region.height,
                    "button_y": action_buttons.region.y,
                    "button_height": action_buttons.region.height,
                    "button_bottom": action_buttons.region.bottom,
                    "hunk_panel_width": hunk_panel.region.width,
                    "diff_panel_width": diff_panel.region.width,
                    "screen_height": height,
                    "screen_width": width,
                }

                # Verify buttons are at bottom
                assert result["button_bottom"] <= height, (
                    f"Buttons extend beyond screen in {label} terminal: "
                    f"{result['button_bottom']} > {height}"
                )

                # Verify buttons are near bottom (within 4 rows)
                assert result["button_bottom"] >= height - 4, (
                    f"Buttons not at bottom in {label} terminal: "
                    f"{result['button_bottom']} < {height - 4}"
                )

                # Verify content uses available space (check that content exists)
                assert result["content_height"] > 0, (
                    f"No content area in {label} terminal"
                )

                # For larger terminals, verify good space utilization
                if height >= 20:
                    content_ratio = result["content_height"] / height
                    assert content_ratio >= 0.35, (
                        f"Content area inefficient in {label} terminal: "
                        f"{content_ratio:.2%} of screen height"
                    )

                # Verify horizontal panels use screen width
                panel_width_total = (
                    result["hunk_panel_width"] + result["diff_panel_width"]
                )
                width_ratio = panel_width_total / width
                assert width_ratio > 0.8, (
                    f"Panels don't use enough width in {label} terminal: "
                    f"{width_ratio:.2%} of screen width"
                )

                results.append(result)

        # Print summary to show responsiveness working
        print("\\n=== Layout Responsiveness Summary ===")
        for result in results:
            print(
                f"{result['label'].upper():>6} ({result['size']:>7}): "
                f"Content={result['content_height']:>2}h, "
                f"Buttons at y={result['button_y']:>2}, "
                f"Panels={result['hunk_panel_width']:>2}+{result['diff_panel_width']:>2}w"
            )

        # Verify consistent button positioning across sizes
        button_positions_from_bottom = [
            result["screen_height"] - result["button_y"] for result in results
        ]

        # All buttons should be positioned similarly from the bottom
        position_variance = max(button_positions_from_bottom) - min(
            button_positions_from_bottom
        )
        assert position_variance <= 2, (
            f"Button position variance too high: {position_variance} rows. "
            f"Positions from bottom: {button_positions_from_bottom}"
        )

        print(
            f"✓ Button positions consistent: {button_positions_from_bottom} rows from bottom"
        )
        print("✓ Layout properly responsive across all terminal sizes")

    @pytest.mark.asyncio
    async def test_layout_structure_is_optimal(self, mock_commit_history_analyzer):
        """Verify the current CSS layout structure is already optimal for responsiveness."""
        mappings = MockDataGenerator.create_mock_mappings(2, 1)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)

            # Verify layout hierarchy matches expectations
            main_container = pilot.app.screen.query_one("#main-container")
            content_wrapper = pilot.app.screen.query_one("#content-wrapper")
            content_area = pilot.app.screen.query_one("#content-area")
            action_buttons = pilot.app.screen.query_one("#action-buttons")

            # Main container should fill screen minus header/footer
            expected_height = 24 - 2  # Header + Footer = 2 rows
            assert main_container.region.height == expected_height, (
                f"Main container not correct height: {main_container.region.height} != {expected_height}"
            )

            # Content wrapper should be flexible (1fr)
            # Buttons should be fixed height (3)
            # Together they should fill the main container
            total_used = content_wrapper.region.height + action_buttons.region.height

            # Allow for some margin/padding/borders
            assert abs(total_used - expected_height) <= 3, (
                f"Layout doesn't fill main container efficiently: "
                f"content={content_wrapper.region.height} + "
                f"buttons={action_buttons.region.height} = {total_used} "
                f"(container={expected_height})"
            )

            # Verify horizontal panels split width equally (1fr each)
            hunk_panel = pilot.app.screen.query_one("#hunk-list-panel")
            diff_panel = pilot.app.screen.query_one("#diff-panel")

            width_diff = abs(hunk_panel.region.width - diff_panel.region.width)
            assert width_diff <= 2, (
                f"Panels not split equally: "
                f"hunk={hunk_panel.region.width}, diff={diff_panel.region.width}, "
                f"diff={width_diff}"
            )

            print("✓ Current layout structure is optimal for responsive behavior")
            print(f"  - Main container: {main_container.region.height}h (fills screen)")
            print(f"  - Content wrapper: {content_wrapper.region.height}h (flexible)")
            print(f"  - Action buttons: {action_buttons.region.height}h (fixed)")
            print(
                f"  - Panel split: {hunk_panel.region.width}w + {diff_panel.region.width}w"
            )
