"""Diagnostic test to understand hunk widget layout."""

import pytest
from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp
from tests.tui_integration.helpers import MockDataGenerator


class TestHunkWidgetDiagnostic:
    """Diagnostic tests to understand hunk widget structure."""

    @pytest.mark.asyncio
    async def test_hunk_widget_internal_structure(self, mock_commit_history_analyzer):
        """Analyze what takes up space in hunk widgets."""
        mappings = MockDataGenerator.create_mock_mappings(1, 1)  # 1 blame, 1 fallback
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)

            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")

            print("\\n=== Hunk Widget Internal Structure Analysis ===")

            for i, widget in enumerate(hunk_widgets[:2]):
                print(f"\\n--- Hunk Widget {i + 1} ---")
                print(f"Total height: {widget.region.height} rows")
                print(f"Position: y={widget.region.y} to {widget.region.bottom - 1}")

                # Analyze internal components
                components = []

                # Headers
                headers = widget.query(".hunk-header, .fallback-header")
                for header in headers:
                    components.append(("Header", header.region.height, header.region.y))

                # Notes
                notes = widget.query(".fallback-note")
                for note in notes:
                    components.append(("Note", note.region.height, note.region.y))

                # Commit info
                commit_infos = widget.query(".commit-info")
                for ci in commit_infos:
                    components.append(("Commit Info", ci.region.height, ci.region.y))

                # Radio sets
                radio_sets = widget.query("RadioSet")
                for rs in radio_sets:
                    components.append(
                        (f"RadioSet ({rs.id})", rs.region.height, rs.region.y)
                    )

                # Radio buttons
                radio_buttons = widget.query("RadioButton")
                for rb in radio_buttons:
                    components.append(
                        (f"RadioButton ({rb.id})", rb.region.height, rb.region.y)
                    )

                # Action buttons container
                action_containers = widget.query(".action-buttons")
                for ac in action_containers:
                    components.append(
                        ("Action Container", ac.region.height, ac.region.y)
                    )

                # Sort by Y position
                components.sort(key=lambda x: x[2])

                print("Internal components (sorted by position):")
                total_component_height = 0
                for name, height, y in components:
                    print(f"  {name:20}: {height}h at y={y}")
                    total_component_height += height

                print(f"Total component height: {total_component_height}")
                print(
                    f"Widget border/padding overhead: {widget.region.height - total_component_height}"
                )

                # Check for excessive radio buttons
                radio_count = len(widget.query("RadioButton"))
                print(f"Number of radio buttons: {radio_count}")

                if radio_count > 7:  # Header + 5 commits + approve/ignore = 7 max
                    print(f"⚠️  Too many radio buttons: {radio_count}")

    @pytest.mark.asyncio
    async def test_compare_blame_vs_fallback_widgets(
        self, mock_commit_history_analyzer
    ):
        """Compare layout between blame-matched and fallback widgets."""
        # Create 1 blame match and 1 fallback
        mappings = MockDataGenerator.create_mock_mappings(1, 1)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)

            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")

            print("\\n=== Blame vs Fallback Widget Comparison ===")

            for i, widget in enumerate(hunk_widgets[:2]):
                is_fallback = "fallback" in widget.get_class_list()
                widget_type = "Fallback" if is_fallback else "Blame Match"

                print(f"\\n{widget_type} Widget:")
                print(f"  Height: {widget.region.height} rows")
                print(f"  Radio buttons: {len(widget.query('RadioButton'))}")
                print(f"  RadioSets: {len(widget.query('RadioSet'))}")
                print(f"  Static elements: {len(widget.query('Static'))}")

                # Check what type of header
                if widget.query(".fallback-header"):
                    print("  Has fallback header")
                if widget.query(".hunk-header"):
                    print("  Has blame header")
                if widget.query(".fallback-note"):
                    print("  Has fallback note")

    @pytest.mark.asyncio
    async def test_widget_height_before_after_changes(
        self, mock_commit_history_analyzer
    ):
        """Test to measure impact of layout changes."""
        mappings = MockDataGenerator.create_mock_mappings(2, 1)
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)

            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")

            print("\\n=== Widget Height Assessment ===")

            heights = [w.region.height for w in hunk_widgets[:3]]
            avg_height = sum(heights) / len(heights) if heights else 0

            print(f"Widget heights: {heights}")
            print(f"Average height: {avg_height:.1f} rows")
            print(f"Max height: {max(heights) if heights else 0}")
            print(f"Min height: {min(heights) if heights else 0}")

            # Calculate efficiency
            content_area_height = pilot.app.screen.query_one(
                "#content-area"
            ).region.height
            num_widgets = len(hunk_widgets)

            if num_widgets > 0 and content_area_height > 0:
                total_widget_height = sum(heights)
                utilization = total_widget_height / content_area_height
                widgets_that_fit = (
                    content_area_height // avg_height if avg_height > 0 else 0
                )

                print(f"Content area height: {content_area_height} rows")
                print(f"Space utilization: {utilization:.1%}")
                print(f"Widgets that fit: ~{widgets_that_fit:.0f}")

                # Recommendations
                if avg_height > 8:
                    print("⚠️  Widgets might be too tall for efficient scrolling")
                elif avg_height < 4:
                    print("✓ Widgets are compact")
                else:
                    print("✓ Widget height is reasonable")
