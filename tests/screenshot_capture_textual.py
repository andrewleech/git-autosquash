#!/usr/bin/env python3
"""
Textual-Native Screenshot Capture System

⚠️  DEPRECATED: This was an experimental implementation.
    Use scripts/generate_screenshots.py for the official production-ready version.
    See CLAUDE.md "Screenshot Generation" section for details.

This module uses pytest-textual-snapshot to capture high-quality SVG screenshots
of the git-autosquash TUI interface, replacing the pyte-based approach with
official Textual tooling.
"""

import os
from pathlib import Path
from typing import List, Optional

# For creating test repositories
import sys

sys.path.append(str(Path(__file__).parent.parent / "scripts"))
from screenshot_test_repo import create_screenshot_repository

# For running git-autosquash functionality
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.hunk_target_resolver import HunkTargetResolver
from git_autosquash.commit_history_analyzer import CommitHistoryAnalyzer
from git_autosquash.squash_context import SquashContext
from git_autosquash.tui.modern_app import ModernAutoSquashApp


class TextualScreenshotCapture:
    """Screenshot capture using pytest-textual-snapshot and Textual's native testing tools."""

    def __init__(self, output_dir: Path, terminal_size: tuple = (120, 40)):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.terminal_size = terminal_size

    def create_app_with_test_data(
        self, scenario: str = "default"
    ) -> ModernAutoSquashApp:
        """Create a ModernAutoSquashApp instance with realistic test data.

        Args:
            scenario: Test scenario type for different data configurations

        Returns:
            Configured ModernAutoSquashApp ready for screenshot testing
        """
        # Create test repository with different scenarios
        repo = create_screenshot_repository()

        # Change to repo directory to run git commands
        original_cwd = os.getcwd()
        os.chdir(repo.repo_path)

        try:
            # Initialize git operations
            git_ops = GitOps()
            current_branch = git_ops.get_current_branch()
            if current_branch is None:
                raise ValueError("Could not determine current branch")

            merge_base = git_ops.get_merge_base_with_main(current_branch)
            if merge_base is None:
                raise ValueError("Could not determine merge base")

            # Parse hunks from current changes
            hunk_parser = HunkParser(git_ops)
            hunks = hunk_parser.get_diff_hunks(line_by_line=False)

            # Create context for working tree changes
            context = SquashContext(
                blame_ref="HEAD",
                source_commit=None,
                is_historical_commit=False,
                working_tree_clean=False,
            )

            # Resolve targets for hunks
            resolver = HunkTargetResolver(git_ops, merge_base, context)
            mappings = resolver.resolve_targets(hunks)

            # Create commit analyzer
            commit_analyzer = CommitHistoryAnalyzer(git_ops, merge_base)

            # Create the app
            app = ModernAutoSquashApp(mappings, commit_analyzer)

            return app

        finally:
            os.chdir(original_cwd)

    async def capture_app_states(
        self, scenario_name: str, interactions: Optional[List[str]] = None
    ) -> List[Path]:
        """Capture screenshots of different app states.

        Args:
            scenario_name: Name for the screenshot series
            interactions: List of key sequences to simulate

        Returns:
            List of screenshot file paths
        """
        screenshots = []

        # Import pytest-textual-snapshot functionality

        # Create app instance
        app = self.create_app_with_test_data(scenario_name)

        # Use snap_compare to capture the app
        # Note: This is normally used in pytest tests, but we can use it directly
        # for screenshot generation
        try:
            # The snap_compare function expects a pytest environment
            # For now, let's create a simpler approach using Textual's built-in capabilities

            # Capture screenshot using Textual's screenshot functionality
            screenshot_path = await self._capture_textual_screenshot(
                app, f"{scenario_name}_01_initial"
            )
            screenshots.append(screenshot_path)

            # If interactions provided, simulate them
            if interactions:
                for i, interaction in enumerate(interactions, 2):
                    # Apply interaction to app
                    self._apply_interaction(app, interaction)

                    # Capture state after interaction
                    screenshot_path = await self._capture_textual_screenshot(
                        app, f"{scenario_name}_{i:02d}_{interaction}"
                    )
                    screenshots.append(screenshot_path)

            # Final screenshot
            final_screenshot = await self._capture_textual_screenshot(
                app, f"{scenario_name}_final"
            )
            screenshots.append(final_screenshot)

        except Exception as e:
            print(f"Error capturing screenshots: {e}")
            # Create error file
            error_path = self.output_dir / f"{scenario_name}_error.txt"
            error_path.write_text(f"Capture failed: {e}")
            screenshots.append(error_path)

        return screenshots

    async def _capture_textual_screenshot(
        self, app: ModernAutoSquashApp, name: str
    ) -> Path:
        """Capture a screenshot using Textual's built-in screenshot capability.

        Args:
            app: The Textual app to screenshot
            name: Name for the screenshot file

        Returns:
            Path to the captured screenshot
        """
        # For now, use a simple approach that runs the app in a controlled way
        # This will be refined to use pytest-textual-snapshot properly

        screenshot_path = self.output_dir / f"{name}.svg"

        # Textual apps have a screenshot method, but it requires the app to be running
        # For testing, we need to use the Pilot testing framework

        try:

            async def capture_screenshot():
                """Async function to capture screenshot using Pilot."""
                # Use Pilot to control the app
                async with app.run_test(size=self.terminal_size) as pilot:
                    # Let the app initialize
                    await pilot.pause(1.0)

                    # Take screenshot
                    svg_content = pilot.app.export_screenshot()
                    screenshot_path.write_text(svg_content)

                    return screenshot_path

            # Run the async screenshot capture
            result = await capture_screenshot()
            print(f"Captured screenshot: {result}")
            return result

        except Exception as e:
            # Fallback: create a placeholder
            print(f"Screenshot capture failed: {e}")
            placeholder_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 400">
  <rect width="1200" height="400" fill="#000000"/>
  <text x="600" y="200" text-anchor="middle" fill="white" font-family="monospace" font-size="16">
    Screenshot capture failed: {name}
  </text>
  <text x="600" y="230" text-anchor="middle" fill="gray" font-family="monospace" font-size="12">
    Error: {e}
  </text>
