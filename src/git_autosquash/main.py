"""CLI entry point for git-autosquash."""

import argparse
import subprocess
import sys
from typing import List

from git_autosquash import __version__
from git_autosquash.hunk_target_resolver import HunkTargetResolver
from git_autosquash.exceptions import (
    ErrorReporter,
    GitAutoSquashError,
    RepositoryStateError,
    UserCancelledError,
    handle_unexpected_error,
)
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseConflictError, RebaseManager


def _simple_approval_fallback(mappings, resolver, commit_analyzer=None):
    """Simple text-based approval fallback when TUI fails.

    Args:
        mappings: List of hunk target mappings
        resolver: HunkTargetResolver instance for getting commit summaries
        commit_analyzer: Optional CommitHistoryAnalyzer for fallback scenarios

    Returns:
        Dict with approved and ignored mappings
    """
    from git_autosquash.hunk_target_resolver import HunkTargetMapping

    print("\nReview hunk → commit mappings:")
    print("=" * 60)

    approved_mappings: List[HunkTargetMapping] = []
    ignored_mappings: List[HunkTargetMapping] = []

    for i, mapping in enumerate(mappings, 1):
        hunk = mapping.hunk

        print(f"\n[{i}/{len(mappings)}] {hunk.file_path}")
        print(f"  Lines: {hunk.new_start}-{hunk.new_start + hunk.new_count - 1}")

        # Handle different mapping types
        if mapping.needs_user_selection:
            print(
                f"  Status: Manual selection required ({mapping.targeting_method.value})"
            )

            if commit_analyzer and mapping.fallback_candidates:
                print("  Available targets:")
                for j, commit_hash in enumerate(mapping.fallback_candidates[:5], 1):
                    commit_display = commit_analyzer.get_commit_display_info(
                        commit_hash
                    )
                    print(f"    {j}. {commit_display}")

                while True:
                    choice = (
                        input(
                            f"\nChoose target [1-{min(5, len(mapping.fallback_candidates))}/i/q] or ignore/quit: "
                        )
                        .lower()
                        .strip()
                    )
                    if choice == "i":
                        ignored_mappings.append(mapping)
                        break
                    elif choice == "q":
                        print("Operation cancelled")
                        return {"approved": [], "ignored": []}
                    else:
                        try:
                            target_idx = int(choice) - 1
                            if 0 <= target_idx < len(mapping.fallback_candidates):
                                mapping.target_commit = mapping.fallback_candidates[
                                    target_idx
                                ]
                                mapping.needs_user_selection = False
                                mapping.confidence = "medium"
                                approved_mappings.append(mapping)
                                break
                            else:
                                print("Invalid target number")
                        except ValueError:
                            print(
                                "Please enter a valid number, 'i' (ignore), or 'q' (quit)"
                            )
            else:
                print("  No fallback targets available")
                ignored_mappings.append(mapping)
        else:
            # Regular blame match
            commit_summary = resolver.get_commit_summary(mapping.target_commit)
            print(f"  Target: {commit_summary}")
            print(f"  Confidence: {mapping.confidence}")

            # Show a few lines of the diff
            diff_lines = hunk.lines[1:4]  # Skip @@ header, show first 3 lines
            for line in diff_lines:
                print(f"  {line}")
            if len(hunk.lines) > 4:
                print(f"  ... ({len(hunk.lines) - 1} total lines)")

            while True:
                choice = (
                    input("\nChoose action [s/i/n/q] (squash/ignore/skip/quit): ")
                    .lower()
                    .strip()
                )
                if choice == "s":
                    approved_mappings.append(mapping)
                    break
                elif choice == "i":
                    ignored_mappings.append(mapping)
                    break
                elif choice == "n":
                    break
                elif choice == "q":
                    print("Operation cancelled")
                    return {"approved": [], "ignored": []}
                else:
                    print("Please enter s (squash), i (ignore), n (skip), or q (quit)")

    return {"approved": approved_mappings, "ignored": ignored_mappings}


