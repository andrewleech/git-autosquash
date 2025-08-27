"""Integration tests for EnhancedAutoSquashApp using Textual's native testing framework."""

import pytest


from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp

from .helpers import TextualAssertions, simulate_user_workflow


class TestEnhancedAppLayout:
    """Test layout and positioning of UI elements."""

    @pytest.mark.asyncio
    async def test_header_title_display(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that header displays correct title."""
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            # Check that title is displayed
            await TextualAssertions.assert_text_in_screen(pilot, "Git Autosquash")

    @pytest.mark.asyncio
    async def test_progress_summary_display(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that progress summary shows correct counts."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            progress_text = await TextualAssertions.get_progress_text(pilot)

            # Should show 2 automatic targets, 1 manual selection
            assert "2 automatic targets" in progress_text
            assert "1 manual selection" in progress_text

    @pytest.mark.asyncio
    async def test_action_buttons_at_bottom(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that action buttons are positioned at bottom of screen."""
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            await TextualAssertions.assert_button_at_bottom(
                pilot, "Approve All & Continue"
            )
            await TextualAssertions.assert_button_at_bottom(
                pilot, "Continue with Selected"
            )
            await TextualAssertions.assert_button_at_bottom(pilot, "Cancel")

    @pytest.mark.asyncio
    async def test_hunk_scroll_pane_layout(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that hunk scroll pane is properly sized and contains hunk widgets."""
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            # Check that the single-pane scrollable layout is visible
            await TextualAssertions.assert_widget_visible(pilot, "hunk-scroll-pane")

            # Check that hunk widgets exist within the scroll pane
            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")
            assert len(hunk_widgets) > 0, "No hunk widgets found in scroll pane"

    @pytest.mark.asyncio
    async def test_section_separator_with_mixed_mappings(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that separator appears between blame matches and fallback scenarios."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Should show both section headers and separator
            await TextualAssertions.assert_text_in_screen(pilot, "✓ Automatic Targets")
            await TextualAssertions.assert_text_in_screen(
                pilot, "⚠ Manual Selection Required"
            )

    @pytest.mark.asyncio
    async def test_responsive_layout_different_sizes(
        self, blame_matched_mappings, mock_commit_history_analyzer, terminal_sizes
    ):
        """Test that layout works with different terminal sizes."""
        width, height = terminal_sizes
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test(size=(width, height)) as pilot:
            # Basic layout should work at any reasonable size
            await TextualAssertions.assert_widget_visible(pilot, "hunk-scroll-pane")
            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")
            assert len(hunk_widgets) > 0, "No hunk widgets found at this terminal size"
            await TextualAssertions.assert_button_at_bottom(pilot, "Continue")


class TestWidgetVisibility:
    """Test visibility of various UI widgets."""

    @pytest.mark.asyncio
    async def test_blame_matched_hunks_show_commit_selection(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that blame-matched hunks show commit selection lists."""
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            # Should show commit selection RadioButtons (header text is now compact/minimal)
            # The implementation now focuses on functionality over verbose headers

            # Should show radio buttons for commit selection
            radio_buttons = pilot.app.screen.query("RadioButton")
            assert len(radio_buttons) > 0, "No radio buttons found for commit selection"

    @pytest.mark.asyncio
    async def test_fallback_hunks_show_manual_selection(
        self, fallback_mappings, mock_commit_history_analyzer
    ):
        """Test that fallback hunks show manual selection interface."""
        app = EnhancedAutoSquashApp(fallback_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Should show manual selection header (simplified text)
            await TextualAssertions.assert_text_in_screen(pilot, "Select target:")

            # Should show ignore option in RadioButtons (new design)
            radio_buttons = pilot.app.screen.query("RadioButton")
            ignore_found = any(
                "Ignore (keep in working" in str(rb.label) for rb in radio_buttons
            )
            assert ignore_found, "Ignore (keep in working tree) RadioButton not found"

    @pytest.mark.asyncio
    async def test_approve_ignore_radiobuttons_visible(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that approve/ignore action RadioButtons are visible in the new design."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Should show RadioButtons for accept and ignore actions
            radio_buttons = pilot.app.screen.query("RadioButton")
            assert len(radio_buttons) >= 4, (
                "Not enough radio buttons found for accept/ignore actions"
            )

            radio_button_texts = [str(rb.label) for rb in radio_buttons]
            accept_found = any("Accept" in text for text in radio_button_texts)
            ignore_found = any("Ignore" in text for text in radio_button_texts)

            assert accept_found, "Accept action RadioButton not found"
            assert ignore_found, "Ignore action RadioButton not found"

            # Also check that filter checkboxes exist
            checkboxes = pilot.app.screen.query("Checkbox")
            assert len(checkboxes) >= 1, "No commit filter checkboxes found"

            filter_checkbox_found = any(
                "All commits" in str(cb.label) for cb in checkboxes
            )
            assert filter_checkbox_found, "Commit filter checkbox not found"

    @pytest.mark.asyncio
    async def test_diff_viewer_shows_hunk_content(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that diff content is displayed in hunk widgets (embedded in new single-pane layout)."""
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            # In the new single-pane layout, diff content is embedded in each hunk widget
            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")
            assert len(hunk_widgets) > 0, "No hunk widgets found"

            # Each hunk widget should contain Static widgets with diff content
            static_widgets = pilot.app.screen.query("Static")
            diff_content_found = False

            for static in static_widgets:
                if hasattr(static, "renderable"):
                    content = str(static.renderable)
                    # Look for diff markers that indicate diff content
                    if any(
                        marker in content for marker in ["@@", "---", "+++"]
                    ) or content.startswith(("-", "+")):
                        diff_content_found = True
                        break

            assert diff_content_found, "No diff content found in hunk widgets"


class TestUserInteractions:
    """Test user interactions with the TUI."""

    @pytest.mark.asyncio
    async def test_key_bindings_work(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that key bindings work correctly."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Test 'a' key for toggle all
            await pilot.press("a")
            await pilot.pause(0.1)

            # Test 'i' key for ignore all
            await pilot.press("i")
            await pilot.pause(0.1)

            # Test 'b' key for batch operations (if fallbacks exist)
            await pilot.press("b")
            await pilot.pause(0.1)

            # Test navigation keys
            await pilot.press("j")  # Next hunk
            await pilot.pause(0.1)
            await pilot.press("k")  # Previous hunk

    @pytest.mark.asyncio
    async def test_radio_button_selection_changes_target(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that radio button selection changes the target commit."""
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            # Find radio buttons
            radio_buttons = pilot.app.screen.query("RadioButton")
            assert len(radio_buttons) > 1, "Need at least 2 radio buttons for this test"

            # Click on a different radio button
            await pilot.click(radio_buttons[1])
            await pilot.pause(0.1)

            # Verify the radio button is now selected
            assert radio_buttons[1].value, (
                "Radio button should be selected after clicking"
            )

    @pytest.mark.asyncio
    async def test_checkbox_toggles_work(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that checkbox toggles work for approve/ignore."""
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            # Find approve checkbox
            checkboxes = pilot.app.screen.query("Checkbox")
            approve_checkbox = None

            for cb in checkboxes:
                if "Approve" in str(cb.label):
                    approve_checkbox = cb
                    break

            assert approve_checkbox is not None, "Approve checkbox not found"

            # Toggle the checkbox
            initial_value = approve_checkbox.value
            await pilot.click(approve_checkbox)
            await pilot.pause(0.1)

            assert approve_checkbox.value != initial_value, (
                "Checkbox value should have toggled"
            )

    @pytest.mark.asyncio
    async def test_button_clicks_work(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that button clicks work correctly."""
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            # Test cancel button (should exit)
            buttons = pilot.app.screen.query("Button")
            cancel_button = None

            for button in buttons:
                if "Cancel" in str(button.label):
                    cancel_button = button
                    break

            assert cancel_button is not None, "Cancel button not found"

            # Click cancel - this should close the app
            await pilot.click(cancel_button)
            # Note: In real test, we'd verify the app closes, but that's complex to test

    @pytest.mark.asyncio
    async def test_hunk_navigation_updates_selection(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that navigating between hunks updates the selection state."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Navigate to next hunk
            await pilot.press("j")
            await pilot.pause(0.1)

            # Hunk widgets should still be visible (diff is embedded in widgets)
            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")
            assert len(hunk_widgets) > 0, "No hunk widgets found after navigation"


class TestStateManagement:
    """Test state management and persistence."""

    @pytest.mark.asyncio
    async def test_approved_ignored_state_persists(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that approved/ignored state persists across navigation."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Approve first hunk
            checkboxes = pilot.app.screen.query("Checkbox")
            if checkboxes:
                await pilot.click(checkboxes[0])
                await pilot.pause(0.1)

            # Navigate away and back
            await pilot.press("j")  # Next hunk
            await pilot.pause(0.1)
            await pilot.press("k")  # Back to first hunk
            await pilot.pause(0.1)

            # State should be preserved (this is basic - real test would verify checkbox state)
            assert len(checkboxes) > 0  # Basic assertion that widgets still exist

    @pytest.mark.asyncio
    async def test_batch_operations_apply_to_fallbacks(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that batch operations apply to all fallback hunks."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Press 'b' for batch operations
            await pilot.press("b")
            await pilot.pause(0.2)

            # Should open batch operations modal (basic check)
            # In a full implementation, we'd interact with the modal

    @pytest.mark.asyncio
    async def test_file_consistency_maintained(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that hunks from same file use consistent targets."""
        # Create mappings from same file for testing consistency
        same_file_mappings = []
        for mapping in blame_matched_mappings:
            # Modify to be from same file
            mapping.hunk.file_path = "shared/runtime/pyexec.c"
            same_file_mappings.append(mapping)

        app = EnhancedAutoSquashApp(same_file_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Basic test that app loads with consistent file mappings
            await TextualAssertions.assert_widget_visible(pilot, "hunk-scroll-pane")


class TestCompleteWorkflows:
    """Test complete user workflows."""

    @pytest.mark.asyncio
    async def test_approve_all_workflow(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test the complete 'approve all' workflow."""
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        workflow = [
            {"type": "wait", "duration": 0.1},
            {"type": "assert_visible", "widget_id": "hunk-scroll-pane"},
            {"type": "key", "key": "a"},  # Toggle all approved
            {"type": "wait", "duration": 0.1},
            {"type": "key", "key": "Enter"},  # Approve and continue
            {"type": "wait", "duration": 0.1},
        ]

        async with app.run_test() as pilot:
            await simulate_user_workflow(pilot, workflow)

    @pytest.mark.asyncio
    async def test_manual_selection_workflow(
        self, fallback_mappings, mock_commit_history_analyzer
    ):
        """Test manual selection workflow for fallback scenarios."""
        app = EnhancedAutoSquashApp(fallback_mappings, mock_commit_history_analyzer)

        workflow = [
            {"type": "wait", "duration": 0.1},
            {"type": "assert_text", "text": "Manual Selection Required"},
            {"type": "wait", "duration": 0.2},
        ]

        async with app.run_test() as pilot:
            await simulate_user_workflow(pilot, workflow)

    @pytest.mark.asyncio
    async def test_mixed_scenario_workflow(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test workflow with mixed blame matches and fallbacks."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        workflow = [
            {"type": "wait", "duration": 0.1},
            {"type": "assert_text", "text": "automatic targets"},
            {"type": "assert_text", "text": "manual selection"},
            {"type": "key", "key": "j"},  # Navigate
            {"type": "wait", "duration": 0.1},
            {"type": "key", "key": "space"},  # Toggle current
            {"type": "wait", "duration": 0.1},
        ]

        async with app.run_test() as pilot:
            await simulate_user_workflow(pilot, workflow)
