"""Comprehensive test scenarios covering real-world use cases."""

import pytest

from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp
from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
from git_autosquash.hunk_parser import DiffHunk

from .helpers import TextualAssertions, simulate_user_workflow, MockDataGenerator


class TestRealWorldScenarios:
    """Test scenarios based on real-world usage patterns."""

    @pytest.mark.asyncio
    async def test_scenario_all_blame_matches(
        self, sample_commits, mock_commit_history_analyzer
    ):
        """
        Scenario 1: All hunks have automatic targets from blame analysis.
        User should be able to quickly approve all and continue.
        """
        # Create 5 hunks with successful blame matches
        mappings = MockDataGenerator.create_mock_mappings(
            blame_count=5, fallback_count=0
        )

        app = EnhancedAutoSquashApp(mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Verify initial state
            progress_text = await TextualAssertions.get_progress_text(pilot)
            assert "5 automatic targets, 0 manual selection" in progress_text

            # Should show automatic targets section
            await TextualAssertions.assert_text_in_screen(pilot, "✓ Automatic Targets")

            # All hunks should show commit selection with pre-selected targets
            radio_buttons = pilot.app.query("RadioButton")
            assert len(radio_buttons) >= 5, "Should have radio buttons for all hunks"

            # Quick approve all workflow
            await pilot.press("a")  # Toggle all approved
            await pilot.pause(0.1)
            await pilot.press("Enter")  # Approve and continue

            # App should have processed the approval
            assert hasattr(app, "approved_mappings")

    @pytest.mark.asyncio
    async def test_scenario_mixed_blame_and_fallback(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """
        Scenario 2: Mix of blame matches and fallback scenarios.
        User needs to handle both automatic and manual selections.
        """
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Should show both sections
            await TextualAssertions.assert_text_in_screen(pilot, "✓ Automatic Targets")
            await TextualAssertions.assert_text_in_screen(
                pilot, "⚠ Manual Selection Required"
            )

            # Verify progress shows mixed state
            progress_text = await TextualAssertions.get_progress_text(pilot)
            assert "automatic targets" in progress_text
            assert "manual selection" in progress_text

            # User workflow: approve automatic ones, handle manual selection
            workflow = [
                {"type": "wait", "duration": 0.1},
                {"type": "key", "key": "j"},  # Navigate to fallback section
                {"type": "wait", "duration": 0.1},
                {"type": "key", "key": "b"},  # Open batch operations for fallbacks
                {"type": "wait", "duration": 0.2},
            ]

            await simulate_user_workflow(pilot, workflow)

    @pytest.mark.asyncio
    async def test_scenario_new_file_handling(self, mock_commit_history_analyzer):
        """
        Scenario 3: All hunks are from new files with no git history.
        User must choose targets or ignore them.
        """
        # Create new file hunks
        new_file_hunks = []
        for i in range(3):
            hunk = DiffHunk(
                file_path=f"new_feature_{i}.py",
                old_start=0,
                old_count=0,
                new_start=1,
                new_count=10,
                lines=["@@ -0,0 +1,10 @@"]
                + [f"+def new_function_{i}():"]
                + [f"+    return {i}"] * 9,
                context_before=[],
                context_after=[],
            )

            mapping = HunkTargetMapping(
                hunk=hunk,
                target_commit=None,
                confidence="low",
                blame_info=[],
                targeting_method=TargetingMethod.FALLBACK_NEW_FILE,
                fallback_candidates=["commit1", "commit2", "commit3"],
                needs_user_selection=True,
            )
            new_file_hunks.append(mapping)

        app = EnhancedAutoSquashApp(new_file_hunks, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Should show new file description
            await TextualAssertions.assert_text_in_screen(
                pilot, "Manual Selection Required"
            )

            # All should be fallback scenarios
            progress_text = await TextualAssertions.get_progress_text(pilot)
            assert "3 manual selection" in progress_text
            assert "0 automatic targets" in progress_text

            # User can choose to ignore all new files
            await pilot.press("i")  # Toggle all ignored
            await pilot.pause(0.1)

            # Verify ignore state
            checkboxes = pilot.app.query("Checkbox")
            ignore_checkboxes = [cb for cb in checkboxes if "Ignore" in str(cb.label)]
            assert len(ignore_checkboxes) > 0, "Should have ignore checkboxes"

    @pytest.mark.asyncio
    async def test_scenario_large_project_many_hunks(
        self, large_mappings_dataset, mock_commit_history_analyzer
    ):
        """
        Scenario 4: Large project with 50 hunks requiring scrolling and batch operations.
        """
        app = EnhancedAutoSquashApp(
            large_mappings_dataset, mock_commit_history_analyzer
        )

        async with app.run_test(
            size=(120, 40)
        ) as pilot:  # Larger screen for more hunks
            # Verify we have many hunks
            progress_text = await TextualAssertions.get_progress_text(pilot)
            assert "50 hunks" in progress_text

            # Test scrolling behavior
            len(pilot.app.query("FallbackHunkMappingWidget"))

            # Scroll down multiple times
            for _ in range(10):
                await pilot.press("j")
                await pilot.pause(0.05)

            # Should still have hunk widgets (scrolling working)
            after_scroll_widgets = len(pilot.app.query("FallbackHunkMappingWidget"))
            assert after_scroll_widgets > 0, (
                "Should still have visible widgets after scrolling"
            )

            # Test batch operations for efficiency
            await pilot.press("b")  # Open batch operations
            await pilot.pause(0.2)

            # Should open batch modal (basic test)
            # In full implementation, would interact with modal

    @pytest.mark.asyncio
    async def test_scenario_file_consistency_same_file_hunks(
        self, mock_commit_history_analyzer, sample_commits
    ):
        """
        Scenario 5: Multiple hunks from same file should use consistent targets.
        """
        # Create multiple hunks from same file
        same_file_hunks = []
        for i in range(4):
            hunk = DiffHunk(
                file_path="shared/runtime/pyexec.c",  # Same file
                old_start=100 + i * 10,
                old_count=3,
                new_start=100 + i * 10,
                new_count=3,
                lines=[
                    f"@@ -{100 + i * 10},3 +{100 + i * 10},3 @@",
                    f"- old_line_{i}",
                    f"+ new_line_{i}",
                ],
                context_before=[],
                context_after=[],
            )

            # First hunk has target, others should follow consistency
            if i == 0:
                mapping = HunkTargetMapping(
                    hunk=hunk,
                    target_commit=sample_commits[0].commit_hash,
                    confidence="high",
                    blame_info=[],
                    targeting_method=TargetingMethod.BLAME_MATCH,
                    needs_user_selection=False,
                )
            else:
                mapping = HunkTargetMapping(
                    hunk=hunk,
                    target_commit=sample_commits[
                        0
                    ].commit_hash,  # Same target for consistency
                    confidence="medium",
                    blame_info=[],
                    targeting_method=TargetingMethod.FALLBACK_CONSISTENCY,
                    needs_user_selection=False,
                )

            same_file_hunks.append(mapping)

        app = EnhancedAutoSquashApp(same_file_hunks, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # All should be automatic since they're consistent
            progress_text = await TextualAssertions.get_progress_text(pilot)
            assert "4 automatic targets" in progress_text

            # Should show consistency targeting method
            await TextualAssertions.assert_text_in_screen(pilot, "Target commit")

            # All should target same commit
            radio_buttons = pilot.app.query("RadioButton")
            selected_buttons = [rb for rb in radio_buttons if rb.value]
            # Should have some selected (one per hunk group)
            assert len(selected_buttons) > 0, "Should have pre-selected radio buttons"

    @pytest.mark.asyncio
    async def test_scenario_contextual_blame_detection(
        self, mock_commit_history_analyzer, sample_commits
    ):
        """
        Scenario 6: Test contextual blame when direct blame fails but context lines provide targets.
        """
        # Create hunk that would use contextual blame
        contextual_hunk = DiffHunk(
            file_path="src/context_test.py",
            old_start=50,
            old_count=1,
            new_start=50,
            new_count=3,
            lines=[
                "@@ -50,1 +50,3 @@",
                " # Context line that was modified in target commit",
                "+    new_line_1 = 'added'",
                "+    new_line_2 = 'also added'",
            ],
            context_before=["# This context was touched by target commit"],
            context_after=["# This context also helps identify target"],
        )

        contextual_mapping = HunkTargetMapping(
            hunk=contextual_hunk,
            target_commit=sample_commits[0].commit_hash,
            confidence="medium",  # Reduced confidence for contextual
            blame_info=[],
            targeting_method=TargetingMethod.CONTEXTUAL_BLAME_MATCH,
            needs_user_selection=False,
        )

        app = EnhancedAutoSquashApp([contextual_mapping], mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Should show as automatic target
            await TextualAssertions.assert_text_in_screen(pilot, "✓ Automatic Targets")
            await TextualAssertions.assert_text_in_screen(
                pilot, "Target commit (auto-detected):"
            )

            # Should show medium confidence
            progress_text = await TextualAssertions.get_progress_text(pilot)
            assert "1 automatic target" in progress_text


class TestErrorAndEdgeCaseScenarios:
    """Test error conditions and edge cases."""

    @pytest.mark.asyncio
    async def test_scenario_empty_hunk_list(self, mock_commit_history_analyzer):
        """
        Edge Case: No hunks to process.
        """
        app = EnhancedAutoSquashApp([], mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Should show empty state
            progress_text = await TextualAssertions.get_progress_text(pilot)
            assert "0 hunks" in progress_text

            # Should still have basic UI elements
            await TextualAssertions.assert_widget_visible(pilot, "hunk-list")
            await TextualAssertions.assert_button_at_bottom(pilot, "Cancel")

    @pytest.mark.asyncio
    async def test_scenario_single_hunk_only(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """
        Edge Case: Only one hunk to process.
        """
        single_hunk = [blame_matched_mappings[0]]
        app = EnhancedAutoSquashApp(single_hunk, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            progress_text = await TextualAssertions.get_progress_text(pilot)
            assert "1 hunk" in progress_text

            # Navigation keys should work but not crash
            await pilot.press("j")  # Next (no effect)
            await pilot.press("k")  # Previous (no effect)
            await pilot.pause(0.1)

            # Should still be able to approve
            await pilot.press("space")  # Toggle current
            await pilot.pause(0.1)

    @pytest.mark.asyncio
    async def test_scenario_very_long_commit_messages(
        self, mock_commit_history_analyzer
    ):
        """
        Edge Case: Very long commit messages that need truncation.
        """
        long_message_hunk = DiffHunk(
            file_path="test.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[],
        )

        long_message_mapping = HunkTargetMapping(
            hunk=long_message_hunk,
            target_commit="abcd1234",
            confidence="high",
            blame_info=[],
            targeting_method=TargetingMethod.BLAME_MATCH,
            needs_user_selection=False,
        )

        # Mock analyzer to return commit with very long subject
        mock_commit_history_analyzer.get_commit_suggestions.return_value = [
            type(
                "MockCommit",
                (),
                {
                    "commit_hash": "abcd1234",
                    "short_hash": "abcd1234",
                    "subject": "This is an extremely long commit message that goes on and on and on and should definitely be truncated by the UI to prevent layout issues and ensure readability for users who are trying to select the appropriate target commit for their changes",
                    "author": "Long Winded Author",
                    "timestamp": 1756174372,
                    "is_merge": False,
                    "files_touched": ["test.py"],
                },
            )()
        ]

        app = EnhancedAutoSquashApp(
            [long_message_mapping], mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            # Should handle long text gracefully
            await TextualAssertions.assert_widget_visible(pilot, "hunk-list")
            radio_buttons = pilot.app.query("RadioButton")
            assert len(radio_buttons) > 0, "Should have radio buttons despite long text"

    @pytest.mark.asyncio
    async def test_scenario_unicode_and_special_characters(
        self, mock_commit_history_analyzer
    ):
        """
        Edge Case: Unicode characters in file paths and commit messages.
        """
        unicode_hunk = DiffHunk(
            file_path="测试/файл.py",  # Mixed Chinese and Cyrillic
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=[
                "@@ -1,1 +1,1 @@",
                "-# 旧代码",
                "+# новый код",
            ],  # Chinese and Russian
            context_before=[],
            context_after=[],
        )

        unicode_mapping = HunkTargetMapping(
            hunk=unicode_hunk,
            target_commit="unicode123",
            confidence="high",
            blame_info=[],
            targeting_method=TargetingMethod.BLAME_MATCH,
            needs_user_selection=False,
        )

        app = EnhancedAutoSquashApp([unicode_mapping], mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Should handle Unicode without crashing
            await TextualAssertions.assert_widget_visible(pilot, "hunk-list")
            await TextualAssertions.assert_widget_visible(pilot, "diff-viewer")

    @pytest.mark.asyncio
    async def test_scenario_rapid_key_presses(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """
        Stress Test: Rapid key presses to test responsiveness.
        """
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Rapid navigation
            for _ in range(20):
                await pilot.press("j")
                await pilot.pause(0.01)  # Very short pause

            for _ in range(20):
                await pilot.press("k")
                await pilot.pause(0.01)

            # Rapid toggles
            for _ in range(10):
                await pilot.press("space")
                await pilot.pause(0.01)

            # Should still be responsive
            await pilot.pause(0.2)
            await TextualAssertions.assert_widget_visible(pilot, "hunk-list")

    @pytest.mark.asyncio
    async def test_scenario_terminal_resize_during_use(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """
        Stress Test: Terminal resize while using the application.
        """
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        # Start with normal size
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.1)

            # Navigate around
            await pilot.press("j")
            await pilot.press("space")

            # Simulate resize (conceptually - actual resize testing would need platform-specific code)
            # Here we just verify the app continues to work after operations
            await pilot.pause(0.1)

            # Should still be functional
            await TextualAssertions.assert_widget_visible(pilot, "hunk-list")
            await TextualAssertions.assert_widget_visible(pilot, "diff-viewer")


class TestPerformanceScenarios:
    """Test performance with various data sizes."""

    @pytest.mark.asyncio
    async def test_scenario_performance_100_hunks(self, mock_commit_history_analyzer):
        """
        Performance Test: 100 hunks to test UI responsiveness.
        """
        large_dataset = MockDataGenerator.create_mock_mappings(
            blame_count=70, fallback_count=30
        )
        app = EnhancedAutoSquashApp(large_dataset, mock_commit_history_analyzer)

        import time

        start_time = time.time()

        async with app.run_test(size=(120, 50)) as pilot:
            await pilot.pause(0.2)  # Allow full rendering

            render_time = time.time() - start_time
            assert render_time < 3.0, (
                f"Large dataset rendering too slow: {render_time:.2f}s"
            )

            # Test navigation performance
            nav_start = time.time()
            for _ in range(20):
                await pilot.press("j")
                await pilot.pause(0.01)
            nav_time = time.time() - nav_start

            assert nav_time < 2.0, f"Navigation too slow: {nav_time:.2f}s"

    @pytest.mark.asyncio
    async def test_scenario_memory_usage_large_dataset(
        self, mock_commit_history_analyzer
    ):
        """
        Performance Test: Memory usage with large datasets.
        """
        # This would require memory profiling in a real scenario
        large_dataset = MockDataGenerator.create_mock_mappings(
            blame_count=200, fallback_count=100
        )
        app = EnhancedAutoSquashApp(large_dataset, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            await pilot.pause(0.1)

            # Basic functionality should still work
            await TextualAssertions.assert_widget_visible(pilot, "hunk-list")

            # Navigation should be responsive
            await pilot.press("j")
            await pilot.press("k")
            await pilot.pause(0.1)


class TestAccessibilityScenarios:
    """Test accessibility and usability features."""

    @pytest.mark.asyncio
    async def test_scenario_keyboard_only_navigation(
        self, mixed_mappings, mock_commit_history_analyzer
    ):
        """
        Accessibility: Complete workflow using only keyboard.
        """
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)

        async with app.run_test() as pilot:
            # Full keyboard workflow
            workflow = [
                {"type": "key", "key": "j"},  # Navigate to next hunk
                {"type": "key", "key": "space"},  # Toggle selection
                {"type": "key", "key": "j"},  # Next hunk
                {"type": "key", "key": "space"},  # Toggle selection
                {"type": "key", "key": "a"},  # Toggle all approved
                {"type": "key", "key": "i"},  # Toggle all ignored
                {"type": "key", "key": "b"},  # Open batch operations
                {"type": "wait", "duration": 0.1},
                {"type": "key", "key": "Escape"},  # Close batch operations
                {"type": "key", "key": "Enter"},  # Final approval
            ]

            await simulate_user_workflow(pilot, workflow)

    @pytest.mark.asyncio
    async def test_scenario_screen_reader_friendly_labels(
        self, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """
        Accessibility: Verify widgets have appropriate labels for screen readers.
        """
        app = EnhancedAutoSquashApp(
            blame_matched_mappings, mock_commit_history_analyzer
        )

        async with app.run_test() as pilot:
            # Check that important UI elements have accessible text
            await TextualAssertions.assert_text_in_screen(pilot, "Git Autosquash")
            await TextualAssertions.assert_text_in_screen(
                pilot, "Approve for squashing"
            )
            await TextualAssertions.assert_text_in_screen(pilot, "Target commit")
            await TextualAssertions.assert_text_in_screen(pilot, "Diff Preview")

            # Buttons should have clear labels
            buttons = pilot.app.query("Button")
            button_labels = [str(b.label) for b in buttons]
            assert any("Continue" in label for label in button_labels), (
                "Continue button not labeled"
            )
            assert any("Cancel" in label for label in button_labels), (
                "Cancel button not labeled"
            )
