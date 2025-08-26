"""Test to verify Footer doesn't overlap with action buttons."""

import pytest
from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp
from tests.tui_integration.helpers import MockDataGenerator


class TestFooterButtonOverlap:
    """Test Footer and button positioning to avoid overlap."""

    @pytest.mark.asyncio
    async def test_footer_does_not_overlap_buttons(self, mock_commit_history_analyzer):
        """Test that Footer doesn't overlap with action buttons."""
        mappings = MockDataGenerator.create_mock_mappings(2, 1)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        # Test with standard terminal size
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            
            # Get Footer and buttons
            footer = pilot.app.screen.query_one("Footer")
            action_buttons = pilot.app.screen.query_one("#action-buttons")
            
            # Footer should be at the very bottom (y=23 in 24-row terminal)
            expected_footer_y = 23  # Last row (0-indexed)
            assert footer.region.y == expected_footer_y, (
                f"Footer not at bottom: y={footer.region.y}, expected y={expected_footer_y}"
            )
            
            # Buttons should not overlap with Footer
            button_bottom = action_buttons.region.bottom
            footer_top = footer.region.y
            
            assert button_bottom <= footer_top, (
                f"Buttons overlap Footer: button_bottom={button_bottom}, footer_top={footer_top}"
            )
            
            print(f"✓ Footer at y={footer.region.y}, buttons end at y={button_bottom}")

    @pytest.mark.asyncio
    async def test_buttons_visible_with_footer_different_sizes(self, mock_commit_history_analyzer):
        """Test button visibility with Footer across different terminal sizes."""
        mappings = MockDataGenerator.create_mock_mappings(3, 2)
        
        test_sizes = [(60, 20), (80, 24), (100, 30)]
        
        for width, height in test_sizes:
            app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
            async with app.run_test(size=(width, height)) as pilot:
                await pilot.pause(0.1)
                
                footer = pilot.app.screen.query_one("Footer") 
                action_buttons = pilot.app.screen.query_one("#action-buttons")
                
                # Footer should be at last row
                expected_footer_y = height - 1
                assert footer.region.y == expected_footer_y, (
                    f"Footer wrong position in {width}x{height}: "
                    f"y={footer.region.y}, expected y={expected_footer_y}"
                )
                
                # Buttons should be fully visible above Footer
                button_bottom = action_buttons.region.bottom
                assert button_bottom <= expected_footer_y, (
                    f"Buttons overlap Footer in {width}x{height}: "
                    f"button_bottom={button_bottom}, footer_y={expected_footer_y}"
                )
                
                # Buttons should still be near the bottom (not too high up)
                gap_from_footer = expected_footer_y - button_bottom
                assert gap_from_footer <= 1, (
                    f"Buttons too far from Footer in {width}x{height}: gap={gap_from_footer}"
                )
                
                print(f"✓ {width}x{height}: Footer y={footer.region.y}, buttons end y={button_bottom}")

    @pytest.mark.asyncio
    async def test_content_area_accounts_for_footer(self, mock_commit_history_analyzer):
        """Test that content area properly accounts for Footer space."""
        mappings = MockDataGenerator.create_mock_mappings(4, 2)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            
            # Get all major components
            header = pilot.app.screen.query_one("Header")
            main_container = pilot.app.screen.query_one("#main-container") 
            content_area = pilot.app.screen.query_one("#content-area")
            action_buttons = pilot.app.screen.query_one("#action-buttons")
            footer = pilot.app.screen.query_one("Footer")
            
            # Calculate total used space
            used_space = (
                header.region.height +      # Header: 1 row
                main_container.region.height +  # Main content
                footer.region.height        # Footer: 1 row
            )
            
            # Should use the full screen height
            assert used_space <= 24, (
                f"Layout uses too much space: {used_space} > 24. "
                f"Header={header.region.height}, Main={main_container.region.height}, "
                f"Footer={footer.region.height}"
            )
            
            # Content should still have reasonable space
            assert content_area.region.height >= 8, (
                f"Content area too small: {content_area.region.height} rows"
            )
            
            print(f"✓ Space usage: Header={header.region.height} + Main={main_container.region.height} + Footer={footer.region.height} = {used_space}/24")
            print(f"✓ Content area: {content_area.region.height} rows")