def _apply_ignored_hunks(ignored_mappings, git_ops) -> bool:
    """Apply ignored hunks back to the working tree using complete git-native solution.

    Uses the complete git-native handler with intelligent strategy selection:
    1. Git worktree (best isolation, requires Git 2.5+)
    2. Git index manipulation (good isolation, compatible)
    3. Automatic fallback between strategies

    Args:
        ignored_mappings: List of ignored hunk to commit mappings
        git_ops: GitOps instance

    Returns:
        True if successful, False if any hunks could not be applied
    """
    from git_autosquash.git_native_complete_handler import create_git_native_handler

    handler = create_git_native_handler(git_ops)
    return handler.apply_ignored_hunks(ignored_mappings)


def _create_patch_for_hunk(hunk) -> str:
    """Create a patch string for a single hunk.

    Args:
        hunk: Hunk to create patch for

    Returns:
        Formatted patch content
    """
    patch_lines = []

    # Add proper diff header
    patch_lines.append(f"diff --git a/{hunk.file_path} b/{hunk.file_path}")
    patch_lines.append("index 0000000..1111111 100644")
    patch_lines.append(f"--- a/{hunk.file_path}")
    patch_lines.append(f"+++ b/{hunk.file_path}")

    # Add hunk content
    patch_lines.extend(hunk.lines)

    return "\n".join(patch_lines) + "\n"


