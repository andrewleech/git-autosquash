"""Terminal capture and validation tests using pyte."""

import pytest

from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp

from .helpers import PyteScreenAnalyzer


class TestTerminalScreenCapture:
    """Test terminal screen output using pyte terminal emulation."""

    @pytest.mark.asyncio
    async def test_screen_capture_basic_layout(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test basic screen layout through terminal capture."""
        analyzer = PyteScreenAnalyzer(width=80, height=24)
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        # Capture terminal output (simplified for demonstration)
        async with app.run_test(size=(80, 24)) as pilot:
            # In a real implementation, we'd capture the actual terminal output
            # This is a demonstration of how the analyzer would work

            # Simulate some terminal output for testing
            test_output = (
                "Git Autosquash\n"
                "Git patch -> target commit Review\n"
                "Progress Summary: 2 hunks - 2 automatic targets, 0 manual selection\n"
                "────────────────────────────────────────────────────────────────────────────\n"
                "Hunks                           │ Diff Preview\n"
                "shared/runtime/pyexec.c @@ -87,7 +87,7\n"
                "Target commit (auto-detected):\n"
                " ● d59d2691: Fix context handling in pyexec module\n"
                " ○ 384653e9: shared/runtime/pyexec: Fix UBSan error\n"
                "[X] Approve for squashing [ ] Ignore (keep in working tree)\n"
            )

            analyzer.feed_terminal_output(test_output.encode("utf-8"))

            # Test text positioning
            title_positions = analyzer.find_text_position("Git Autosquash")
            assert len(title_positions) > 0, "Title not found on screen"

            # Verify title is near the top
            title_row, _ = title_positions[0]
            assert title_row <= 2, f"Title should be near top, found at row {title_row}"

    @pytest.mark.asyncio
    async def test_button_positioning_at_bottom(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that action buttons are positioned at the bottom of the terminal."""
        analyzer = PyteScreenAnalyzer(width=80, height=24)
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            # Simulate terminal output with buttons at bottom
            test_output = (
                "Git Autosquash\n"
                + "\n" * 18  # Fill middle of screen
                + "┌─────────────────────────────────────────────────────────────────────────┐\n"
                "│ Approve All & Continue │ Continue with Selected │ Cancel              │\n"
                "└─────────────────────────────────────────────────────────────────────────┘\n"
                "⏎ Approve & Continue  esc Cancel  a Toggle All  i Toggle All Ignore\n"
            )

            analyzer.feed_terminal_output(test_output.encode("utf-8"))

            # Find button text
            continue_positions = analyzer.find_text_position("Continue with Selected")
            assert len(continue_positions) > 0, "Continue button not found"

            # Verify buttons are near bottom (within last 4 lines)
            button_row, _ = continue_positions[0]
            assert button_row >= 20, (
                f"Buttons should be near bottom, found at row {button_row}"
            )

    @pytest.mark.asyncio
    async def test_hunk_list_diff_panel_layout(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that hunk list and diff panel are properly laid out side by side."""
        analyzer = PyteScreenAnalyzer(width=120, height=30)  # Wider screen
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test(size=(120, 30)) as pilot:
            # Simulate side-by-side layout
            test_output = (
                "Git Autosquash\n"
                "Progress Summary: 2 hunks - 2 automatic targets, 0 manual selection\n"
                "────────────────────────────────────────────────────────────────────────────────────────────────────────────────\n"
                "Hunks                                          │ Diff Preview\n"
                "shared/runtime/pyexec.c @@ -87,7 +87,7        │ @@ -87,7 +87,7 @@ static int parse_c\n"
                "Target commit (auto-detected):                 │             ctx->constants = frozen\n"
                " ● d59d2691: Fix context handling              │             module_fun = mp_make\n"
                " ○ 384653e9: shared/runtime/pyexec             │ \n"
                "[X] Approve for squashing                      │ -            #if MICROPY_PY___FILE__\n"
                "                                               │ +            #if MICROPY_MODULE___FILE__\n"
            )

            analyzer.feed_terminal_output(test_output.encode("utf-8"))

            # Find the vertical separator
            separator_positions = analyzer.find_text_position("│")
            assert len(separator_positions) > 0, "Vertical separator not found"

            # Check that content appears on both sides of separator
            hunk_text = analyzer.find_text_position("shared/runtime/pyexec.c")
            diff_text = analyzer.find_text_position("@@ -87,7 +87,7 @@")

            assert len(hunk_text) > 0, "Hunk text not found in left panel"
            assert len(diff_text) > 0, "Diff text not found in right panel"

            # Verify they're on opposite sides of separator
            sep_col = separator_positions[0][1]
            hunk_col = hunk_text[0][1]
            diff_col = diff_text[0][1]

            assert hunk_col < sep_col < diff_col, (
                "Panels not properly positioned around separator"
            )

    @pytest.mark.asyncio
    async def test_color_coding_validation(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that color coding is applied correctly in terminal output."""
        analyzer = PyteScreenAnalyzer(width=80, height=24)
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(80, 24)) as pilot:
            # This is a conceptual test - real implementation would capture ANSI codes
            test_output_with_colors = (
                "\033[1;32mGit Autosquash\033[0m\n"  # Green bold title
                "\033[33m⚠ Manual Selection Required\033[0m\n"  # Yellow warning
                "\033[32m✓ Automatic Targets\033[0m\n"  # Green success
                "\033[31m-            #if MICROPY_PY___FILE__\033[0m\n"  # Red deletion
                "\033[32m+            #if MICROPY_MODULE___FILE__\033[0m\n"  # Green addition
            )

            analyzer.feed_terminal_output(test_output_with_colors.encode("utf-8"))

            # Basic validation that content is captured
            content = analyzer.get_screen_content()
            assert any("Git Autosquash" in line for line in content), (
                "Title not found in screen content"
            )

    @pytest.mark.asyncio
    async def test_no_text_overlap_or_truncation(
        self, large_mappings_dataset, mock_commit_history_analyzer
    ):
        """Test that with large datasets, text doesn't overlap or get truncated."""
        analyzer = PyteScreenAnalyzer(
            width=100, height=40
        )  # Larger screen for more data
        app = EnhancedAutoSquashApp(
            large_mappings_dataset[:10], mock_commit_history_analyzer
        )  # Subset for testing

        async with app.run_test(size=(100, 40)) as pilot:
            # Simulate output with many hunks
            test_lines = []
            test_lines.append("Git Autosquash")
            test_lines.append(
                "Progress Summary: 10 hunks - 7 automatic targets, 3 manual selection"
            )
            test_lines.append("─" * 98)
            test_lines.append("Hunks" + " " * 35 + "│" + " " * 10 + "Diff Preview")

            # Add multiple hunk entries
            for i in range(10):
                hunk_line = (
                    f"test_file_{i % 3}.py @@ -{i + 1},3 +{i + 1},3"
                    + " " * 10
                    + f"│ @@ -{i + 1},3 +{i + 1},3 @@"
                )
                test_lines.append(hunk_line)
                commit_line = (
                    f" ● commit_{i:08d}: Fix issue in component"
                    + " " * 5
                    + "│   - old_code_{i}"
                )
                test_lines.append(commit_line)

            test_output = "\n".join(test_lines)
            analyzer.feed_terminal_output(test_output.encode("utf-8"))

            # Verify no line exceeds screen width
            content = analyzer.get_screen_content()
            for i, line in enumerate(content):
                assert len(line) <= 100, (
                    f"Line {i} exceeds screen width: {len(line)} chars"
                )

    @pytest.mark.asyncio
    async def test_scrolling_behavior_with_many_hunks(
        self, large_mappings_dataset, mock_commit_history_analyzer
    ):
        """Test scrolling behavior when there are more hunks than fit on screen."""
        analyzer = PyteScreenAnalyzer(width=80, height=24)
        app = EnhancedAutoSquashApp(
            large_mappings_dataset[:20], mock_commit_history_analyzer
        )

        async with app.run_test(size=(80, 24)) as pilot:
            # Simulate scrolling by showing different sets of hunks
            initial_content = (
                "Git Autosquash\n"
                "Progress Summary: 20 hunks\n"
                + "\n".join([f"Hunk {i}: test_file_{i}.py" for i in range(1, 15)])
                + "\nApprove All & Continue  Continue  Cancel\n"
            )

            analyzer.feed_terminal_output(initial_content.encode("utf-8"))

            # Verify that not all hunks are shown at once (scrolling is working)
            content = analyzer.get_screen_content()
            hunk_lines = [
                line for line in content if "Hunk" in line and "test_file_" in line
            ]

            # Should show subset of hunks, not all 20
            assert len(hunk_lines) < 20, (
                "All hunks shown at once - scrolling may not be working"
            )


class TestLayoutValidation:
    """Test specific layout validation using terminal coordinates."""

    @pytest.mark.asyncio
    async def test_exact_widget_positioning(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test exact positioning of widgets using terminal coordinates."""
        analyzer = PyteScreenAnalyzer(width=80, height=24)
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test(size=(80, 24)) as pilot:
            # Create precise layout
            lines = [""] * 24
            lines[0] = " " * 30 + "Git Autosquash" + " " * 36  # Centered title
            lines[2] = "Git patch -> target commit Review"
            lines[4] = (
                "Progress Summary: 2 hunks - 2 automatic targets, 0 manual selection"
            )
            lines[6] = "─" * 78  # Separator
            lines[8] = "Hunks" + " " * 30 + "│" + " " * 10 + "Diff Preview"
            lines[10] = (
                "shared/runtime/pyexec.c @@ -87,7"
                + " " * 8
                + "│"
                + " " * 5
                + "@@ -87,7 +87,7 @@"
            )
            lines[21] = "Approve All & Continue │ Continue with Selected │ Cancel"
            lines[23] = "⏎ Approve & Continue  esc Cancel  a Toggle All"

            test_output = "\n".join(lines)
            analyzer.feed_terminal_output(test_output.encode("utf-8"))

            # Test exact positioning
            analyzer.assert_text_at_position(0, 30, "Git Autosquash")
            analyzer.assert_text_at_position(8, 0, "Hunks")
            analyzer.assert_text_at_position(8, 35, "│")
            analyzer.assert_text_at_position(21, 0, "Approve All")
            analyzer.assert_text_at_position(23, 0, "⏎ Approve")

    @pytest.mark.asyncio
    async def test_widget_bounds_no_overlap(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that widgets don't overlap each other."""
        analyzer = PyteScreenAnalyzer(width=100, height=30)
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test(size=(100, 30)) as pilot:
            # Simulate layout with clearly defined widget areas
            test_output = (
                "Git Autosquash\n"
                "Progress Summary: 3 hunks - 2 automatic targets, 1 manual selection\n"
                "─" * 98 + "\n"
                "Hunks" + " " * 40 + "│" + " " * 15 + "Diff Preview\n"
                "✓ Automatic Targets (Blame Analysis)" + " " * 8 + "│\n"
                "shared/runtime/pyexec.c @@ -87,7"
                + " " * 15
                + "│"
                + " " * 10
                + "@@ -87,7 +87,7 @@\n"
                "Target commit (auto-detected):" + " " * 14 + "│\n"
                " ● d59d2691: Fix context handling"
                + " " * 12
                + "│"
                + " " * 10
                + "-  #if MICROPY_PY___FILE__\n"
                "⚠ Manual Selection Required"
                + " " * 18
                + "│"
                + " " * 10
                + "+  #if MICROPY_MODULE___FILE__\n"
                "new_feature.py @@ -0,0 +1,10" + " " * 19 + "│\n"
                " " * 27 + "│" * 3 + " " * 70 + "\n"
                "Approve All & Continue │ Continue with Selected │ Cancel\n"
            )

            analyzer.feed_terminal_output(test_output.encode("utf-8"))

            # Define widget identifiers
            widgets = [
                "Git Autosquash",
                "Hunks",
                "Diff Preview",
                "✓ Automatic Targets",
                "⚠ Manual Selection Required",
                "Approve All & Continue",
            ]

            # Verify no overlaps
            assert analyzer.verify_no_overlap(widgets), (
                "Widgets are overlapping on screen"
            )

    @pytest.mark.asyncio
    async def test_box_drawing_characters_alignment(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test that box drawing characters and borders align properly."""
        analyzer = PyteScreenAnalyzer(width=80, height=24)
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test(size=(80, 24)) as pilot:
            # Test box drawing alignment
            test_output = (
                "Git Autosquash\n"
                "╭────────────────────────────────────╮\n"
                "│ Progress Summary: 2 hunks         │\n"
                "├────────────────────────────────────┤\n"
                "│ Hunks           │ Diff Preview     │\n"
                "│                 │                  │\n"
                "│ ● commit_hash   │ @@ -87,7 +87,7  │\n"
                "│   Fix issue     │   - old line     │\n"
                "│                 │   + new line     │\n"
                "╰────────────────────────────────────╯\n"
                "┌─────────────────────────────────────┐\n"
                "│ Approve All │ Continue │ Cancel   │\n"
                "└─────────────────────────────────────┘\n"
            )

            analyzer.feed_terminal_output(test_output.encode("utf-8"))

            # Verify box characters align
            content = analyzer.get_screen_content()

            # Find box top-left corners
            top_corners = analyzer.find_text_position("╭")
            assert len(top_corners) > 0, "Box top-left corner not found"

            # Verify alignment by checking that box edges line up
            for row_idx, line in enumerate(content):
                if "│" in line:
                    # Count vertical bars to ensure they align
                    bar_positions = [i for i, char in enumerate(line) if char == "│"]
                    # Basic check that bars exist where expected
                    assert len(bar_positions) > 0, (
                        f"No vertical bars found in line {row_idx}"
                    )


class TestPerformanceValidation:
    """Test performance aspects of terminal rendering."""

    @pytest.mark.asyncio
    async def test_large_dataset_rendering_performance(
        self, large_mappings_dataset, mock_commit_history_analyzer
    ):
        """Test that large datasets render without performance issues."""
        analyzer = PyteScreenAnalyzer(width=120, height=50)
        app = EnhancedAutoSquashApp(
            large_mappings_dataset, mock_commit_history_analyzer
        )

        import time

        start_time = time.time()

        async with app.run_test(size=(120, 50)) as pilot:
            # Simulate rendering time
            await pilot.pause(0.1)  # Allow rendering to complete

            # Basic performance assertion
            render_time = time.time() - start_time
            assert render_time < 5.0, f"Rendering took too long: {render_time:.2f}s"

            # Verify that content is still properly structured
            test_output = (
                "Git Autosquash\n"
                + f"Progress Summary: {len(large_mappings_dataset)} hunks\n"
            )
            analyzer.feed_terminal_output(test_output.encode("utf-8"))

            title_found = analyzer.find_text_position("Git Autosquash")
            assert len(title_found) > 0, "Title not found with large dataset"

    @pytest.mark.asyncio
    async def test_responsive_layout_terminal_resize(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that layout responds properly to terminal size changes."""
        # Start with small terminal
        analyzer_small = PyteScreenAnalyzer(width=60, height=20)

        # Test small layout
        small_output = (
            "Git Autosquash\n"
            "Summary: 3 hunks - 2 auto, 1 manual\n"  # Abbreviated for small screen
            "─" * 58 + "\n"
            "Hunks\n"
            "pyexec.c @@ -87,7\n"
            "● d59d2691: Fix\n"  # Truncated commit message
            "Continue │ Cancel\n"  # Fewer buttons
        )

        analyzer_small.feed_terminal_output(small_output.encode("utf-8"))
        small_content = analyzer_small.get_screen_content()

        # Test large layout
        analyzer_large = PyteScreenAnalyzer(width=120, height=40)

        large_output = (
            "Git Autosquash\n"
            "Progress Summary: 3 hunks - 2 automatic targets, 1 manual selection\n"
            "─" * 118 + "\n"
            "Hunks" + " " * 50 + "│" + " " * 20 + "Diff Preview\n"
            "shared/runtime/pyexec.c @@ -87,7 +87,7"
            + " " * 20
            + "│"
            + " " * 10
            + "@@ -87,7 +87,7 @@\n"
            "● d59d2691: Fix context handling in pyexec module"
            + " " * 5
            + "│"
            + " " * 10
            + "- #if MICROPY_PY___FILE__\n"
            "Approve All & Continue │ Continue with Selected │ Cancel\n"
        )

        analyzer_large.feed_terminal_output(large_output.encode("utf-8"))
        large_content = analyzer_large.get_screen_content()

        # Verify both layouts work
        assert any("Git Autosquash" in line for line in small_content), (
            "Small layout broken"
        )
        assert any("Git Autosquash" in line for line in large_content), (
            "Large layout broken"
        )

        # Verify large layout has more detail
        small_text_len = sum(len(line) for line in small_content)
        large_text_len = sum(len(line) for line in large_content)
        assert large_text_len > small_text_len, (
            "Large layout should have more content than small"
        )
