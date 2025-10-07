#!/usr/bin/env python3
"""
Consolidated Screenshot Generator for git-autosquash

This script uses Textual's built-in screenshot capabilities to generate
high-quality SVG screenshots of the git-autosquash TUI.

This is the OFFICIAL and RECOMMENDED approach for capturing screenshots,
replacing older pexpect/pyte-based methods.

Usage:
    python scripts/generate_screenshots.py [--output-dir DIR] [--format svg|png]

Requirements:
    - pytest-textual-snapshot (installed via dev dependencies)
    - Textual (core dependency)
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.hunk_target_resolver import HunkTargetResolver
from git_autosquash.commit_history_analyzer import CommitHistoryAnalyzer
from git_autosquash.tui.modern_app import ModernAutoSquashApp
from scripts.screenshot_test_repo import (
    create_screenshot_repository,
    ScreenshotTestRepo,
)


class TextualScreenshotGenerator:
    """Generate screenshots using Textual's native screenshot capabilities."""

    def __init__(
        self,
        output_dir: Path,
        terminal_size: tuple[int, int] = (120, 40),
        format: str = "svg",
    ):
        """Initialize screenshot generator.

        Args:
            output_dir: Directory to save screenshots
            terminal_size: Terminal dimensions (width, height)
            format: Output format ('svg' or 'png')
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.terminal_size = terminal_size
        self.format = format.lower()
        self.test_repos: List[ScreenshotTestRepo] = []

    def cleanup(self) -> None:
        """Clean up temporary test repositories."""
        for repo in self.test_repos:
            repo.cleanup()
        self.test_repos.clear()

    async def capture_app_screenshot(
        self,
        name: str,
        interactions: Optional[List[dict]] = None,
        scenario: str = "default",
    ) -> Path:
        """Capture a screenshot of the git-autosquash TUI.

        Args:
            name: Screenshot filename (without extension)
            interactions: List of interaction dicts with 'type' and parameters
                         e.g., [{"type": "key", "keys": ["j", "space"]}]
            scenario: Test scenario for repository setup

        Returns:
            Path to the captured screenshot file

        Example:
            await capture_app_screenshot(
                "hero_screenshot",
                interactions=[
                    {"type": "wait", "duration": 1.0},
                    {"type": "key", "keys": ["j", "space"]}
                ]
            )
        """
        # Create test repository
        repo = create_screenshot_repository()
        self.test_repos.append(repo)

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

            # Parse hunks and resolve targets
            hunk_parser = HunkParser(git_ops)
            hunks = hunk_parser.get_diff_hunks(line_by_line=False)

            resolver = HunkTargetResolver(git_ops, merge_base)
            mappings = resolver.resolve_targets(hunks)

            commit_analyzer = CommitHistoryAnalyzer(git_ops, merge_base)

            # Create the app
            app = ModernAutoSquashApp(mappings, commit_analyzer)

            # Capture screenshot using Pilot
            async with app.run_test(size=self.terminal_size) as pilot:
                # Let app initialize
                await pilot.pause(0.5)

                # Apply interactions if provided
                if interactions:
                    for interaction in interactions:
                        if interaction["type"] == "wait":
                            await pilot.pause(interaction["duration"])
                        elif interaction["type"] == "key":
                            for key in interaction["keys"]:
                                await pilot.press(key)
                                await pilot.pause(0.1)
                        elif interaction["type"] == "click":
                            # Not commonly used but available
                            await pilot.click(interaction.get("selector"))

                # Wait a bit before capturing to ensure rendering is complete
                await pilot.pause(0.3)

                # Capture screenshot
                screenshot_path = self.output_dir / f"{name}.{self.format}"

                if self.format == "svg":
                    svg_content = pilot.app.export_screenshot()
                    screenshot_path.write_text(svg_content)
                else:
                    # For PNG, we'd need to convert SVG
                    # This requires additional dependencies (cairosvg or similar)
                    raise NotImplementedError(
                        "PNG export requires SVG-to-PNG conversion. "
                        "Use SVG format and convert externally if needed."
                    )

                print(f"✓ Captured: {screenshot_path.name}")
                return screenshot_path

        finally:
            os.chdir(original_cwd)

    async def generate_hero_screenshot(self) -> Path:
        """Generate the main hero screenshot for README."""
        return await self.capture_app_screenshot(
            "hero_screenshot",
            interactions=[
                {"type": "wait", "duration": 1.0},
            ],
        )

    async def generate_workflow_screenshots(self) -> List[Path]:
        """Generate step-by-step workflow screenshots."""
        screenshots = []

        # Step 1: Initial state
        screenshots.append(
            await self.capture_app_screenshot(
                "workflow_01_initial",
                interactions=[
                    {"type": "wait", "duration": 0.8},
                ],
            )
        )

        # Step 2: After selecting first hunk
        screenshots.append(
            await self.capture_app_screenshot(
                "workflow_02_select_first",
                interactions=[
                    {"type": "wait", "duration": 0.8},
                    {"type": "key", "keys": ["space"]},
                    {"type": "wait", "duration": 0.3},
                ],
            )
        )

        # Step 3: Navigate and select more hunks
        screenshots.append(
            await self.capture_app_screenshot(
                "workflow_03_multi_select",
                interactions=[
                    {"type": "wait", "duration": 0.8},
                    {"type": "key", "keys": ["space", "j", "space"]},
                    {"type": "wait", "duration": 0.3},
                ],
            )
        )

        # Step 4: View target commits
        screenshots.append(
            await self.capture_app_screenshot(
                "workflow_04_view_targets",
                interactions=[
                    {"type": "wait", "duration": 0.8},
                    {"type": "key", "keys": ["tab"]},
                    {"type": "wait", "duration": 0.3},
                ],
            )
        )

        return screenshots

    async def generate_all_screenshots(self) -> dict[str, List[Path]]:
        """Generate all screenshot categories."""
        screenshots = {}

        try:
            print("🎬 Generating screenshots...\n")

            print("📸 Hero screenshot...")
            screenshots["hero"] = [await self.generate_hero_screenshot()]

            print("\n📸 Workflow screenshots...")
            screenshots["workflow"] = await self.generate_workflow_screenshots()

            print(
                f"\n✨ Generated {sum(len(v) for v in screenshots.values())} screenshots"
            )
            print(f"📁 Output: {self.output_dir}")

        finally:
            self.cleanup()

        return screenshots


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate screenshots for git-autosquash documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate default screenshots
  python scripts/generate_screenshots.py

  # Specify output directory
  python scripts/generate_screenshots.py --output-dir docs/screenshots

  # Change terminal size
  python scripts/generate_screenshots.py --width 140 --height 50
        """,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("screenshots/textual"),
        help="Output directory for screenshots (default: screenshots/textual)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=120,
        help="Terminal width in columns (default: 120)",
    )
    parser.add_argument(
        "--height", type=int, default=40, help="Terminal height in rows (default: 40)"
    )
    parser.add_argument(
        "--format",
        choices=["svg", "png"],
        default="svg",
        help="Output format (default: svg)",
    )
    parser.add_argument(
        "--hero-only", action="store_true", help="Generate only the hero screenshot"
    )

    args = parser.parse_args()

    # Create generator
    generator = TextualScreenshotGenerator(
        output_dir=args.output_dir,
        terminal_size=(args.width, args.height),
        format=args.format,
    )

    # Generate screenshots
    async def run():
        if args.hero_only:
            await generator.generate_hero_screenshot()
        else:
            await generator.generate_all_screenshots()

    try:
        asyncio.run(run())
        print("\n🎉 Screenshot generation complete!")
        return 0
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        generator.cleanup()


if __name__ == "__main__":
    sys.exit(main())
