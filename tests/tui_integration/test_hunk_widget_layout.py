"""Test hunk widget layout improvements."""

import pytest
from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp
from tests.tui_integration.helpers import MockDataGenerator


class TestHunkWidgetLayout:
    """Test hunk widget spacing and layout improvements."""

    @pytest.mark.asyncio
    async def test_hunk_widget_compact_layout(self, mock_commit_history_analyzer):
        """Test that hunk widgets have compact, consistent layout."""
        mappings = MockDataGenerator.create_mock_mappings(
            3, 2
        )  # Mix of blame and fallback
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)

            # Get hunk widgets
            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")
            assert len(hunk_widgets) >= 3, (
                f"Expected at least 3 hunk widgets, found {len(hunk_widgets)}"
            )

            print("\\n=== Hunk Widget Layout Analysis ===")

            for i, widget in enumerate(hunk_widgets[:3]):  # Check first 3
                widget_height = widget.region.height
                print(
                    f"Hunk {i + 1}: height={widget_height}, y={widget.region.y}-{widget.region.bottom - 1}"
                )

                # Verify reasonable height (enhanced with functional commit selection)
                assert widget_height <= 12, (
                    f"Hunk widget {i + 1} too tall: {widget_height} rows"
                )

                # Verify minimum height for content
                assert widget_height >= 4, (
                    f"Hunk widget {i + 1} too short: {widget_height} rows"
                )

            # Check for consistent heights (similar widgets should be similar size)
            heights = [w.region.height for w in hunk_widgets[:3]]
            height_variance = max(heights) - min(heights)

            # Allow some variance but not excessive
            assert height_variance <= 3, (
                f"Too much height variance between hunk widgets: {heights}"
            )

            print(f"Widget heights: {heights} (variance: {height_variance})")
            print("✓ Hunk widgets have compact, consistent layout")

    @pytest.mark.asyncio
    async def test_action_buttons_are_mutually_exclusive(
        self, mock_commit_history_analyzer
    ):
        """Test that approve/ignore selection is mutually exclusive."""
        mappings = MockDataGenerator.create_mock_mappings(2, 1)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)

            # Get hunk widgets
            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")

            found_mutual_exclusivity = False

            for hunk_widget in hunk_widgets:
                # Check for action selector (blame matches)
                action_radiosets = hunk_widget.query("#action-selector")
                if action_radiosets:
                    action_radioset = action_radiosets.first()
                    radio_buttons = action_radioset.query("RadioButton")
                    assert len(radio_buttons) == 2, (
                        f"Expected 2 action radio buttons, found {len(radio_buttons)}"
                    )

                    # Test mutual exclusivity - only one can be selected at a time in RadioSet
                    initially_selected = [r for r in radio_buttons if r.value]
                    assert len(initially_selected) <= 1, (
                        f"Multiple action radio buttons selected: {[r.id for r in initially_selected]}"
                    )
                    found_mutual_exclusivity = True
                    print("✓ Found mutually exclusive action buttons (approve/ignore)")

                # Check for target selector (fallback cases)
                target_radiosets = hunk_widget.query("#target-selector")
                if target_radiosets:
                    target_radioset = target_radiosets.first()
                    radio_buttons = target_radioset.query("RadioButton")

                    # Target selector includes ignore + commits, also mutually exclusive
                    initially_selected = [r for r in radio_buttons if r.value]
                    assert len(initially_selected) <= 1, (
                        f"Multiple target radio buttons selected: {[r.id for r in initially_selected]}"
                    )
                    found_mutual_exclusivity = True
                    print(
                        f"✓ Found mutually exclusive target selection ({len(radio_buttons)} options)"
                    )

            assert found_mutual_exclusivity, "No mutually exclusive buttons found"
            print("✓ All selection widgets are mutually exclusive")

    @pytest.mark.asyncio
    async def test_hunk_widget_spacing_consistency(self, mock_commit_history_analyzer):
        """Test consistent spacing within and between hunk widgets."""
        mappings = MockDataGenerator.create_mock_mappings(4, 2)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)

            # Get hunk widgets
            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")
            assert len(hunk_widgets) >= 3, "Need multiple hunk widgets for spacing test"

            print("\\n=== Hunk Widget Spacing Analysis ===")

            # Check spacing between widgets
            gaps = []
            for i in range(len(hunk_widgets) - 1):
                current_bottom = hunk_widgets[i].region.bottom
                next_top = hunk_widgets[i + 1].region.y
                gap = next_top - current_bottom
                gaps.append(gap)
                print(f"Gap between hunk {i + 1} and {i + 2}: {gap} rows")

            # Verify consistent gaps
            if gaps:
                gap_variance = max(gaps) - min(gaps)
                assert gap_variance <= 1, (
                    f"Inconsistent spacing between hunk widgets: {gaps}"
                )

                # Verify reasonable gap size
                avg_gap = sum(gaps) / len(gaps)
                assert 0 <= avg_gap <= 2, f"Gaps too large: average {avg_gap:.1f} rows"

                print(f"✓ Consistent spacing: {gaps} (variance: {gap_variance})")

            # Check internal widget spacing
            first_widget = hunk_widgets[0]

            # Find internal components
            header = first_widget.query(".hunk-header, .fallback-header").first()
            action_buttons = first_widget.query("#action-selector").first()

            if header and action_buttons:
                internal_gap = action_buttons.region.y - header.region.bottom
                print(f"Internal spacing (header to actions): {internal_gap} rows")

                # Should have reasonable internal spacing
                assert internal_gap >= 1, f"Internal spacing too tight: {internal_gap}"
                assert internal_gap <= 4, f"Internal spacing too loose: {internal_gap}"

                print("✓ Good internal spacing within hunk widgets")

    @pytest.mark.asyncio
    async def test_hunk_widget_no_wasted_space(self, mock_commit_history_analyzer):
        """Test that hunk widgets don't have excessive empty space."""
        mappings = MockDataGenerator.create_mock_mappings(2, 1)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test(
            size=(80, 20)
        ) as pilot:  # Smaller terminal to test efficiency
            await pilot.pause(0.1)

            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")

            for i, widget in enumerate(hunk_widgets[:2]):
                widget_height = widget.region.height

                # Count actual content elements
                header = widget.query(".hunk-header, .fallback-header")
                commit_info = widget.query(".commit-info")
                action_buttons = widget.query("#action-selector")
                radio_buttons = widget.query("RadioButton")

                content_elements = (
                    len(header)
                    + len(commit_info)
                    + len(action_buttons)
                    + len(radio_buttons)
                )

                # Rough efficiency check: height shouldn't be more than 2x content elements
                efficiency_ratio = widget_height / max(content_elements, 1)

                print(
                    f"Hunk {i + 1}: {widget_height} rows, {content_elements} elements, ratio: {efficiency_ratio:.1f}"
                )

                assert efficiency_ratio <= 3.0, (
                    f"Hunk widget {i + 1} inefficient: {efficiency_ratio:.1f} rows per element"
                )

            print("✓ Hunk widgets efficiently use vertical space")