def _execute_rebase(approved_mappings, git_ops, merge_base, resolver) -> bool:
    """Execute the interactive rebase to apply approved mappings.

    Args:
        approved_mappings: List of approved hunk to commit mappings
        git_ops: GitOps instance
        merge_base: Merge base commit hash
        resolver: HunkTargetResolver for getting commit summaries

    Returns:
        True if successful, False if aborted or failed
    """
    try:
        # Initialize rebase manager
        rebase_manager = RebaseManager(git_ops, merge_base)

        # Show what we're about to do
        print(f"Distributing {len(approved_mappings)} hunks to their target commits:")
        commit_counts = {}
        for mapping in approved_mappings:
            if mapping.target_commit:
                if mapping.target_commit not in commit_counts:
                    commit_counts[mapping.target_commit] = 0
                commit_counts[mapping.target_commit] += 1

        for commit_hash, count in commit_counts.items():
            try:
                commit_summary = resolver.get_commit_summary(commit_hash)
                print(f"  {count} hunk{'s' if count > 1 else ''} → {commit_summary}")
            except Exception:
                print(f"  {count} hunk{'s' if count > 1 else ''} → {commit_hash}")

        print("\nStarting rebase operation...")

        # Execute the squash operation
        success = rebase_manager.execute_squash(approved_mappings)

        if success:
            return True
        else:
            print("Rebase operation was cancelled by user")
            return False

    except RebaseConflictError as e:
        print("\n⚠️ Rebase conflicts detected:")
        for file_path in e.conflicted_files:
            print(f"  {file_path}")

        print("\nTo resolve conflicts:")
        print("1. Edit the conflicted files to resolve conflicts")
        print("2. Stage the resolved files: git add <files>")
        print("3. Continue the rebase: git rebase --continue")
        print("4. Or abort the rebase: git rebase --abort")

        return False

    except KeyboardInterrupt:
        print("\n\nRebase operation interrupted by user")
        try:
            rebase_manager.abort_operation()
            print("Rebase aborted, repository restored to original state")
        except Exception as cleanup_error:
            print(f"Warning: Cleanup failed: {cleanup_error}")
            print("You may need to manually abort the rebase: git rebase --abort")

        return False

    except Exception as e:
        print(f"\n✗ Rebase execution failed: {e}")

        # Try to clean up
        try:
            rebase_manager.abort_operation()
            print("Repository restored to original state")
        except Exception as cleanup_error:
            print(f"Warning: Cleanup failed: {cleanup_error}")
            print("You may need to manually abort the rebase: git rebase --abort")

        return False


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
        "--auto-accept",
        action="store_true",
        help="Automatically accept all hunks with blame-identified targets, bypass TUI",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    # Add strategy management subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Import here to avoid circular imports
    from git_autosquash.cli_strategy import add_strategy_subcommands

    add_strategy_subcommands(subparsers)

    args = parser.parse_args()

    # Handle strategy subcommands
    if hasattr(args, "func"):
        sys.exit(args.func(args))

    try:
        git_ops = GitOps()

        # Phase 1: Check git availability
        if not git_ops.is_git_available():
            error = RepositoryStateError(
                "Git is not installed or not available in PATH",
                recovery_suggestion="Please install git and ensure it's available in your PATH environment variable",
            )
            ErrorReporter.report_error(error)
            sys.exit(1)

        # Phase 2: Validate git repository
        if not git_ops.is_git_repo():
            error = RepositoryStateError(
                "Not in a git repository",
                recovery_suggestion="Run this command from within a git repository",
            )
            ErrorReporter.report_error(error)
            sys.exit(1)

        current_branch = git_ops.get_current_branch()
        if not current_branch:
            error = RepositoryStateError(
                "Not on a branch (detached HEAD)",
                recovery_suggestion="Switch to a branch with 'git checkout <branch-name>'",
            )
            ErrorReporter.report_error(error)
            sys.exit(1)

        merge_base = git_ops.get_merge_base_with_main(current_branch)
        if not merge_base:
            error = RepositoryStateError(
                "Could not find merge base with main/master",
                current_state=f"on branch {current_branch}",
                recovery_suggestion="Ensure your branch is based on main/master",
            )
            ErrorReporter.report_error(error)
            sys.exit(1)

        # Check if there are commits to work with
        if not git_ops.has_commits_since_merge_base(merge_base):
            error = RepositoryStateError(
                "No commits found on current branch since merge base",
                current_state=f"merge base: {merge_base}",
                recovery_suggestion="Make some commits on your branch before running git-autosquash",
            )
            ErrorReporter.report_error(error)
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

        # Phase 3: Parse hunks and analyze blame
        print("\nAnalyzing changes and finding target commits...")

        hunk_parser = HunkParser(git_ops)
        hunks = hunk_parser.get_diff_hunks(line_by_line=args.line_by_line)

        if not hunks:
            print("No changes found to process", file=sys.stderr)
            sys.exit(1)

        print(f"Found {len(hunks)} hunks to process")

        # Analyze hunks with enhanced blame and fallback analysis
        resolver = HunkTargetResolver(git_ops, merge_base)
        mappings = resolver.resolve_targets(hunks)

        # Categorize mappings into automatic and fallback
        automatic_mappings = [m for m in mappings if not m.needs_user_selection]
        fallback_mappings = [m for m in mappings if m.needs_user_selection]

        print(f"Found target commits for {len(automatic_mappings)} hunks")
        if fallback_mappings:
            print(
                f"Found {len(fallback_mappings)} hunks requiring manual target selection"
            )

        # If we have no automatic targets and no fallbacks, something is wrong
        if not mappings:
            print("No hunks found to process", file=sys.stderr)
            sys.exit(1)

        # Phase 4: User approval - either auto-accept or interactive TUI
        if args.auto_accept:
            # Auto-accept mode: accept all hunks with automatic blame targets
            approved_mappings = []
            ignored_mappings = []

            print(f"\nAuto-accept mode: Processing {len(mappings)} hunks...")

            for mapping in mappings:
                if mapping.target_commit and not mapping.needs_user_selection:
                    # This hunk has an automatic blame-identified target
                    approved_mappings.append(mapping)
                    commit_summary = resolver.get_commit_summary(mapping.target_commit)
                    print(
                        f"✓ Auto-accepted: {mapping.hunk.file_path} → {commit_summary}"
                    )
                else:
                    # This hunk needs manual selection, leave in working tree
                    ignored_mappings.append(mapping)
                    if mapping.needs_user_selection:
                        print(
                            f"⚠ Left in working tree: {mapping.hunk.file_path} (needs manual selection)"
                        )
                    else:
                        print(
                            f"⚠ Left in working tree: {mapping.hunk.file_path} (no target found)"
                        )

            print(
                f"\nAuto-accepted {len(approved_mappings)} hunks with automatic targets"
            )
            if ignored_mappings:
                print(f"Left {len(ignored_mappings)} hunks in working tree")

            # Execute the rebase for approved hunks
            if approved_mappings:
                success = _execute_rebase(
                    approved_mappings, git_ops, merge_base, resolver
                )
                if not success:
                    print("✗ Squash operation was aborted or failed.")
                    return
            else:
                success = True  # No rebase needed, just apply ignored hunks

            # Apply ignored hunks back to working tree
            if success and ignored_mappings:
                print(
                    f"\nApplying {len(ignored_mappings)} ignored hunks back to working tree..."
                )
                ignore_success = _apply_ignored_hunks(ignored_mappings, git_ops)
                if ignore_success:
                    print("✓ Ignored hunks have been restored to working tree")
                else:
                    print(
                        "⚠️  Some ignored hunks could not be restored - check working tree status"
                    )

            # Report final results for auto-accept mode
            if success:
                if approved_mappings and ignored_mappings:
                    print(
                        "✓ Operation completed! Changes squashed to commits and ignored hunks restored to working tree."
                    )
                elif approved_mappings:
                    print("✓ Squash operation completed successfully!")
                    print("Your changes have been distributed to their target commits.")
                elif ignored_mappings:
                    print("✓ Ignored hunks have been restored to working tree.")
            else:
                print("✗ Operation failed.")

        else:
            # Interactive TUI mode
            print("\nLaunching enhanced interactive approval interface...")

            try:
                # Create commit history analyzer for fallback suggestions
                from git_autosquash.commit_history_analyzer import CommitHistoryAnalyzer

                commit_analyzer = CommitHistoryAnalyzer(git_ops, merge_base)

                # Always use enhanced app for better display of commit information
                from git_autosquash.tui.enhanced_app import EnhancedAutoSquashApp

                app = EnhancedAutoSquashApp(mappings, commit_analyzer)

                approved = app.run()

                if approved and (app.approved_mappings or app.ignored_mappings):
                    approved_mappings = app.approved_mappings
                    ignored_mappings = app.ignored_mappings

                    print(
                        f"\nUser selected {len(approved_mappings)} hunks for squashing"
                    )
                    if ignored_mappings:
                        print(
                            f"User selected {len(ignored_mappings)} hunks to ignore (keep in working tree)"
                        )

                    # Phase 4 - Execute the interactive rebase for approved hunks
                    if approved_mappings:
                        print("\nExecuting interactive rebase for approved hunks...")
                        success = _execute_rebase(
                            approved_mappings, git_ops, merge_base, resolver
                        )

                        if not success:
                            print("✗ Squash operation was aborted or failed.")
                            return
                    else:
                        success = True  # No rebase needed, just apply ignored hunks

                    # Phase 5 - Apply ignored hunks back to working tree
                    if success and ignored_mappings:
                        print(
                            f"\nApplying {len(ignored_mappings)} ignored hunks back to working tree..."
                        )
                        ignore_success = _apply_ignored_hunks(ignored_mappings, git_ops)
                        if ignore_success:
                            print("✓ Ignored hunks have been restored to working tree")
                        else:
                            print(
                                "⚠️  Some ignored hunks could not be restored - check working tree status"
                            )

                    if success:
                        if approved_mappings and ignored_mappings:
                            print(
                                "✓ Operation completed! Changes squashed to commits and ignored hunks restored to working tree."
                            )
                        elif approved_mappings:
                            print("✓ Squash operation completed successfully!")
                            print(
                                "Your changes have been distributed to their target commits."
                            )
                        elif ignored_mappings:
                            print("✓ Ignored hunks have been restored to working tree.")
                    else:
                        print("✗ Operation failed.")

                else:
                    print("\nOperation cancelled by user or no hunks selected")

            except ImportError as e:
                print(f"\nTextual TUI not available: {e}")
                print("Falling back to simple text-based approval...")
                result = _simple_approval_fallback(mappings, resolver, commit_analyzer)

                approved_mappings = result["approved"]
                ignored_mappings = result["ignored"]

                if approved_mappings:
                    print(f"\nApproved {len(approved_mappings)} hunks for squashing")
                    if ignored_mappings:
                        print(
                            f"Selected {len(ignored_mappings)} hunks to ignore (keep in working tree)"
                        )

                    # Phase 4 - Execute the interactive rebase
                    print("\nExecuting interactive rebase...")
                    success = _execute_rebase(
                        approved_mappings, git_ops, merge_base, resolver
                    )

                    if success:
                        print("✓ Squash operation completed successfully!")
                        print(
                            "Your changes have been distributed to their target commits."
                        )

                        # Apply ignored hunks back to working tree
                        if ignored_mappings:
                            print(
                                f"\nApplying {len(ignored_mappings)} ignored hunks back to working tree..."
                            )
                            ignore_success = _apply_ignored_hunks(
                                ignored_mappings, git_ops
                            )
                            if ignore_success:
                                print(
                                    "✓ Ignored hunks have been restored to working tree"
                                )
                            else:
                                print(
                                    "⚠️  Some ignored hunks could not be restored - check working tree status"
                                )
                    else:
                        print("✗ Squash operation was aborted or failed.")
                else:
                    print("\nOperation cancelled")

            except Exception as e:
                print(f"\nTUI encountered an error: {e}")
                print("Falling back to simple text-based approval...")
                result = _simple_approval_fallback(mappings, resolver, commit_analyzer)

                approved_mappings = result["approved"]
                ignored_mappings = result["ignored"]

                if approved_mappings:
                    print(f"\nApproved {len(approved_mappings)} hunks for squashing")
                    if ignored_mappings:
                        print(
                            f"Selected {len(ignored_mappings)} hunks to ignore (keep in working tree)"
                        )

                    # Phase 4 - Execute the interactive rebase
                    print("\nExecuting interactive rebase...")
                    success = _execute_rebase(
                        approved_mappings, git_ops, merge_base, resolver
                    )

                    if success:
                        print("✓ Squash operation completed successfully!")
                        print(
                            "Your changes have been distributed to their target commits."
                        )

                        # Apply ignored hunks back to working tree
                        if ignored_mappings:
                            print(
                                f"\nApplying {len(ignored_mappings)} ignored hunks back to working tree..."
                            )
                            ignore_success = _apply_ignored_hunks(
                                ignored_mappings, git_ops
                            )
                            if ignore_success:
                                print(
                                    "✓ Ignored hunks have been restored to working tree"
                                )
                            else:
                                print(
                                    "⚠️  Some ignored hunks could not be restored - check working tree status"
                                )
                    else:
                        print("✗ Squash operation was aborted or failed.")
                else:
                    print("\nOperation cancelled")

    except GitAutoSquashError as e:
        # Our custom exceptions with user-friendly messages
        ErrorReporter.report_error(e)
        sys.exit(1)
    except KeyboardInterrupt:
        cancel_error = UserCancelledError("git-autosquash operation")
        ErrorReporter.report_error(cancel_error)
        sys.exit(130)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        # Git/system operation failures
        wrapped = handle_unexpected_error(
            e, "git operation", "Check git installation and repository state"
        )
        ErrorReporter.report_error(wrapped)
        sys.exit(1)
    except Exception as e:
        # Catch-all for unexpected errors
        wrapped = handle_unexpected_error(e, "git-autosquash execution")
        ErrorReporter.report_error(wrapped)
        sys.exit(1)


if __name__ == "__main__":
    main()
