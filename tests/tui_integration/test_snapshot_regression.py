"""Visual regression tests using pytest-textual-snapshot."""

import pytest
from typing import List

from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp
from git_autosquash.hunk_target_resolver import HunkTargetMapping


@pytest.mark.asyncio
class TestSnapshotRegression:
    """Visual regression tests to catch UI changes."""

    async def test_blame_matches_only_layout(
        self, snap_compare, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test layout with only blame-matched hunks."""
        app = EnhancedAutoSquashApp(blame_matched_mappings, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)  # Allow rendering to complete
        )

    async def test_fallback_only_layout(
        self, snap_compare, fallback_mappings, mock_commit_history_analyzer
    ):
        """Test layout with only fallback hunks requiring manual selection."""
        app = EnhancedAutoSquashApp(fallback_mappings, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_mixed_hunks_layout(
        self, snap_compare, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test layout with mixed blame matches and fallback hunks."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(120, 35),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_small_terminal_layout(
        self, snap_compare, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test responsive layout on small terminal."""
        app = EnhancedAutoSquashApp(blame_matched_mappings, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(60, 20),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_large_terminal_layout(
        self, snap_compare, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test layout on large terminal with more space."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(150, 45),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_wide_terminal_layout(
        self, snap_compare, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test layout on very wide terminal."""
        app = EnhancedAutoSquashApp(blame_matched_mappings, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(200, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_scrolled_state_many_hunks(
        self, snap_compare, large_mappings_dataset, mock_commit_history_analyzer
    ):
        """Test scrolled state with many hunks."""
        # Use subset to ensure we have scrolling
        hunks_subset = large_mappings_dataset[:15]
        app = EnhancedAutoSquashApp(hunks_subset, mock_commit_history_analyzer)
        
        async def scroll_down(pilot):
            await pilot.pause(0.2)
            # Simulate scrolling down
            await pilot.press("j", "j", "j", "j", "j")  # Multiple down presses
            await pilot.pause(0.1)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 25),
            run_before=scroll_down
        )

    async def test_hunk_selection_state(
        self, snap_compare, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test visual state when a hunk is selected."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)
        
        async def select_second_hunk(pilot):
            await pilot.pause(0.2)
            await pilot.press("j")  # Move to second hunk
            await pilot.pause(0.1)
        
        assert await snap_compare(
            app,
            terminal_size=(120, 30),
            run_before=select_second_hunk
        )

    async def test_approve_toggle_state(
        self, snap_compare, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test visual state after toggling approve on hunks."""
        app = EnhancedAutoSquashApp(blame_matched_mappings, mock_commit_history_analyzer)
        
        async def toggle_approve_all(pilot):
            await pilot.pause(0.2)
            await pilot.press("a")  # Toggle all approved
            await pilot.pause(0.1)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=toggle_approve_all
        )

    async def test_ignore_toggle_state(
        self, snap_compare, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test visual state after toggling ignore on hunks."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)
        
        async def toggle_ignore_all(pilot):
            await pilot.pause(0.2)
            await pilot.press("i")  # Toggle all ignored
            await pilot.pause(0.1)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=toggle_ignore_all
        )

    async def test_batch_modal_opened(
        self, snap_compare, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test visual state when batch operations modal is opened."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)
        
        async def open_batch_modal(pilot):
            await pilot.pause(0.2)
            await pilot.press("b")  # Open batch operations
            await pilot.pause(0.3)  # Allow modal to open
        
        assert await snap_compare(
            app,
            terminal_size=(120, 35),
            run_before=open_batch_modal
        )

    async def test_radio_button_selection(
        self, snap_compare, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test visual state when different radio button is selected."""
        app = EnhancedAutoSquashApp(blame_matched_mappings, mock_commit_history_analyzer)
        
        async def select_different_commit(pilot):
            await pilot.pause(0.2)
            # Click on second radio button (if available)
            radio_buttons = pilot.app.query("RadioButton")
            if len(radio_buttons) > 1:
                await pilot.click(radio_buttons[1])
            await pilot.pause(0.1)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=select_different_commit
        )

    async def test_diff_viewer_content(
        self, snap_compare, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test diff viewer showing hunk content."""
        app = EnhancedAutoSquashApp(blame_matched_mappings, mock_commit_history_analyzer)
        
        async def select_hunk_show_diff(pilot):
            await pilot.pause(0.2)
            # Click on first hunk to show its diff
            hunk_widgets = pilot.app.query("FallbackHunkMappingWidget")
            if hunk_widgets:
                await pilot.click(hunk_widgets[0])
            await pilot.pause(0.1)
        
        assert await snap_compare(
            app,
            terminal_size=(120, 30),
            run_before=select_hunk_show_diff
        )

    async def test_progress_summary_updates(
        self, snap_compare, mixed_mappings, mock_commit_history_analyzer
    ):
        """Test that progress summary updates correctly."""
        app = EnhancedAutoSquashApp(mixed_mappings, mock_commit_history_analyzer)
        
        async def change_selections(pilot):
            await pilot.pause(0.2)
            # Change some selections to update progress
            await pilot.press("space")  # Toggle current
            await pilot.press("j")      # Move to next
            await pilot.press("space")  # Toggle next
            await pilot.pause(0.1)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=change_selections
        )

    async def test_empty_state_no_hunks(
        self, snap_compare, mock_commit_history_analyzer
    ):
        """Test visual state when no hunks are provided."""
        app = EnhancedAutoSquashApp([], mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_single_hunk_layout(
        self, snap_compare, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test layout with only a single hunk."""
        single_hunk = [blame_matched_mappings[0]]
        app = EnhancedAutoSquashApp(single_hunk, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_very_long_file_paths(
        self, snap_compare, mock_commit_history_analyzer, sample_diff_hunks
    ):
        """Test layout with very long file paths."""
        # Create hunk with very long path
        from git_autosquash.hunk_parser import DiffHunk
        from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
        
        long_path_hunk = DiffHunk(
            file_path="very/deep/nested/directory/structure/with/many/levels/and/a/very/long/filename_that_might_cause_wrapping_issues.py",
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
            context_before=[],
            context_after=[]
        )
        
        long_path_mapping = HunkTargetMapping(
            hunk=long_path_hunk,
            target_commit="1234567890abcdef1234567890abcdef12345678",
            confidence="high",
            blame_info=[],
            targeting_method=TargetingMethod.BLAME_MATCH,
            needs_user_selection=False
        )
        
        app = EnhancedAutoSquashApp([long_path_mapping], mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_unicode_content_handling(
        self, snap_compare, mock_commit_history_analyzer
    ):
        """Test layout with Unicode content in commit messages and file paths."""
        from git_autosquash.hunk_parser import DiffHunk
        from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
        
        unicode_hunk = DiffHunk(
            file_path="测试文件.py",  # Chinese characters
            old_start=1,
            old_count=1,
            new_start=1,
            new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-# 旧代码", "+# 新代码"],  # Chinese comments
            context_before=[],
            context_after=[]
        )
        
        unicode_mapping = HunkTargetMapping(
            hunk=unicode_hunk,
            target_commit="abcd1234",
            confidence="high",
            blame_info=[],
            targeting_method=TargetingMethod.BLAME_MATCH,
            needs_user_selection=False
        )
        
        app = EnhancedAutoSquashApp([unicode_mapping], mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_error_state_handling(
        self, snap_compare, mock_commit_history_analyzer
    ):
        """Test visual state when errors occur."""
        # This would need to be implemented with actual error scenarios
        # For now, create a mapping with missing data to simulate errors
        from git_autosquash.hunk_parser import DiffHunk
        from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
        
        error_hunk = DiffHunk(
            file_path="",  # Empty path might cause issues
            old_start=0,
            old_count=0,
            new_start=0,
            new_count=0,
            lines=[],  # Empty lines
            context_before=[],
            context_after=[]
        )
        
        error_mapping = HunkTargetMapping(
            hunk=error_hunk,
            target_commit=None,  # No target
            confidence="low",
            blame_info=[],
            targeting_method=TargetingMethod.BLAME_MATCH,
            needs_user_selection=True
        )
        
        app = EnhancedAutoSquashApp([error_mapping], mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )


@pytest.mark.asyncio
class TestThemeVariations:
    """Test different color themes and visual states."""

    async def test_high_confidence_styling(
        self, snap_compare, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test styling for high confidence blame matches."""
        # Ensure all mappings have high confidence
        for mapping in blame_matched_mappings:
            mapping.confidence = "high"
            
        app = EnhancedAutoSquashApp(blame_matched_mappings, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_medium_confidence_styling(
        self, snap_compare, blame_matched_mappings, mock_commit_history_analyzer
    ):
        """Test styling for medium confidence matches."""
        # Set all to medium confidence
        for mapping in blame_matched_mappings:
            mapping.confidence = "medium"
            
        app = EnhancedAutoSquashApp(blame_matched_mappings, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_low_confidence_styling(
        self, snap_compare, fallback_mappings, mock_commit_history_analyzer
    ):
        """Test styling for low confidence fallback scenarios."""
        app = EnhancedAutoSquashApp(fallback_mappings, mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_contextual_blame_styling(
        self, snap_compare, mock_commit_history_analyzer, sample_diff_hunks
    ):
        """Test styling for contextual blame matches."""
        from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
        
        contextual_mapping = HunkTargetMapping(
            hunk=sample_diff_hunks[0],
            target_commit="d59d269184f1f320a1e4d31bddde6440cceae7e1",
            confidence="medium",
            blame_info=[],
            targeting_method=TargetingMethod.CONTEXTUAL_BLAME_MATCH,
            needs_user_selection=False
        )
        
        app = EnhancedAutoSquashApp([contextual_mapping], mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )

    async def test_merge_commit_styling(
        self, snap_compare, mock_commit_history_analyzer, sample_commits, sample_diff_hunks
    ):
        """Test styling when target is a merge commit."""
        from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
        
        # Find merge commit from sample data
        merge_commit = next((c for c in sample_commits if c.is_merge), sample_commits[0])
        
        merge_mapping = HunkTargetMapping(
            hunk=sample_diff_hunks[0],
            target_commit=merge_commit.commit_hash,
            confidence="high",
            blame_info=[],
            targeting_method=TargetingMethod.BLAME_MATCH,
            needs_user_selection=False
        )
        
        app = EnhancedAutoSquashApp([merge_mapping], mock_commit_history_analyzer)
        
        assert await snap_compare(
            app,
            terminal_size=(100, 30),
            run_before=lambda pilot: pilot.pause(0.2)
        )