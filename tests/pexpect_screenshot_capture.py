#!/usr/bin/env python3
"""
Pexpect-based TUI Screenshot Capture System

⚠️  DEPRECATED: This approach has timing and reliability issues.
    Use scripts/generate_screenshots.py for Textual-native screenshots.
    See CLAUDE.md "Screenshot Generation" section for details.

This module uses pexpect to properly interact with git-autosquash's input() calls
and pyte to capture the TUI output as images.
"""

import asyncio
import os
import time
from pathlib import Path
from typing import List, Dict, Any
from contextlib import contextmanager
import subprocess
import tempfile

import pexpect
import pyte
from PIL import Image, ImageDraw, ImageFont


class PexpectScreenshotCapture:
    """
    Screenshot capture using pexpect for terminal interaction and pyte for rendering.

    This approach properly handles git-autosquash's input() calls by using pexpect
    to simulate a real terminal session.
    """

    def __init__(self, output_dir: Path, terminal_size: tuple = (120, 40)):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.terminal_size = terminal_size  # (columns, rows)
        self.screenshot_counter = 0

    async def capture_app_flow(
        self,
        app_command: List[str],
        interactions: List[Dict[str, Any]] | None = None,
        scenario_name: str = "app",
    ) -> List[Path]:
        """
        Capture screenshots of an application flow using pexpect.

        Args:
            app_command: Command to run the application (e.g., ['git-autosquash'])
            interactions: List of interactions to simulate
            scenario_name: Name for the screenshot series

        Returns:
            List of screenshot file paths
        """
        screenshots: List[Path] = []

        # Create a virtual terminal for rendering
        screen = pyte.Screen(self.terminal_size[0], self.terminal_size[1])
        stream = pyte.Stream(screen)

        # Ensure output directory is absolute
        if not self.output_dir.is_absolute():
            original_cwd = os.getcwd()
            self.output_dir = (Path(original_cwd) / self.output_dir).resolve()

        try:
            # Set up environment
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["COLUMNS"] = str(self.terminal_size[0])
            env["LINES"] = str(self.terminal_size[1])

            # Start the application with pexpect
            child = pexpect.spawn(
                " ".join(app_command),  # pexpect expects a single command string
                env=env,
                timeout=10,
            )
            child.setwinsize(self.terminal_size[1], self.terminal_size[0])

            # Wait for initial choice prompt
            print("Waiting for git-autosquash choice prompt...")

            try:
                index = child.expect(
                    [
                        "Your choice",  # Simplified pattern - just match "Your choice"
                        pexpect.TIMEOUT,
                        pexpect.EOF,
                    ],
                    timeout=10,
                )  # Longer timeout

                if index == 0:
                    # Found choice prompt, feed output to pyte and capture
                    full_output = child.before.decode("utf-8", errors="replace")
                    stream.feed(full_output)

                    screenshot_path = await self._capture_screen(
                        screen, f"{scenario_name}_01_initial"
                    )
                    screenshots.append(screenshot_path)

                    # Send 'c\n' to proceed to TUI
                    print("Sending 'c' to proceed to TUI...")
                    child.send("c\n")

                    # Wait for TUI to load
                    await asyncio.sleep(2.0)

                    # Try to read TUI output
                    try:
                        # Read whatever is available
                        tui_output = ""
                        start_time = time.time()

                        while time.time() - start_time < 3.0:
                            if not child.isalive():
                                break

                            try:
                                # Use read_nonblocking to get available output
                                chunk = child.read_nonblocking(size=8192, timeout=0.5)
                                if chunk:
                                    # Decode bytes to string
                                    chunk_str = chunk.decode("utf-8", errors="replace")
                                    tui_output += chunk_str
                                else:
                                    break
                            except pexpect.TIMEOUT:
                                break  # No more output available
                            except pexpect.EOF:
                                break  # Process ended

                        if tui_output:
                            print(f"Captured TUI output ({len(tui_output)} chars)")
                            stream.feed(tui_output)

                            # Take final screenshot with TUI
                            screenshot_path = await self._capture_screen(
                                screen, f"{scenario_name}_tui_loaded"
                            )
                            screenshots.append(screenshot_path)
                        else:
                            print("No TUI output captured")

                    except Exception as e:
                        print(f"Error reading TUI output: {e}")

                    # Process additional interactions if provided
                    if interactions:
                        for i, interaction in enumerate(interactions, 3):
                            await self._simulate_pexpect_interaction(child, interaction)
                            await asyncio.sleep(0.5)

                            # Try to capture output after interaction
                            try:
                                chunk = child.read_nonblocking(size=8192, timeout=1.0)
                                if chunk:
                                    # Decode bytes to string
                                    chunk_str = chunk.decode("utf-8", errors="replace")
                                    stream.feed(chunk_str)
                                    screenshot_path = await self._capture_screen(
                                        screen,
                                        f"{scenario_name}_{i:02d}_interaction_{i - 2}",
                                    )
                                    screenshots.append(screenshot_path)
                            except (pexpect.TIMEOUT, pexpect.EOF):
                                pass

                    # Final screenshot - use the scenario name directly
                    screenshot_path = await self._capture_screen(screen, scenario_name)
                    screenshots.append(screenshot_path)

                else:
                    print(f"Failed to find choice prompt (index: {index})")
                    if index == 1:  # TIMEOUT
                        print("Timeout - output received:")
                        print(child.before.decode("utf-8", errors="replace"))

            except pexpect.exceptions.ExceptionPexpect as e:
                print(f"Pexpect error: {e}")

            # Cleanup
            try:
                if child.isalive():
                    child.send("q")
                    child.expect(pexpect.EOF, timeout=2)
            except Exception:
                if child.isalive():
                    child.terminate()

        except Exception as e:
            print(f"Error capturing app flow: {e}")
            # Create error file
            error_path = self.output_dir / f"{scenario_name}_error.txt"
            error_path.write_text(f"Capture failed: {e}")
            screenshots.append(error_path)

        return screenshots

    async def _simulate_pexpect_interaction(self, child, interaction: Dict[str, Any]):
        """Simulate user interaction with the pexpect child."""
        interaction_type = interaction.get("type", "key")

        if interaction_type == "key":
            key = interaction.get("key", "")
            if key == "enter":
                child.send("\n")
            elif key == "space":
                child.send(" ")
            elif key == "tab":
                child.send("\t")
            elif key == "escape":
                child.send("\x1b")
            elif key == "q":
                child.send("q")
            else:
                child.send(key)

        elif interaction_type == "wait":
            duration = interaction.get("duration", 0.5)
            await asyncio.sleep(duration)

        elif interaction_type == "text":
            text = interaction.get("text", "")
            child.send(text)

    async def _capture_screen(self, screen: pyte.Screen, name: str) -> Path:
        """Capture the current screen state as text and convert to image."""

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Save as text first
        text_path = self.output_dir / f"{name}.txt"
        screen_text = self._screen_to_text(screen)
        text_path.write_text(screen_text)

        # Convert to image
        image_path = self.output_dir / f"{name}.png"
        await self._text_to_image(screen_text, image_path, screen)

        print(f"Working directory: {os.getcwd()}")
        print(f"Captured screenshot: {image_path.absolute()}")
        print(f"Text file: {text_path.absolute()}")
        print(f"Image file exists: {image_path.exists()}")
        print(f"Text file exists: {text_path.exists()}")
        if text_path.exists():
            print(f"Text content preview: {screen_text[:200]}...")
        return image_path

    def _screen_to_text(self, screen: pyte.Screen) -> str:
        """Convert pyte screen to text representation."""
        lines = []
        for row in range(screen.lines):
            line_chars = []
            for col in range(screen.columns):
                try:
                    char = screen.buffer[row][col]
                    line_chars.append(char.data if hasattr(char, "data") else str(char))
                except (IndexError, KeyError):
                    line_chars.append(" ")
            lines.append("".join(line_chars).rstrip())

        # Remove trailing empty lines
        while lines and not lines[-1].strip():
            lines.pop()

        return "\\n".join(lines)

    async def _text_to_image(self, text: str, image_path: Path, screen: pyte.Screen):
        """Convert text representation to a PNG image."""

        # Try to get a monospace font
        try:
            # Common monospace fonts
            font_paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
                "/System/Library/Fonts/Monaco.ttf",
                "C:\\\\Windows\\\\Fonts\\\\consola.ttf",
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

        # Calculate image dimensions
        lines = text.split("\\n")
        max_width = max(len(line) for line in lines) if lines else 80

        # Get font metrics
        try:
            bbox = font.getbbox("M")  # Use 'M' as reference character
            char_width = bbox[2] - bbox[0]
            char_height = bbox[3] - bbox[1] + 2  # Add line spacing
        except Exception:
            char_width = 8
            char_height = 16

        img_width = max_width * char_width + 20  # Add padding
        img_height = len(lines) * char_height + 20  # Add padding

        # Create image
        img = Image.new(
            "RGB", (int(img_width), int(img_height)), color=(12, 12, 12)
        )  # Dark background
        draw = ImageDraw.Draw(img)

        # Draw text with basic color support
        y_offset = 10
        for line in lines:
            # Basic terminal color parsing (simplified)
            clean_line = self._strip_ansi(line)

            # Use white text for now (could be enhanced with ANSI color parsing)
            draw.text((10, y_offset), clean_line, font=font, fill=(255, 255, 255))
            y_offset += char_height

        # Save image
        img.save(image_path)

    def _strip_ansi(self, text: str) -> str:
        """Remove ANSI escape sequences from text."""
        import re

        # Fixed regex pattern to avoid nested set warning
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    async def capture_git_autosquash_workflow(
        self, repo_path: Path, scenario_name: str = "git_autosquash"
    ) -> List[Path]:
        """
        Capture a complete git-autosquash workflow using pexpect.

        Args:
            repo_path: Path to git repository to run autosquash on
            scenario_name: Name for the screenshot series

        Returns:
            List of screenshot file paths
        """

        # Change to the repository directory but preserve output path
        original_cwd = os.getcwd()

        # Convert output_dir to absolute path before changing directories
        if not self.output_dir.is_absolute():
            self.output_dir = (Path(original_cwd) / self.output_dir).resolve()

        os.chdir(repo_path)

        try:
            # Define interaction sequence for git-autosquash
            interactions: List[Dict[str, Any]] = [
                {"type": "wait", "duration": 1.0},  # Let TUI settle
                {"type": "key", "key": "j"},  # Navigate down
                {"type": "wait", "duration": 0.3},
                {"type": "key", "key": "space"},  # Toggle approval
                {"type": "wait", "duration": 0.3},
                {"type": "key", "key": "j"},  # Navigate down
                {"type": "wait", "duration": 0.3},
                {"type": "key", "key": "enter"},  # Confirm selection
                {"type": "wait", "duration": 0.5},
                {"type": "key", "key": "q"},  # Quit
            ]

            screenshots = await self.capture_app_flow(
                ["git-autosquash"], interactions, scenario_name
            )

        finally:
            os.chdir(original_cwd)

        return screenshots


