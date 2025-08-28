#!/usr/bin/env python3
"""
Script to capture all screenshots needed for the README.md

This script generates a comprehensive set of screenshots following the
principal code reviewer's recommendations.
"""

import asyncio
from pathlib import Path
from typing import List, Dict

from tests.pyte_screenshot_capture import PyteScreenshotCapture, MockTerminalCapture


class ReadmeScreenshotGenerator:
    """Generates all screenshots needed for the README.md"""

    def __init__(self, output_dir: Path | None = None):
        if output_dir is None:
            output_dir = Path("screenshots/readme")

        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.pyte_capture = PyteScreenshotCapture(output_dir, terminal_size=(120, 35))
        self.mock_capture = MockTerminalCapture(output_dir)

    async def generate_all_screenshots(self) -> Dict[str, List[Path]]:
        """Generate all README screenshots organized by category."""
        screenshots = {}

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

        return screenshots

    async def capture_hero_screenshot(self) -> List[Path]:
        """Generate the main hero screenshot for top of README."""
        # Create an enhanced mock that looks like a real session
        hero_mock = """git-autosquash - Interactive Hunk Target Selection
        
┌─ Changes to Review ──────────────────────────────────┐ ┌─ Target Commits ─────────────────────────────────┐
│ ✓ src/auth.py:45-52        [HIGH 95%]               │ │ 🎯 abc1234 Fix login validation (2 days ago)     │
│ ◯ src/dashboard.py:15-23   [HIGH 89%]               │ │ 🎯 def5678 Add user dashboard (3 days ago)       │
│ ◯ tests/test_auth.py:67-70 [MED  76%]               │ │ 🎯 ghi9012 Update auth tests (4 days ago)        │
│ ? src/utils.py:12-18       [FALLBACK]               │ │ ❓ No clear target - needs review                │
└──────────────────────────────────────────────────────┘ └───────────────────────────────────────────────────┘

┌─ Preview: src/auth.py:45-52 ─────────────────────────────────────────────────────────────────────────┐
│  44 │     def validate_login(self, email, password):                                                    │
│  45 │-        if not email or not password:                                                            │
│  45 │+        if not email or not password or len(password) < 8:  # Enhanced validation               │
│  46 │             raise ValueError("Invalid credentials")                                              │
│  47 │-        return self.check_user(email, password)                                                  │
│  47 │+        return self.check_user(email.lower(), password)    # Normalize email                    │
│  48 │     def logout_user(self):                                                                       │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘

[Space] Toggle approval  [Enter] Apply changes  [Tab] Switch panels  [q] Quit"""

        hero_path = self.output_dir / "hero_screenshot.txt"
        hero_path.write_text(hero_mock)

        # Convert to image
        png_path = self.output_dir / "hero_screenshot.png"
        await self._text_to_image(hero_mock, png_path)

        return [hero_path, png_path]

    async def capture_workflow_sequence(self) -> List[Path]:
        """Generate step-by-step workflow screenshots."""

        workflow_steps = [
            # Step 1: Before - git status
            """$ git status
On branch feature/user-dashboard
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git checkout -- <file>..." to discard changes)

        modified:   src/auth.py
        modified:   src/dashboard.py
        modified:   tests/test_auth.py
        modified:   src/utils.py

no changes added to commit (use "git add" or "git commit -a")""",
            # Step 2: Launch git-autosquash
            """$ git-autosquash
🔍 Analyzing working directory changes...
📋 Found 4 modified files with 8 hunks
🎯 Analyzing git blame for target resolution...
✨ Opening interactive TUI...""",
            # Step 3: TUI Analysis View
            """git-autosquash - Analysis Results

✅ HIGH CONFIDENCE MATCHES (3 hunks)
  src/auth.py:45-52        → abc1234 "Fix login validation" 
  src/dashboard.py:15-23   → def5678 "Add user dashboard"
  tests/test_auth.py:67-70 → ghi9012 "Update auth tests"

⚠️  MEDIUM CONFIDENCE (1 hunk)  
  src/utils.py:85-90       → jkl3456 "Add utility helpers"

❓ NEEDS REVIEW (1 hunk)
  src/utils.py:12-18       → No clear target found

Press [Space] to continue to interactive review...""",
            # Step 4: Interactive Review
            """git-autosquash - Interactive Review

┌─ Changes ────────────────────────────────┐ ┌─ Selected Target ──────────────────────┐
│ ✓ src/auth.py:45-52        [HIGH 95%]   │ │ Commit: abc1234                        │
│ ✓ src/dashboard.py:15-23   [HIGH 89%]   │ │ Author: dev@example.com                │
│ ◯ tests/test_auth.py:67-70 [MED  76%]   │ │ Date: 2 days ago                       │
│ ◯ src/utils.py:85-90       [MED  64%]   │ │ Message: Fix login validation          │
│ ? src/utils.py:12-18       [FALLBACK]   │ │                                        │
└──────────────────────────────────────────┘ └────────────────────────────────────────┘

Ready to apply 2 approved changes. Continue? [y/N]: y""",
            # Step 5: Execution Progress
            """git-autosquash - Applying Changes

✅ Backing up current state...
✅ Starting interactive rebase...
🔄 Squashing src/auth.py:45-52 → abc1234
🔄 Squashing src/dashboard.py:15-23 → def5678
✅ Rebase completed successfully!

📊 Summary:
  - 2 hunks squashed into historical commits  
  - 2 hunks left as working directory changes
  - 0 conflicts encountered
  
✨ Your git history has been cleaned up!""",
            # Step 6: After - clean git log
            """$ git log --oneline -5
def5678 Add user dashboard              # Enhanced with dashboard fixes
abc1234 Fix login validation           # Enhanced with auth improvements  
hij7890 Add utility functions
klm1234 Initial authentication system
nop5678 Project setup""",
        ]

        screenshots = []
        for i, step_content in enumerate(workflow_steps, 1):
            step_path = self.output_dir / f"workflow_step_{i:02d}.txt"
            step_path.write_text(step_content)

            png_path = self.output_dir / f"workflow_step_{i:02d}.png"
            await self._text_to_image(step_content, png_path)

            screenshots.extend([step_path, png_path])

        return screenshots

    async def capture_feature_demonstrations(self) -> List[Path]:
        """Generate individual feature demonstration screenshots."""

        features = {
            "smart_targeting": """git-autosquash - Smart Targeting Demo

Git Blame Analysis:
abc1234  (dev@example.com  2024-01-15 14:23:45 -0800  45) def validate_login(email, pass):
abc1234  (dev@example.com  2024-01-15 14:23:45 -0800  46)     if not email or not pass:
abc1234  (dev@example.com  2024-01-15 14:23:45 -0800  47)         raise ValueError("Invalid")

Your Changes:
+    if not email or not pass or len(pass) < 8:  # Enhanced validation

🎯 Smart Target Resolution:
   Confidence: 95% → Commit abc1234 "Fix login validation"
   Reason: All modified lines trace to same commit""",
            "interactive_tui": """git-autosquash - Interactive Interface

Navigation:        Keyboard Shortcuts:
[↑↓] Move cursor   [Space] Toggle approval
[Tab] Switch pane  [Enter] Apply changes  
[PgUp/Dn] Scroll   [Escape] Cancel
                   [q] Quit application

Current Selection:
┌─ src/auth.py:45-52 ─────────────────────────────┐
│  45 │- if not email or not password:             │
│  45 │+ if not email or not password or len(...): │
└─────────────────────────────────────────────────┘

Status: ✓ APPROVED for squashing into abc1234""",
            "safety_first": """git-autosquash - Safety Features

⚠️  SAFETY DEFAULTS:
All changes start UNAPPROVED - you must explicitly review and approve

Current Status:
◯ src/auth.py:45-52        [Not approved] 
◯ src/dashboard.py:15-23   [Not approved]
◯ tests/test_auth.py:67-70 [Not approved]

🛡️  ROLLBACK PROTECTION:
- Full git reflog integration
- Backup refs created before rebase  
- Easy recovery with: git reset --hard ORIG_HEAD

Proceed only after careful review!""",
            "conflict_resolution": """git-autosquash - Conflict Resolution

⚠️  MERGE CONFLICT DETECTED

File: src/auth.py
Conflict in commit: abc1234 "Fix login validation"

┌─ Conflict Details ──────────────────────────────────┐
│ <<<<<<< HEAD                                        │
│ if not email or not password:                       │
│ =======                                             │  
│ if not email or not password or len(password) < 8: │
│ >>>>>>> feature/enhanced-validation                 │
└─────────────────────────────────────────────────────┘

Options:
[r] Retry after manual resolution
[s] Skip this hunk and continue
[a] Abort entire rebase operation""",
            "progress_tracking": """git-autosquash - Progress Tracking

📊 REBASE PROGRESS: Step 3 of 5

✅ Completed:
  ✓ Backup created (ORIG_HEAD)
  ✓ src/auth.py:45-52 → abc1234
  ✓ src/dashboard.py:15-23 → def5678

🔄 Current:
  → tests/test_auth.py:67-70 → ghi9012 "Update auth tests"

⏳ Remaining:
  - src/utils.py:85-90 → jkl3456
  - Finalize rebase

Estimated time: 30 seconds""",
        }

        screenshots = []
        for feature_name, content in features.items():
            text_path = self.output_dir / f"feature_{feature_name}.txt"
            text_path.write_text(content)

            png_path = self.output_dir / f"feature_{feature_name}.png"
            await self._text_to_image(content, png_path)

            screenshots.extend([text_path, png_path])

        return screenshots

    async def capture_comparison_views(self) -> List[Path]:
        """Generate before/after comparison screenshots."""

        before_after = {
            "before_traditional": """Traditional Approach - Messy History

$ git log --oneline -8
abc1234 Fix lint errors and address review feedback  😞
def5678 Add dashboard feature
ghi9012 Fix failing tests  😞  
jkl3456 Address PR comments 😞
mno7890 Add user authentication 
pqr1234 More lint fixes 😞
stu5678 Add utility functions
vwx9012 Initial setup

Problem: Hard to understand what each commit actually accomplishes!""",
            "after_autosquash": """After git-autosquash - Clean History  

$ git log --oneline -5  
def5678 Add dashboard feature              ✨ Includes dashboard improvements
mno7890 Add user authentication           ✨ Includes auth enhancements  
stu5678 Add utility functions             ✨ Includes utility refinements
vwx9012 Initial setup
                                          
✅ Each commit tells complete, focused story
✅ No more "fix" commits cluttering history  
✅ Easy to understand and review changes""",
            "history_comparison": """Side-by-Side History Comparison

BEFORE git-autosquash:          │  AFTER git-autosquash:
                               │
* Fix lint and review feedback │  
* Add dashboard feature        │  * Add dashboard feature (enhanced)
* Fix failing auth tests       │  * Add user authentication (complete)  
* Address PR feedback          │  * Add utility functions (refined)
* Add user authentication      │  * Initial project setup
* Fix more lint issues         │  
* Add utility functions        │  Clean, logical progression! 
* Initial project setup        │  Each commit = complete feature
                               │
Cluttered, hard to follow      │  """,
        }

        screenshots = []
        for comparison_name, content in before_after.items():
            text_path = self.output_dir / f"comparison_{comparison_name}.txt"
            text_path.write_text(content)

            png_path = self.output_dir / f"comparison_{comparison_name}.png"
            await self._text_to_image(content, png_path)

            screenshots.extend([text_path, png_path])

        return screenshots

    async def capture_fallback_scenarios(self) -> List[Path]:
        """Generate fallback scenario demonstrations."""

        fallback_scenarios = {
            "new_file_fallback": """git-autosquash - New File Handling

❓ NEW FILE DETECTED: src/new_feature.py

No git blame history available (file didn't exist before)

┌─ Fallback Options ────────────────────────────────────┐
│ 1. 📅 Most recent commit in branch:                   │
│    abc1234 "Add dashboard feature" (2 days ago)       │
│                                                        │
│ 2. 🎯 Commits that modified similar files:            │
│    def5678 "Add auth system" (modified src/auth.py)   │
│    ghi9012 "Add utilities" (modified src/utils.py)    │
│                                                        │
│ 3. ➕ Keep as new commit                               │
│    (Recommended for genuinely new functionality)      │
└────────────────────────────────────────────────────────┘

Your choice: [1/2/3]""",
            "ambiguous_blame_fallback": """git-autosquash - Ambiguous Target Resolution

⚠️  MULTIPLE POSSIBLE TARGETS for src/utils.py:45-50

Git blame shows mixed history:
Line 45: abc1234 "Add utility functions"    (60% match)
Line 46: abc1234 "Add utility functions"    (60% match)  
Line 47: def5678 "Refactor utilities"       (40% match)
Line 48: def5678 "Refactor utilities"       (40% match)

┌─ Target Options ───────────────────────────────────────┐
│ ◯ abc1234 "Add utility functions" (3 weeks ago)       │
│   └─ Lines 45-46 originated here                      │
│                                                        │
│ ◯ def5678 "Refactor utilities" (1 week ago)           │
│   └─ Lines 47-48 last modified here                   │ 
│                                                        │
│ ◯ Skip this hunk (leave in working directory)         │
└────────────────────────────────────────────────────────┘

Select target: [1/2/3]""",
            "manual_override": """git-autosquash - Manual Override

🎯 SUGGESTED TARGET: def5678 "Add dashboard feature"
   Confidence: 75% (Medium)

💡 YOU CAN OVERRIDE THIS SUGGESTION

┌─ Alternative Targets ──────────────────────────────────┐
│ ◯ abc1234 "Fix login validation" (High confidence)    │
│ ◯ def5678 "Add dashboard feature" ← SUGGESTED          │
│ ◯ ghi9012 "Update auth tests" (Low confidence)        │
│ ◯ [Custom] Enter different commit hash                │
│ ◯ [Skip] Leave in working directory                   │
└────────────────────────────────────────────────────────┘

Sometimes you know better than the algorithm! 
Use manual override when:
- You remember the real context
- Suggested target doesn't make sense
- You want to group related changes""",
        }

        screenshots = []
        for scenario_name, content in fallback_scenarios.items():
            text_path = self.output_dir / f"fallback_{scenario_name}.txt"
            text_path.write_text(content)

            png_path = self.output_dir / f"fallback_{scenario_name}.png"
            await self._text_to_image(content, png_path)

            screenshots.extend([text_path, png_path])

        return screenshots

    async def _text_to_image(self, text: str, image_path: Path):
        """Convert text to PNG image using PIL."""
        from PIL import Image, ImageDraw, ImageFont
        import os
        import re

        # Try to get a monospace font
        try:
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
                "/System/Library/Fonts/Monaco.ttf",
                "C:\\Windows\\Fonts\\consola.ttf",
            ]

            font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, 14)
                    break

            if font is None:
                font = ImageFont.load_default()

        except Exception:
            font = ImageFont.load_default()

        # Remove ANSI escape codes
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        clean_text = ansi_escape.sub("", text)

        lines = clean_text.split("\n")
        max_width = max(len(line) for line in lines) if lines else 80

        # Calculate image dimensions
        try:
            bbox = font.getbbox("M")
            char_width = bbox[2] - bbox[0]
            char_height = bbox[3] - bbox[1] + 4  # Add line spacing
        except Exception:
            char_width = 8
            char_height = 16

        img_width = max_width * char_width + 40  # Add padding
        img_height = len(lines) * char_height + 40  # Add padding

        # Create image with terminal-like appearance
        img = Image.new(
            "RGB", (img_width, img_height), color=(18, 18, 18)
        )  # Dark background
        draw = ImageDraw.Draw(img)

        # Draw text
        y_offset = 20
        for line in lines:
            # Basic syntax highlighting colors
            color = (255, 255, 255)  # Default white

            # Color coding for different elements
            if line.strip().startswith("✅") or line.strip().startswith("✓"):
                color = (0, 255, 0)  # Green for success
            elif line.strip().startswith("⚠️") or line.strip().startswith("◯"):
                color = (255, 255, 0)  # Yellow for warnings
            elif line.strip().startswith("❓") or line.strip().startswith("?"):
                color = (255, 165, 0)  # Orange for questions
            elif line.strip().startswith("🎯") or "HIGH" in line:
                color = (0, 255, 128)  # Light green for high confidence
            elif "MED" in line or "MEDIUM" in line:
                color = (255, 255, 0)  # Yellow for medium confidence
            elif "LOW" in line or "FALLBACK" in line:
                color = (255, 128, 0)  # Orange for low confidence
            elif line.strip().startswith("#") or line.strip().startswith("$"):
                color = (128, 255, 255)  # Cyan for commands/comments
            elif "commit" in line or "abc1234" in line or "def5678" in line:
                color = (255, 182, 193)  # Light pink for commit refs

            draw.text((20, y_offset), line, font=font, fill=color)
            y_offset += char_height

        # Save image
        img.save(image_path)
        print(f"  📸 Created: {image_path}")


async def main():
    """Generate all README screenshots."""
    print("🎬 Starting README screenshot generation...")

    generator = ReadmeScreenshotGenerator()

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

    except Exception as e:
        print(f"❌ Error generating screenshots: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
