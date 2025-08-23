"""CLI entry point for git-autosquash."""

import argparse
import subprocess
import sys

from git_autosquash import __version__
from git_autosquash.git_ops import GitOps


def main() -> None:
    """Main entry point for git-autosquash command."""
    parser = argparse.ArgumentParser(
        prog="git-autosquash",
        description="Automatically squash changes back into historical commits",
    )
    parser.add_argument(
        "--line-by-line",
        action="store_true",
        help="Use line-by-line hunk splitting instead of default git hunks",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    _args = parser.parse_args()  # TODO: Use args for --line-by-line in Phase 2

    try:
        git_ops = GitOps()

        # Phase 1: Validate git repository
        if not git_ops.is_git_repo():
            print("Error: Not in a git repository", file=sys.stderr)
            sys.exit(1)

        current_branch = git_ops.get_current_branch()
        if not current_branch:
            print("Error: Not on a branch (detached HEAD)", file=sys.stderr)
            sys.exit(1)

        merge_base = git_ops.get_merge_base_with_main(current_branch)
        if not merge_base:
            print("Error: Could not find merge base with main/master", file=sys.stderr)
            sys.exit(1)

        # Check if there are commits to work with
        if not git_ops.has_commits_since_merge_base(merge_base):
            print(
                "Error: No commits found on current branch since merge base",
                file=sys.stderr,
            )
            sys.exit(1)

        # Analyze working tree status
        status = git_ops.get_working_tree_status()
        print(f"Current branch: {current_branch}")
        print(f"Merge base: {merge_base}")
        print(
            f"Working tree status: staged={status['has_staged']}, unstaged={status['has_unstaged']}, clean={status['is_clean']}"
        )

        # Handle mixed staged/unstaged state
        if status["has_staged"] and status["has_unstaged"]:
            print("\nMixed staged and unstaged changes detected.")
            print("Choose an option:")
            print("  a) Process all changes (staged + unstaged)")
            print("  s) Stash unstaged changes and process only staged")
            print("  q) Quit")

            choice = input("Your choice [a/s/q]: ").lower().strip()
            if choice == "q":
                print("Operation cancelled")
                sys.exit(0)
            elif choice == "s":
                print("Stash-only mode selected (not yet implemented)")
            elif choice == "a":
                print("Process-all mode selected")
            else:
                print("Invalid choice, defaulting to process all")
        elif status["is_clean"]:
            print("Working tree is clean, will reset HEAD~1 and process those changes")
        elif status["has_staged"]:
            print("Processing staged changes")
        else:
            print("Processing unstaged changes")

        # TODO: Continue with remaining phases
        print("Implementation in progress...")

    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"Git operation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