@contextmanager
def temporary_git_repo_with_changes():
    """Create a temporary git repository with sample changes for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Create initial files
        (repo_path / "main.py").write_text("""def main():
    print("Hello World")
    return 0

if __name__ == "__main__":
    main()
""")

        (repo_path / "utils.py").write_text("""def helper():
    pass
""")

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        # Make changes
        (repo_path / "main.py").write_text("""def main():
    print("Hello World!")  # Added exclamation
    print("Starting application...")  # New line
    return 0

if __name__ == "__main__":
    main()
""")

        (repo_path / "utils.py").write_text('''def helper():
    """Helper function for utilities."""  # Added docstring
    pass

def new_helper():  # New function
    return True
''')

        yield repo_path


if __name__ == "__main__":
    # Demo/test the screenshot system
    async def main():
        import sys
        from pathlib import Path

        output_dir = Path("screenshots/pexpect_demo")
        capture = PexpectScreenshotCapture(output_dir)

        print("Testing pexpect screenshot capture...")

        # Test with real git repo using the existing test repo creator
        try:
            sys.path.append(str(Path(__file__).parent.parent / "scripts"))
            from screenshot_test_repo import create_screenshot_repository

            repo = create_screenshot_repository()
            print(f"Testing with test repo at {repo.repo_path}")
            real_screenshots = await capture.capture_git_autosquash_workflow(
                repo.repo_path, "real_demo"
            )
            print(f"Created {len(real_screenshots)} real screenshots")
        except Exception as e:
            print(f"Real workflow test failed: {e}")

        print(f"Screenshots saved to: {output_dir}")

    asyncio.run(main())
