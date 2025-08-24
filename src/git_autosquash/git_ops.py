"""Git operations module for repository analysis and commands."""

import subprocess
from pathlib import Path
from typing import Optional

from git_autosquash.exceptions import handle_unexpected_error


class GitOps:
    """Handles git operations for repository analysis and validation."""

    def __init__(self, repo_path: Optional[Path] = None) -> None:
        """Initialize GitOps with optional repository path.

        Args:
            repo_path: Path to git repository. Defaults to current directory.
        """
        self.repo_path = repo_path if repo_path is not None else Path.cwd()

    def _run_git_command(self, *args: str) -> tuple[bool, str]:
        """Run a git command and return success status and output.

        Args:
            *args: Git command arguments

        Returns:
            Tuple of (success, output/error_message)
        """
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            return (
                result.returncode == 0,
                result.stdout.strip() or result.stderr.strip(),
            )
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            return False, f"Git command failed: {e}"

    def _run_git_command_with_input(
        self, *args: str, input_text: str
    ) -> tuple[bool, str]:
        """Run a git command with input text and return success status and output.

        Args:
            *args: Git command arguments
            input_text: Text to provide as stdin to the command

        Returns:
            Tuple of (success, output/error_message)
        """
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.repo_path,
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
            )
            return (
                result.returncode == 0,
                result.stdout.strip() or result.stderr.strip(),
            )
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            return False, f"Git command failed: {e}"

    def is_git_repo(self) -> bool:
        """Check if current directory is inside a git repository.

        Returns:
            True if in a git repository, False otherwise
        """
        success, _ = self._run_git_command("rev-parse", "--git-dir")
        return success

    def get_current_branch(self) -> Optional[str]:
        """Get the current branch name.

        Returns:
            Branch name if on a branch, None if detached HEAD
        """
        success, output = self._run_git_command("symbolic-ref", "--short", "HEAD")
        return output if success else None

    def get_merge_base_with_main(self, current_branch: str) -> Optional[str]:
        """Find merge base with main/master branch.

        Args:
            current_branch: Current branch name

        Returns:
            Commit hash of merge base, or None if not found
        """
        # Try merge-base directly, let git handle missing refs
        for main_branch in ["main", "master"]:
            if main_branch == current_branch:
                continue

            success, output = self._run_git_command(
                "merge-base", main_branch, current_branch
            )
            if success:
                return output

        return None

    def get_working_tree_status(self) -> dict[str, bool]:
        """Get working tree status information.

        Returns:
            Dictionary with status flags: has_staged, has_unstaged, is_clean
        """
        success, output = self._run_git_command("status", "--porcelain")
        if not success:
            return {"has_staged": False, "has_unstaged": False, "is_clean": True}

        lines = output.split("\n") if output else []
        has_staged = any(line and line[0] not in "? " for line in lines)
        has_unstaged = any(line and line[1] not in " " for line in lines)
        is_clean = not lines or all(not line.strip() for line in lines)

        return {
            "has_staged": has_staged,
            "has_unstaged": has_unstaged,
            "is_clean": is_clean,
        }

    def has_commits_since_merge_base(self, merge_base: str) -> bool:
        """Check if there are commits on current branch since merge base.

        Args:
            merge_base: Merge base commit hash

        Returns:
            True if there are commits to work with
        """
        success, output = self._run_git_command(
            "rev-list", "--count", f"{merge_base}..HEAD"
        )
        if not success:
            return False

        try:
            count = int(output)
            return count > 0
        except ValueError:
            return False

    def run_git_command(
        self, args: list[str], env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command and return the complete result.

        Args:
            args: Git command arguments (without 'git')
            env: Optional environment variables

        Returns:
            CompletedProcess with stdout, stderr, and return code
        """
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                env=env,
                timeout=300,  # 5 minute timeout
            )
            return result
        except subprocess.TimeoutExpired as e:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=124,  # timeout exit code
                stdout=e.stdout.decode() if e.stdout else "",
                stderr=f"Command timed out after 300 seconds: {e}",
            )
        except (OSError, PermissionError, FileNotFoundError) as e:
            # File system or permission errors
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr=f"System error: {e}",
            )
        except Exception as e:
            # Unexpected errors - wrap for better reporting
            wrapped = handle_unexpected_error(e, f"git command: {' '.join(cmd)}")
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr=str(wrapped),
            )
