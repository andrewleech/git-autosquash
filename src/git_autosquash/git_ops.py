"""Git operations module for repository analysis and commands."""

import subprocess
from pathlib import Path
from typing import Optional, Union

from git_autosquash.exceptions import handle_unexpected_error


class GitOps:
    """Handles git operations for repository analysis and validation."""

    def __init__(self, repo_path: Optional[Union[str, Path]] = None) -> None:
        """Initialize GitOps with optional repository path.

        Args:
            repo_path: Path to git repository. Defaults to current directory.
        """
        if repo_path is None:
            self.repo_path = Path.cwd()
        else:
            self.repo_path = Path(repo_path)

    def is_git_available(self) -> bool:
        """Check if git is installed and available.

        Returns:
            True if git command is available, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return False

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

            # For status --porcelain and diff/show commands, preserve trailing whitespace
            # as it's significant (blank context lines in diffs are represented as a single space)
            if (
                len(args) >= 2 and args[0] == "status" and args[1] == "--porcelain"
            ) or (len(args) >= 1 and args[0] in ("show", "diff")):
                output = result.stdout.rstrip("\n")  # Only remove trailing newlines
            else:
                output = result.stdout.strip()  # Full strip for other commands

            return (
                result.returncode == 0,
                output or result.stderr.strip(),
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

    def validate_merge_base(self, base_ref: str) -> tuple[bool, str, Optional[str]]:
        """Validate that a base reference is valid and usable as a merge-base.

        Args:
            base_ref: Git reference (branch name, commit hash, etc.)

        Returns:
            Tuple of (is_valid, error_message, resolved_commit_hash)
            If is_valid is True, error_message will be empty and resolved_commit_hash will be set
            If is_valid is False, error_message will contain the reason and resolved_commit_hash will be None
        """
        # First, check if the ref exists and resolve it to a commit hash
        success, output = self._run_git_command("rev-parse", "--verify", base_ref)
        if not success:
            return False, f"Reference '{base_ref}' does not exist", None

        resolved_hash = output.strip()

        # Check if it's actually a commit (not a tree or blob)
        success, obj_type = self._run_git_command("cat-file", "-t", resolved_hash)
        if not success or obj_type.strip() != "commit":
            return (
                False,
                f"'{base_ref}' is not a commit (type: {obj_type.strip()})",
                None,
            )

        # Check if the base is an ancestor of HEAD
        success, _ = self._run_git_command(
            "merge-base", "--is-ancestor", resolved_hash, "HEAD"
        )
        if not success:
            return (
                False,
                f"'{base_ref}' is not an ancestor of HEAD (not in current branch history)",
                None,
            )

        # Check if there are commits between base and HEAD
        success, output = self._run_git_command(
            "rev-list", "--count", f"{resolved_hash}..HEAD"
        )
        if not success:
            return False, f"Failed to check commits since '{base_ref}'", None

        try:
            count = int(output.strip())
            if count == 0:
                return False, f"No commits between '{base_ref}' and HEAD", None
        except ValueError:
            return False, f"Failed to parse commit count for '{base_ref}'", None

        return True, "", resolved_hash

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

    def run_git_command_with_input(
        self, args: list[str], input_text: str, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command with stdin input and return the complete result.

        Args:
            args: Git command arguments (without 'git')
            input_text: Text to provide as stdin to the command
            env: Optional environment variables

        Returns:
            CompletedProcess with stdout, stderr, and return code
        """
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                input=input_text,
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
