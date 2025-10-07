#!/usr/bin/env python3
"""
Real Application Screenshot Generator for git-autosquash

⚠️  DEPRECATED: This script uses pexpect for terminal capture.
    Use scripts/generate_screenshots.py instead for Textual-native screenshots.
    See CLAUDE.md "Screenshot Generation" section for details.

This script generates authentic screenshots by running the real git-autosquash
application on realistic test repositories and capturing actual terminal output.
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import List, Dict

# Add current directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

# PyteScreenshotCapture replaced with working PexpectScreenshotCapture
from scripts.screenshot_test_repo import (
    create_screenshot_repository,
    ScreenshotTestRepo,
)


class RealScreenshotGenerator:
    """Generates authentic screenshots using real git-autosquash application."""

    def __init__(self, output_dir: Path | None = None):
        if output_dir is None:
            # Use docs directory for MkDocs integration
            script_dir = Path(__file__).parent
            output_dir = script_dir / "docs" / "screenshots" / "readme"

        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Use working pexpect capture system for real TUI screenshots
        import sys

        sys.path.append(str(Path(__file__).parent / "tests"))
        from pexpect_screenshot_capture import PexpectScreenshotCapture

        self.pexpect_capture = PexpectScreenshotCapture(
            output_dir, terminal_size=(120, 40)
        )
        self.test_repos: List[ScreenshotTestRepo] = []

    def cleanup(self) -> None:
        """Clean up test repositories."""
        for repo in self.test_repos:
            repo.cleanup()
        self.test_repos.clear()

    async def generate_all_screenshots(self) -> Dict[str, List[Path]]:
        """Generate all README screenshots using real application."""
        screenshots = {}

        try:
            print("🎯 Generating hero screenshot...")
            screenshots["hero"] = await self.capture_hero_screenshot()

            print("📋 Generating workflow sequence...")
            screenshots["workflow"] = await self.capture_workflow_sequence()

            print("⚡ Generating feature demonstrations...")
            screenshots["features"] = await self.capture_feature_demonstrations()

            print("📊 Generating comparison views...")
            screenshots["comparisons"] = await self.capture_comparison_views()

            print("🔄 Generating fallback scenarios...")
            screenshots["fallbacks"] = await self.capture_fallback_scenarios()

        finally:
            self.cleanup()

        return screenshots

    async def capture_hero_screenshot(self) -> List[Path]:
        """Generate the main hero screenshot showing git-autosquash TUI."""
        # Create realistic repository
        repo = create_screenshot_repository()
        self.test_repos.append(repo)

        # Change to repo directory
        original_cwd = os.getcwd()
        os.chdir(repo.repo_path)

        try:
            # Capture initial git-autosquash screen
            screenshots = await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {
                        "type": "key",
                        "key": "a\n",
                    },  # Choose "Process all changes" + Enter
                    {
                        "type": "wait",
                        "duration": 5.0,
                    },  # Let TUI fully load and analysis complete
                ],
                scenario_name="hero_screenshot",
            )
            return screenshots

        finally:
            os.chdir(original_cwd)

    async def capture_workflow_sequence(self) -> List[Path]:
        """Generate step-by-step workflow screenshots."""
        repo = create_screenshot_repository()
        self.test_repos.append(repo)

        original_cwd = os.getcwd()
        os.chdir(repo.repo_path)
        screenshots = []

        try:
            # Step 1: Show git status (before)
            step1 = await self.pexpect_capture.capture_app_flow(
                app_command=["git", "status"],
                interactions=[{"type": "wait", "duration": 0.5}],
                scenario_name="workflow_step_01",
            )
            screenshots.extend(step1)

            # Step 2: Launch git-autosquash and show initial analysis (no selections)
            step2 = await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {
                        "type": "wait",
                        "duration": 4.0,
                    },  # Let analysis complete and TUI fully render
                    {
                        "type": "key",
                        "key": "q",
                    },  # Quit to capture fully loaded analysis screen
                ],
                scenario_name="workflow_step_02",
            )
            screenshots.extend(step2)

            # Step 3: Show interactive review with selective approvals
            step3 = await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {"type": "wait", "duration": 3.0},  # Let analysis complete
                    {"type": "key", "key": "space"},  # Toggle first hunk (approve)
                    {"type": "wait", "duration": 1.0},  # Let UI update
                    {"type": "key", "key": "down"},  # Move to next hunk
                    {"type": "wait", "duration": 0.5},
                    {"type": "key", "key": "down"},  # Move to third hunk (skip second)
                    {"type": "wait", "duration": 0.5},
                    {"type": "key", "key": "space"},  # Toggle third hunk (approve)
                    {
                        "type": "wait",
                        "duration": 1.0,
                    },  # Let UI update and show selections
                    {"type": "key", "key": "q"},  # Quit to capture selection state
                ],
                scenario_name="workflow_step_03",
            )
            screenshots.extend(step3)

            # Step 4: Show execution confirmation dialog
            step4 = await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {"type": "wait", "duration": 3.0},  # Let analysis complete
                    {"type": "key", "key": "space"},  # Approve first hunk
                    {"type": "wait", "duration": 0.5},
                    {"type": "key", "key": "down"},
                    {"type": "key", "key": "space"},  # Approve second hunk
                    {"type": "wait", "duration": 0.5},
                    {"type": "key", "key": "down"},
                    {"type": "key", "key": "space"},  # Approve third hunk
                    {"type": "wait", "duration": 0.5},
                    {"type": "key", "key": "enter"},  # Trigger confirmation dialog
                    {"type": "wait", "duration": 2.0},  # Let confirmation dialog appear
                    {"type": "text", "text": "n"},  # Cancel to avoid actual execution
                ],
                scenario_name="workflow_step_04",
            )
            screenshots.extend(step4)

            # Step 5: Show git log after successful operation
            # First actually run the operation
            await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {"type": "wait", "duration": 2.0},
                    {"type": "key", "key": "space"},  # Approve first
                    {"type": "key", "key": "down"},
                    {"type": "key", "key": "space"},  # Approve second
                    {"type": "key", "key": "enter"},
                    {"type": "text", "text": "y"},  # Confirm execution
                    {"type": "wait", "duration": 3.0},  # Let rebase complete
                ],
                scenario_name="workflow_step_05_execution",
            )

            # Then show the cleaned git log
            step5 = await self.pexpect_capture.capture_app_flow(
                app_command=["git", "log", "--oneline", "-10"],
                interactions=[{"type": "wait", "duration": 0.5}],
                scenario_name="workflow_step_05",
            )
            screenshots.extend(step5)

        finally:
            os.chdir(original_cwd)

        return screenshots

    async def capture_feature_demonstrations(self) -> List[Path]:
        """Generate feature demonstration screenshots."""
        screenshots = []

        # Smart Targeting Demo
        repo = create_screenshot_repository()
        self.test_repos.append(repo)
        original_cwd = os.getcwd()
        os.chdir(repo.repo_path)

        try:
            smart_targeting = await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {"type": "wait", "duration": 2.5},  # Let full analysis complete
                    {"type": "key", "key": "tab"},  # Switch to target panel
                    {"type": "wait", "duration": 0.5},
                    {"type": "key", "key": "q"},
                ],
                scenario_name="feature_smart_targeting",
            )
            screenshots.extend(smart_targeting)

        finally:
            os.chdir(original_cwd)

        # Interactive TUI Demo
        repo2 = create_screenshot_repository()
        self.test_repos.append(repo2)
        os.chdir(repo2.repo_path)

        try:
            interactive_tui = await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {"type": "wait", "duration": 2.0},
                    {"type": "key", "key": "down"},  # Navigate
                    {"type": "key", "key": "down"},
                    {"type": "key", "key": "space"},  # Toggle approval
                    {"type": "key", "key": "up"},
                    {"type": "key", "key": "space"},  # Toggle another
                    {"type": "wait", "duration": 0.5},
                    {"type": "key", "key": "q"},
                ],
                scenario_name="feature_interactive_tui",
            )
            screenshots.extend(interactive_tui)

        finally:
            os.chdir(original_cwd)

        # Safety First Demo
        repo3 = create_screenshot_repository()
        self.test_repos.append(repo3)
        os.chdir(repo3.repo_path)

        try:
            safety_first = await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {"type": "wait", "duration": 2.0},  # Show initial unapproved state
                    {"type": "key", "key": "q"},
                ],
                scenario_name="feature_safety_first",
            )
            screenshots.extend(safety_first)

        finally:
            os.chdir(original_cwd)

        return screenshots

    async def capture_comparison_views(self) -> List[Path]:
        """Generate before/after comparison screenshots."""
        screenshots = []

        # Before: Traditional approach (messy working directory)
        repo = create_screenshot_repository()
        self.test_repos.append(repo)
        original_cwd = os.getcwd()
        os.chdir(repo.repo_path)

        try:
            # Show messy git status
            before_traditional = await self.pexpect_capture.capture_app_flow(
                app_command=["git", "status", "--short"],
                interactions=[{"type": "wait", "duration": 0.5}],
                scenario_name="comparison_before_traditional",
            )
            screenshots.extend(before_traditional)

            # Show git diff to emphasize the mess
            before_diff = await self.pexpect_capture.capture_app_flow(
                app_command=["git", "diff", "--stat"],
                interactions=[{"type": "wait", "duration": 0.5}],
                scenario_name="comparison_before_diff",
            )
            screenshots.extend(before_diff)

            # After: Run git-autosquash and show clean result
            await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {"type": "wait", "duration": 2.0},
                    {"type": "key", "key": "space"},  # Approve first
                    {"type": "key", "key": "down"},
                    {"type": "key", "key": "space"},  # Approve second
                    {"type": "key", "key": "down"},
                    {"type": "key", "key": "space"},  # Approve third
                    {"type": "key", "key": "enter"},
                    {"type": "text", "text": "y"},  # Execute
                    {"type": "wait", "duration": 4.0},  # Let rebase complete
                ],
                scenario_name="execution_cleanup",
            )

            # Show clean git log
            after_autosquash = await self.pexpect_capture.capture_app_flow(
                app_command=["git", "log", "--oneline", "--graph", "-8"],
                interactions=[{"type": "wait", "duration": 0.5}],
                scenario_name="comparison_after_autosquash",
            )
            screenshots.extend(after_autosquash)

        finally:
            os.chdir(original_cwd)

        return screenshots

    async def capture_fallback_scenarios(self) -> List[Path]:
        """Generate fallback scenario screenshots."""
        screenshots = []

        # Create repository with fallback scenarios
        repo = create_screenshot_repository()
        self.test_repos.append(repo)
        original_cwd = os.getcwd()
        os.chdir(repo.repo_path)

        try:
            # New file fallback (config.json has no git history)
            new_file_fallback = await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {"type": "wait", "duration": 2.5},  # Let analysis find fallbacks
                    {"type": "key", "key": "down"},  # Navigate to fallback hunk
                    {"type": "key", "key": "down"},
                    {"type": "key", "key": "down"},
                    {"type": "key", "key": "down"},
                    {"type": "wait", "duration": 0.5},  # Show fallback state
                    {"type": "key", "key": "q"},
                ],
                scenario_name="fallback_new_file_fallback",
            )
            screenshots.extend(new_file_fallback)

            # Manual override demonstration
            manual_override = await self.pexpect_capture.capture_app_flow(
                app_command=["git-autosquash"],
                interactions=[
                    {"type": "wait", "duration": 1.5},  # Wait for choice prompt
                    {"type": "key", "key": "c"},  # Choose "Continue"
                    {"type": "key", "key": "enter"},  # Press Enter to confirm
                    {"type": "wait", "duration": 2.0},
                    {"type": "key", "key": "down"},  # Go to a hunk
                    {"type": "key", "key": "tab"},  # Switch to targets
                    {"type": "key", "key": "down"},  # Navigate targets
                    {"type": "key", "key": "up"},
                    {"type": "wait", "duration": 0.5},  # Show manual selection
                    {"type": "key", "key": "q"},
                ],
                scenario_name="fallback_manual_override",
            )
            screenshots.extend(manual_override)

        finally:
            os.chdir(original_cwd)

        return screenshots

    def copy_screenshots_to_docs(self):
        """Screenshots are now generated directly in docs directory."""
        print("\n📋 Screenshots generated directly in docs directory...")

        # Count final screenshots (excluding intermediate files)
        png_files = list(self.output_dir.glob("*.png"))
        final_screenshots = [
            png_file
            for png_file in png_files
            if not any(
                intermediate in png_file.name
                for intermediate in ["_01_initial", "_tui_loaded", "_interaction"]
            )
        ]

        print(
            f"📸 Generated {len(final_screenshots)} final screenshots in {self.output_dir}"
        )
        print("📁 Ready for mkdocs integration from docs/screenshots/readme/")


async def main():
    """Generate all README screenshots using real application."""
    print("🎬 Starting REAL README screenshot generation...")
    generator = RealScreenshotGenerator()

    try:
        screenshots = await generator.generate_all_screenshots()

        print("\n📊 Screenshot Generation Summary:")
        total_files = 0
        for category, files in screenshots.items():
            print(f"  {category}: {len(files)} files")
            total_files += len(files)

        print(f"\n✨ Total: {total_files} screenshot files generated")
        print(f"📁 Output directory: {generator.output_dir}")

        # List all PNG files for easy reference
        png_files = list(generator.output_dir.glob("*.png"))
        print(f"\n🖼️  PNG Screenshots ({len(png_files)}):")
        for png_file in sorted(png_files):
            print(f"  - {png_file.name}")

        # Copy screenshots to docs directory
        generator.copy_screenshots_to_docs()

        print("\n🎉 Real application screenshots generated successfully!")

    except Exception as e:
        print(f"\n❌ Error generating screenshots: {e}")
        raise
    finally:
        generator.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
