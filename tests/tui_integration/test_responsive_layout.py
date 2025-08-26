"""Test responsive layout across different terminal sizes."""

import pytest
from textual.app import App

from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp
from tests.tui_integration.helpers import TextualAssertions, MockDataGenerator


class TestResponsiveLayout:
    """Test layout behavior across different terminal sizes."""

    @pytest.mark.asyncio
    async def test_button_positioning_small_terminal(self, mock_commit_history_analyzer):
        """Test button positioning in small terminal (40x12)."""
        mappings = MockDataGenerator.create_mock_mappings(2, 1)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        # Use small terminal size
        async with app.run_test(size=(40, 12)) as pilot:
            await pilot.pause(0.1)
            
            # Get buttons and verify they're at the bottom
            buttons = pilot.app.screen.query("Button")
            assert len(buttons) == 3, "Should have 3 action buttons"
            
            # Verify buttons are positioned at bottom of 12-row terminal (0-11)
            for button in buttons:
                button_bottom = button.region.bottom
                screen_height = pilot.app.screen.size.height
                # Buttons should be within last 4 rows of screen
                assert button_bottom >= screen_height - 4, (
                    f"Button not at bottom in small terminal. "
                    f"Bottom: {button_bottom}, Screen height: {screen_height}"
                )
    
    @pytest.mark.asyncio 
    async def test_button_positioning_large_terminal(self, mock_commit_history_analyzer):
        """Test button positioning in large terminal (120x30)."""
        mappings = MockDataGenerator.create_mock_mappings(2, 1)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        # Use large terminal size
        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause(0.1)
            
            # Get buttons and verify they're at the bottom
            buttons = pilot.app.screen.query("Button")
            assert len(buttons) == 3, "Should have 3 action buttons"
            
            # Verify buttons are positioned at bottom of 30-row terminal (0-29)
            for button in buttons:
                button_bottom = button.region.bottom
                screen_height = pilot.app.screen.size.height
                # Buttons should be within last 4 rows of screen
                assert button_bottom >= screen_height - 4, (
                    f"Button not at bottom in large terminal. "
                    f"Bottom: {button_bottom}, Screen height: {screen_height}"
                )

    @pytest.mark.asyncio
    async def test_scrolling_area_fills_available_space_small(self, mock_commit_history_analyzer):
        """Test that scrolling areas expand to fill available space in small terminal."""
        mappings = MockDataGenerator.create_mock_mappings(5, 3)  # More content
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        # Test with small size
        async with app.run_test(size=(60, 20)) as pilot:
            await pilot.pause(0.1)
            
            # Find scrollable content areas
            hunk_list = pilot.app.screen.query_one("#hunk-list")
            diff_viewer = pilot.app.screen.query_one("#diff-viewer")
            content_area = pilot.app.screen.query_one("#content-area")
            action_buttons = pilot.app.screen.query_one("#action-buttons")
            
            # Verify content area fills most of the screen (minus header, title, buttons)
            content_bottom = content_area.region.bottom
            buttons_top = action_buttons.region.y
            
            # Content should extend close to where buttons start
            gap = buttons_top - content_bottom
            assert gap <= 2, (
                f"Too much gap between content and buttons in small terminal. "
                f"Gap: {gap}, Content bottom: {content_bottom}, Buttons top: {buttons_top}"
            )
            
            # Verify scrollable areas have reasonable height
            assert hunk_list.region.height > 3, (
                f"Hunk list too short in small terminal: {hunk_list.region.height}"
            )
            assert diff_viewer.region.height > 3, (
                f"Diff viewer too short in small terminal: {diff_viewer.region.height}"
            )

    @pytest.mark.asyncio
    async def test_scrolling_area_fills_available_space_large(self, mock_commit_history_analyzer):
        """Test that scrolling areas expand to fill available space in large terminal."""
        mappings = MockDataGenerator.create_mock_mappings(5, 3)  # More content  
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        # Test with large size
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)
            
            # Find scrollable content areas
            hunk_list = pilot.app.screen.query_one("#hunk-list")
            diff_viewer = pilot.app.screen.query_one("#diff-viewer")
            content_area = pilot.app.screen.query_one("#content-area")
            action_buttons = pilot.app.screen.query_one("#action-buttons")
            
            # Verify content area fills most of the screen (minus header, title, buttons)
            content_bottom = content_area.region.bottom
            buttons_top = action_buttons.region.y
            
            # Content should extend close to where buttons start
            gap = buttons_top - content_bottom
            assert gap <= 2, (
                f"Too much gap between content and buttons in large terminal. "
                f"Gap: {gap}, Content bottom: {content_bottom}, Buttons top: {buttons_top}"
            )
            
            # Verify scrollable areas have reasonable height - should be much larger
            assert hunk_list.region.height > 10, (
                f"Hunk list too short in large terminal: {hunk_list.region.height}"
            )
            assert diff_viewer.region.height > 10, (
                f"Diff viewer too short in large terminal: {diff_viewer.region.height}"
            )

    @pytest.mark.asyncio
    async def test_horizontal_panels_split_properly(self, mock_commit_history_analyzer):
        """Test that horizontal panels split screen width appropriately."""
        mappings = MockDataGenerator.create_mock_mappings(3, 2)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        # Test with standard width
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            
            hunk_panel = pilot.app.screen.query_one("#hunk-list-panel")
            diff_panel = pilot.app.screen.query_one("#diff-panel")
            
            # Both panels should have reasonable width
            hunk_width = hunk_panel.region.width
            diff_width = diff_panel.region.width
            
            assert hunk_width > 10, f"Hunk panel too narrow: {hunk_width} in 80px terminal"
            assert diff_width > 10, f"Diff panel too narrow: {diff_width} in 80px terminal"
            
            # Together they should use most of the screen width
            total_panel_width = hunk_width + diff_width
            # Allow some margin for borders/padding
            assert total_panel_width >= 80 * 0.80, (
                f"Panels don't use enough width: {total_panel_width} of 80"
            )

    @pytest.mark.asyncio
    async def test_very_small_terminal_graceful_handling(self, mock_commit_history_analyzer):
        """Test graceful handling of very small terminals."""
        mappings = MockDataGenerator.create_mock_mappings(1, 1)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        # Test minimal terminal size
        async with app.run_test(size=(30, 10)) as pilot:
            await pilot.pause(0.1)
            
            # App should still work, even if cramped
            buttons = pilot.app.screen.query("Button")
            assert len(buttons) == 3, "Should still have all buttons in small terminal"
            
            # Buttons should still be at bottom
            for button in buttons:
                button_bottom = button.region.bottom
                screen_height = pilot.app.screen.size.height
                assert button_bottom <= screen_height, (
                    f"Button outside screen bounds: {button_bottom} > {screen_height}"
                )

    @pytest.mark.asyncio
    async def test_dynamic_resize_handling(self, mock_commit_history_analyzer):
        """Test behavior when terminal is resized (if supported by test framework)."""
        mappings = MockDataGenerator.create_mock_mappings(3, 2)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        # Start with medium size
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            
            # Get initial positions
            initial_buttons = pilot.app.screen.query("Button")
            initial_content = pilot.app.screen.query_one("#content-area")
            
            assert len(initial_buttons) == 3
            assert initial_content.region.height > 10
            
            # Note: Textual's test framework may not support dynamic resizing
            # This test validates the layout works at the initial size
            # In real usage, Textual handles resize events automatically
            
            # Verify layout is still correct after initial render
            for button in initial_buttons:
                assert button.region.bottom <= pilot.app.screen.size.height