</svg>"""
            screenshot_path.write_text(placeholder_content)
            return screenshot_path

    def _apply_interaction(self, app: ModernAutoSquashApp, interaction: str):
        """Apply an interaction to the app (simulate keypress, etc).

        Args:
            app: The app to interact with
            interaction: The interaction to apply (e.g., "space", "enter", "q")
        """
        # This would be implemented using Textual's Pilot testing framework
        # For now, it's a placeholder
        pass

    async def generate_hero_screenshot(self) -> Path:
        """Generate the main hero screenshot showing git-autosquash TUI."""
        screenshots = await self.capture_app_states("hero_screenshot")
        # Return the final screenshot as the hero
        if not screenshots:
            raise RuntimeError("Failed to generate hero screenshot")
        return screenshots[-1]

    async def generate_workflow_screenshots(self) -> List[Path]:
        """Generate step-by-step workflow screenshots."""
        workflow_screenshots = []

        # Step 1: Initial launch
        screenshots = await self.capture_app_states("workflow_step_01")
        workflow_screenshots.extend(screenshots)

        # Step 2: Analysis complete
        screenshots = await self.capture_app_states("workflow_step_02", ["space"])
        workflow_screenshots.extend(screenshots)

        # Step 3: Navigate and select
        screenshots = await self.capture_app_states("workflow_step_03", ["j", "space"])
        workflow_screenshots.extend(screenshots)

        # Step 4: Review targets
        screenshots = await self.capture_app_states("workflow_step_04", ["tab"])
        workflow_screenshots.extend(screenshots)

        # Step 5: Execute
        screenshots = await self.capture_app_states("workflow_step_05", ["enter"])
        workflow_screenshots.extend(screenshots)

        return workflow_screenshots

    async def generate_feature_screenshots(self) -> List[Path]:
        """Generate feature demonstration screenshots."""
        feature_screenshots = []

        # Smart targeting
        screenshots = await self.capture_app_states("feature_smart_targeting")
        feature_screenshots.extend(screenshots)

        # Interactive TUI
        screenshots = await self.capture_app_states(
            "feature_interactive_tui", ["j", "space"]
        )
        feature_screenshots.extend(screenshots)

        # Safety first
        screenshots = await self.capture_app_states("feature_safety_first", ["?"])
        feature_screenshots.extend(screenshots)

        return feature_screenshots


if __name__ == "__main__":
    # Demo the new screenshot system
    import asyncio

    async def main():
        output_dir = Path("screenshots/textual_demo")
        capture = TextualScreenshotCapture(output_dir)

        print("Testing Textual-native screenshot capture...")

        # Test hero screenshot
        hero_path = await capture.generate_hero_screenshot()
        print(f"Hero screenshot: {hero_path}")

        # Test workflow screenshots
        workflow_paths = await capture.generate_workflow_screenshots()
        print(f"Workflow screenshots: {len(workflow_paths)} files")

        print(f"Screenshots saved to: {output_dir}")

    asyncio.run(main())
