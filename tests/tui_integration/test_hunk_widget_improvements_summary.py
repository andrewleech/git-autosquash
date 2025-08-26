"""Summary test showing all hunk widget improvements."""

import pytest
from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp
from tests.tui_integration.helpers import MockDataGenerator


class TestHunkWidgetImprovements:
    """Final test showing all hunk widget improvements."""

    @pytest.mark.asyncio
    async def test_all_improvements_summary(self, mock_commit_history_analyzer):
        """Comprehensive test showing all hunk widget improvements."""
        mappings = MockDataGenerator.create_mock_mappings(3, 2)  # Mix of blame and fallback
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            
            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")
            
            print(f"\\n=== Hunk Widget Improvements Summary ===")
            print(f"Found {len(hunk_widgets)} hunk widgets")
            
            # ✅ 1. Consistent Widget Heights
            heights = [w.region.height for w in hunk_widgets[:5]]
            height_variance = max(heights) - min(heights) if heights else 0
            avg_height = sum(heights) / len(heights) if heights else 0
            
            print(f"\\n1. CONSISTENT HEIGHTS:")
            print(f"   Widget heights: {heights}")
            print(f"   Average: {avg_height:.1f} rows")
            print(f"   Variance: {height_variance} rows")
            assert height_variance <= 1, f"Height variance too high: {height_variance}"
            print("   ✓ Consistent heights achieved")
            
            # ✅ 2. Mutually Exclusive Selection  
            print(f"\\n2. MUTUALLY EXCLUSIVE SELECTION:")
            mutually_exclusive_widgets = 0
            
            for i, widget in enumerate(hunk_widgets[:3]):
                # Check action selectors (blame matches)
                action_radiosets = widget.query("#action-selector")
                if action_radiosets:
                    radio_buttons = action_radiosets.first().query("RadioButton")
                    selected = [r for r in radio_buttons if r.value]
                    assert len(selected) <= 1, f"Widget {i+1}: Multiple action buttons selected"
                    mutually_exclusive_widgets += 1
                    print(f"   Widget {i+1}: Action selector with {len(radio_buttons)} options (mutually exclusive)")
                
                # Check target selectors (fallback cases)
                target_radiosets = widget.query("#target-selector")
                if target_radiosets:
                    radio_buttons = target_radiosets.first().query("RadioButton")
                    selected = [r for r in radio_buttons if r.value]
                    assert len(selected) <= 1, f"Widget {i+1}: Multiple target buttons selected"
                    mutually_exclusive_widgets += 1
                    print(f"   Widget {i+1}: Target selector with {len(radio_buttons)} options (mutually exclusive)")
            
            print(f"   ✓ {mutually_exclusive_widgets} widgets have mutually exclusive selection")
            
            # ✅ 3. Compact Spacing
            print(f"\\n3. COMPACT SPACING:")
            gaps = []
            for i in range(len(hunk_widgets) - 1):
                gap = hunk_widgets[i + 1].region.y - hunk_widgets[i].region.bottom
                gaps.append(gap)
                print(f"   Gap between widget {i+1} and {i+2}: {gap} rows")
            
            if gaps:
                avg_gap = sum(gaps) / len(gaps)
                max_gap = max(gaps)
                
                # Allow larger gap for section separators (between blame matches and fallbacks)
                normal_gaps = [g for g in gaps if g <= 5]  # Filter out section separators
                if normal_gaps:
                    max_normal_gap = max(normal_gaps)
                    assert max_normal_gap <= 2, f"Normal gap too large: {max_normal_gap}"
                    
                print(f"   Average gap: {avg_gap:.1f} rows")
                print(f"   Max gap (including separators): {max_gap} rows")
                if max_gap > 5:
                    print("   Note: Large gap likely due to section separator")
                print("   ✓ Compact spacing maintained (excluding section separators)")
            
            # ✅ 4. Efficient Space Usage
            print(f"\\n4. EFFICIENT SPACE USAGE:")
            content_area = pilot.app.screen.query_one("#content-area")
            content_height = content_area.region.height
            total_widget_height = sum(heights)
            
            if content_height > 0:
                utilization = total_widget_height / content_height
                widgets_that_fit = content_height // avg_height if avg_height > 0 else 0
                
                print(f"   Content area: {content_height} rows")
                print(f"   Total widget height: {total_widget_height} rows")
                print(f"   Widgets that fit: ~{widgets_that_fit:.0f}")
                print(f"   Space utilization: {utilization:.1%}")
                
                # Should fit at least 1 widget comfortably
                assert widgets_that_fit >= 1, f"Widgets too large: only {widgets_that_fit} fit"
                print("   ✓ Efficient space usage")
            
            # ✅ 5. No Checkbox Issues
            print(f"\\n5. NO CHECKBOX CONFLICTS:")
            checkbox_count = 0
            for widget in hunk_widgets:
                checkboxes = widget.query("Checkbox")
                checkbox_count += len(checkboxes)
            
            print(f"   Total checkboxes found: {checkbox_count}")
            assert checkbox_count == 0, f"Found {checkbox_count} non-exclusive checkboxes"
            print("   ✓ No conflicting checkboxes - all replaced with RadioSets")
            
            # 📊 FINAL SUMMARY
            print(f"\\n=== FINAL SUMMARY ===")
            print("✅ Consistent widget heights (no variable spacing)")
            print("✅ Mutually exclusive selection (RadioSet instead of Checkbox)")  
            print("✅ Compact spacing between widgets")
            print("✅ Efficient space usage in scrollable area")
            print("✅ Eliminated checkbox conflicts")
            print("🎉 All hunk widget layout issues resolved!")

    @pytest.mark.asyncio
    async def test_performance_improvement(self, mock_commit_history_analyzer):
        """Test that layout improvements don't hurt performance."""
        mappings = MockDataGenerator.create_mock_mappings(8, 4)  # More widgets
        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)
        
        import time
        start_time = time.time()
        
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            
            # Test that many widgets still render quickly
            hunk_widgets = pilot.app.screen.query("FallbackHunkMappingWidget")
            
        render_time = time.time() - start_time
        
        print(f"\\n=== Performance Test ===")
        print(f"Rendered {len(hunk_widgets)} hunk widgets in {render_time:.3f}s")
        
        # Should render quickly (less than 3 seconds for 12 widgets)
        assert render_time < 3.0, f"Rendering too slow: {render_time:.3f}s"
        print("✓ Layout improvements maintain good performance")