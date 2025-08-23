"""CLI entry point for git-autosquash."""

import argparse
import subprocess
import sys

from git_autosquash import __version__
from git_autosquash.blame_analyzer import BlameAnalyzer
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.tui.app import AutoSquashApp


def _simple_approval_fallback(mappings, blame_analyzer):
    """Simple text-based approval fallback when TUI fails.

    Args:
        mappings: List of hunk target mappings
        blame_analyzer: BlameAnalyzer instance for getting commit summaries

    Returns:
        List of approved mappings
    """
    from git_autosquash.blame_analyzer import HunkTargetMapping
    from typing import List

    print("\nReview hunk → commit mappings:")
    print("=" * 60)

    approved_mappings: List[HunkTargetMapping] = []

    for i, mapping in enumerate(mappings, 1):
        commit_summary = blame_analyzer.get_commit_summary(mapping.target_commit)
        hunk = mapping.hunk

        print(f"\n[{i}/{len(mappings)}] {hunk.file_path}")
        print(f"  Lines: {hunk.new_start}-{hunk.new_start + hunk.new_count - 1}")
        print(f"  Target: {commit_summary}")
        print(f"  Confidence: {mapping.confidence}")

        # Show a few lines of the diff
        diff_lines = hunk.lines[1:4]  # Skip @@ header, show first 3 lines
        for line in diff_lines:
            print(f"  {line}")
        if len(hunk.lines) > 4:
            print(f"  ... ({len(hunk.lines) - 1} total lines)")

        while True:
            choice = input("\nApprove this mapping? [y/n/q]: ").lower().strip()
            if choice == "y":
                approved_mappings.append(mapping)
                break
            elif choice == "n":
                break
            elif choice == "q":
                print("Operation cancelled")
                return []
            else:
                print("Please enter y, n, or q")

    return approved_mappings


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

    args = parser.parse_args()

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

        # Phase 2: Parse hunks and analyze blame
        print("\nAnalyzing changes and finding target commits...")

        hunk_parser = HunkParser(git_ops)
        hunks = hunk_parser.get_diff_hunks(line_by_line=args.line_by_line)

        if not hunks:
            print("No changes found to process", file=sys.stderr)
            sys.exit(1)

        print(f"Found {len(hunks)} hunks to process")

        # Analyze hunks with blame to find target commits
        blame_analyzer = BlameAnalyzer(git_ops, merge_base)
        mappings = blame_analyzer.analyze_hunks(hunks)

        # Filter out mappings without target commits
        valid_mappings = [m for m in mappings if m.target_commit is not None]

        if not valid_mappings:
            print("No valid target commits found for any hunks", file=sys.stderr)
            print(
                "This may happen if all changes are in new files or outside branch scope"
            )
            sys.exit(1)

        print(f"Found target commits for {len(valid_mappings)} hunks")

        # Phase 3: Show TUI for user approval
        print("\nLaunching interactive approval interface...")

        try:
            app = AutoSquashApp(valid_mappings)
            approved = app.run()

            if approved and app.approved_mappings:
                approved_mappings = app.approved_mappings
                print(f"\nUser approved {len(approved_mappings)} hunks for squashing")

                # TODO: Phase 4 - Execute the interactive rebase
                print("Phase 4 (rebase execution) not yet implemented")
                print("\nApproved mappings:")
                for mapping in approved_mappings:
                    try:
                        if mapping.target_commit:
                            commit_summary = blame_analyzer.get_commit_summary(
                                mapping.target_commit
                            )
                            print(f"  {mapping.hunk.file_path} → {commit_summary}")
                        else:
                            print(f"  {mapping.hunk.file_path} → No target commit")
                    except Exception as e:
                        print(
                            f"  {mapping.hunk.file_path} → {mapping.target_commit} (summary failed: {e})"
                        )

            else:
                print("\nOperation cancelled by user or no hunks approved")

        except ImportError as e:
            print(f"\nTextual TUI not available: {e}")
            print("Falling back to simple text-based approval...")
            approved_mappings = _simple_approval_fallback(
                valid_mappings, blame_analyzer
            )

            if approved_mappings:
                print(f"\nApproved {len(approved_mappings)} hunks for squashing")
                # TODO: Phase 4 - Execute the interactive rebase
                print("Phase 4 (rebase execution) not yet implemented")
            else:
                print("\nOperation cancelled")

        except Exception as e:
            print(f"\nTUI encountered an error: {e}")
            print("Falling back to simple text-based approval...")
            approved_mappings = _simple_approval_fallback(
                valid_mappings, blame_analyzer
            )

            if approved_mappings:
                print(f"\nApproved {len(approved_mappings)} hunks for squashing")
                # TODO: Phase 4 - Execute the interactive rebase
                print("Phase 4 (rebase execution) not yet implemented")
            else:
                print("\nOperation cancelled")

    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"Git operation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
