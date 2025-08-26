"""Final verification test showing button positioning fix."""

import pytest
from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp
from tests.tui_integration.helpers import MockDataGenerator


class TestFinalLayoutVerification:
    """Final verification that layout issues are resolved."""

    @pytest.mark.asyncio
    async def test_complete_layout_verification(self, mock_commit_history_analyzer):
        """Comprehensive test showing all layout issues are resolved."""
        mappings = MockDataGenerator.create_mock_mappings(3, 2)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)

            # Get all components
            header = pilot.app.screen.query_one("Header")
            main_container = pilot.app.screen.query_one("#main-container")
            content_area = pilot.app.screen.query_one("#content-area")
            action_buttons = pilot.app.screen.query_one("#action-buttons")
            footer = pilot.app.screen.query_one("Footer")

            # Verify layout hierarchy and positioning
            print("\\n=== Final Layout Verification ===")
            print("Terminal size: 80x24 (rows 0-23)")
            print(f"Header: y={header.region.y}, height={header.region.height}")
            print(
                f"Main container: y={main_container.region.y}, height={main_container.region.height}"
            )
            print(
                f"Content area: y={content_area.region.y}, height={content_area.region.height}"
            )
            print(
                f"Action buttons: y={action_buttons.region.y}-{action_buttons.region.bottom - 1}, height={action_buttons.region.height}"
            )
            print(f"Footer: y={footer.region.y}, height={footer.region.height}")

            # ✅ Verify buttons are properly positioned at bottom
            assert action_buttons.region.bottom <= 23, (
                f"Buttons extend beyond screen: {action_buttons.region.bottom} > 23"
            )

            # ✅ Verify Footer doesn't overlap buttons
            button_bottom = action_buttons.region.bottom
            footer_top = footer.region.y
            assert button_bottom <= footer_top, (
                f"Buttons overlap Footer: button_bottom={button_bottom}, footer_top={footer_top}"
            )

            # ✅ Verify there's appropriate gap
            gap = footer_top - button_bottom
            assert gap >= 0, f"Buttons overlap Footer: gap={gap}"
            print(f"Gap between buttons and Footer: {gap} row(s)")

            # ✅ Verify buttons are still close to bottom (not too high up)
            buttons_from_bottom = 24 - action_buttons.region.bottom
            assert buttons_from_bottom <= 3, (
                f"Buttons too far from bottom: {buttons_from_bottom} rows from bottom"
            )

            # ✅ Verify content area has reasonable space
            assert content_area.region.height >= 8, (
                f"Content area too small: {content_area.region.height} rows"
            )

            # ✅ Verify responsive behavior
            hunk_panel = pilot.app.screen.query_one("#hunk-list-panel")
            diff_panel = pilot.app.screen.query_one("#diff-panel")
            total_panel_width = hunk_panel.region.width + diff_panel.region.width
            width_efficiency = total_panel_width / 80
            assert width_efficiency >= 0.8, (
                f"Poor width utilization: {width_efficiency:.1%}"
            )

            print(
                f"✅ Buttons positioned correctly: {buttons_from_bottom} rows from bottom edge"
            )
            print(f"✅ No Footer overlap: {gap} row gap")
            print(
                f"✅ Content area: {content_area.region.height} rows (sufficient space)"
            )
            print(
                f"✅ Width utilization: {width_efficiency:.1%} (panels: {hunk_panel.region.width}+{diff_panel.region.width})"
            )
            print("✅ All layout issues resolved!")

    @pytest.mark.asyncio
    async def test_cross_terminal_size_verification(self, mock_commit_history_analyzer):
        """Verify fix works across different terminal sizes."""
        mappings = MockDataGenerator.create_mock_mappings(2, 1)

        sizes_to_test = [
            (60, 15, "small"),
            (80, 24, "standard"),
            (120, 30, "large"),
            (40, 12, "tiny"),
        ]

        print("\\n=== Cross-Size Verification ===")

        for width, height, label in sizes_to_test:
            app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
            async with app.run_test(size=(width, height)) as pilot:
                await pilot.pause(0.1)

                action_buttons = pilot.app.screen.query_one("#action-buttons")
                footer = pilot.app.screen.query_one("Footer")

                # Check Footer doesn't overlap buttons
                button_bottom = action_buttons.region.bottom
                footer_top = footer.region.y
                gap = footer_top - button_bottom

                assert gap >= 0, (
                    f"Buttons overlap Footer in {label} terminal ({width}x{height}): gap={gap}"
                )

                # Check buttons are positioned near bottom but not off-screen
                assert button_bottom <= height, (
                    f"Buttons off-screen in {label} terminal: {button_bottom} > {height}"
                )

                buttons_from_bottom = height - button_bottom
                assert buttons_from_bottom <= 4, (
                    f"Buttons too high in {label} terminal: {buttons_from_bottom} rows from bottom"
                )

                print(
                    f"{label:>8} ({width:>3}x{height:>2}): buttons end y={button_bottom:>2}, footer y={footer_top:>2}, gap={gap}"
                )

        print("✅ Footer-button positioning fixed across all terminal sizes!")
