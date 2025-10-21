"""CLI entry point for git-autosquash."""

import subprocess
import sys
from typing import TYPE_CHECKING, List, Optional

import typer
from typing_extensions import Annotated

from git_autosquash.cli_strategy import strategy_app
from git_autosquash.exceptions import (
    ErrorReporter,
    GitAutoSquashError,
    RepositoryStateError,
    UserCancelledError,
    handle_unexpected_error,
)
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.hunk_target_resolver import HunkTargetMapping, HunkTargetResolver
from git_autosquash.rebase_manager import RebaseConflictError, RebaseManager
from git_autosquash.source_normalizer import SourceNormalizer
from git_autosquash.squash_context import SquashContext
from git_autosquash.validation import ProcessingValidator

if TYPE_CHECKING:
    from git_autosquash.hunk_commit_splitter import HunkCommitSplitter


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


def _execute_rebase(
    approved_mappings,
    ignored_mappings,
    git_ops,
    merge_base,
    resolver,
    context,
    blame_ref="HEAD",
) -> bool:
    """Execute the interactive rebase to apply approved mappings.

    Args:
        approved_mappings: List of approved hunk to commit mappings
        ignored_mappings: List of ignored hunk to commit mappings
        git_ops: GitOps instance
        merge_base: Merge base commit hash
        resolver: HunkTargetResolver for getting commit summaries
        context: SquashContext for centralized logic
        blame_ref: Git ref to use for blame operations (default: HEAD)

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
        success = rebase_manager.execute_squash(
            approved_mappings, ignored_mappings, context=context
        )

        if success:
            return True
        else:
            print("Rebase operation was cancelled by user")
            return False

    except RebaseConflictError as e:
        print("\n⚠️ Rebase conflicts detected:")
        for file_path in e.conflicted_files:
            print(f"  {file_path}")

        # Check if rebase is actually still in progress
        try:
            status_result = git_ops.run_git_command(["status", "--porcelain"])
            rebase_in_progress = rebase_manager.is_rebase_in_progress()
            print(f"DEBUG: Rebase in progress: {rebase_in_progress}")
            print(f"DEBUG: Working tree status: {status_result.stdout.strip()}")
        except Exception as debug_e:
            print(f"DEBUG: Failed to check rebase status: {debug_e}")

        if rebase_manager.is_rebase_in_progress():
            print("\nTo resolve conflicts:")
            print("1. Edit the conflicted files to resolve conflicts")
            print("2. Stage the resolved files: git add <files>")
            print("3. Continue the rebase: git rebase --continue")
            print("4. Or abort the rebase: git rebase --abort")
        else:
            print("\nRebase was automatically aborted due to conflicts.")
            print("Repository has been restored to its original state.")
            print(
                "This prevents manual conflict resolution but keeps the repository clean."
            )

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


def _get_user_choice_for_uncommitted_changes() -> str:
    """Get user choice for handling uncommitted changes.

    Returns:
        User's choice: 'continue' or other
    """
    print("Choose an option:")
    print("  c) Continue (changes will be temporarily stashed)")
    print("  q) Quit")

    while True:
        choice = input("Your choice [c/q]: ").lower().strip()
        if choice == "c":
            return "continue"
        elif choice == "q":
            return "quit"
        else:
            print("Please enter 'c' to continue or 'q' to quit")


def _display_automatic_mappings(mappings: List[HunkTargetMapping]) -> None:
    """Display automatic mappings to the user.

    Args:
        mappings: List of automatic mappings to display
    """
    print(f"\nFound {len(mappings)} hunks with automatic blame-identified targets:")
    for mapping in mappings:
        commit_summary = (
            mapping.target_commit[:8] if mapping.target_commit else "unknown"
        )
        print(f"  → {mapping.hunk.file_path}: {commit_summary}")
    print()


# Create Typer app
app = typer.Typer(
    name="git-autosquash",
    help="Automatically squash changes back into historical commits",
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# Add strategy subcommands
app.add_typer(strategy_app)


def complete_git_branches(incomplete: str) -> List[str]:
    """Auto-complete git branch names for --base option.

    Args:
        incomplete: Partial branch name typed by user

    Returns:
        List of matching branch names
    """
    try:
        result = subprocess.run(
            ["git", "branch", "-a", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            branches = [
                b.strip() for b in result.stdout.strip().split("\n") if b.strip()
            ]
            return [b for b in branches if b.startswith(incomplete)]
    except Exception:
        pass
    return []


def complete_source_option(incomplete: str) -> List[str]:
    """Auto-complete source options.

    Args:
        incomplete: Partial source value typed by user

    Returns:
        List of matching source options
    """
    options = ["auto", "working-tree", "index", "head"]
    return [o for o in options if o.startswith(incomplete)]


# Old argparse setup functions removed - now using Typer (see app definition above)


def validate_git_environment(git_ops: GitOps) -> str:
    """Validate git environment and return current branch.

    Args:
        git_ops: GitOps instance

    Returns:
        Current branch name

    Raises:
        SystemExit: If validation fails
    """
    # Check git availability
    if not git_ops.is_git_available():
        error = RepositoryStateError(
            "Git is not installed or not available in PATH",
            recovery_suggestion="Please install git and ensure it's available in your PATH environment variable",
        )
        ErrorReporter.report_error(error)
        sys.exit(1)

    # Validate git repository
    if not git_ops.is_git_repo():
        error = RepositoryStateError(
            "Not in a git repository",
            recovery_suggestion="Please run this command from within a git repository directory",
        )
        ErrorReporter.report_error(error)
        sys.exit(1)

    # Get current branch
    current_branch = git_ops.get_current_branch()
    if not current_branch:
        error = RepositoryStateError(
            "Not on a branch (detached HEAD)",
            recovery_suggestion="Please checkout a branch before using git-autosquash",
        )
        ErrorReporter.report_error(error)
        sys.exit(1)

    return current_branch


def get_merge_base(
    git_ops: GitOps, current_branch: str, base_ref: Optional[str] = None
) -> str:
    """Get merge base with main branch or specified base.

    Args:
        git_ops: GitOps instance
        current_branch: Current branch name
        base_ref: Optional base reference (branch/commit) to use instead of main/master

    Returns:
        Merge base commit hash

    Raises:
        SystemExit: If merge base not found or invalid
    """
    if base_ref:
        # User specified a base, validate it
        is_valid, error_msg, resolved_hash = git_ops.validate_merge_base(base_ref)
        if not is_valid:
            # Get tracking branch info for helpful error message
            result = git_ops.run_git_command(["branch", "-vv", current_branch])
            tracking_info = ""
            if result.returncode == 0 and result.stdout.strip():
                tracking_info = (
                    "\n\nYour current branch tracking info:\n" + result.stdout.strip()
                )

            error = RepositoryStateError(
                f"Invalid base reference: {error_msg}",
                recovery_suggestion=f"Please provide a valid base commit or branch.\n"
                f"Find your tracking branch with: git branch -vv{tracking_info}",
            )
            ErrorReporter.report_error(error)
            sys.exit(1)

        # Validation passed, resolved_hash is guaranteed to be a str
        assert resolved_hash is not None, (
            "validate_merge_base should return hash if valid"
        )
        return resolved_hash

    # Try automatic detection with main/master
    merge_base = git_ops.get_merge_base_with_main(current_branch)
    if not merge_base:
        # Get tracking branch info for helpful error message
        result = git_ops.run_git_command(["branch", "-vv", current_branch])
        tracking_info = ""
        if result.returncode == 0 and result.stdout.strip():
            # Parse tracking branch from output like: * branch_name hash [remote/branch] message
            import re

            match = re.search(r"\[([^\]]+)\]", result.stdout)
            if match:
                tracking_branch = (
                    match.group(1).split(":")[0].strip()
                )  # Remove ahead/behind info
                tracking_info = f"\n\nYour branch appears to track '{tracking_branch}'.\nTry using: git autosquash --base {tracking_branch}"

        error = RepositoryStateError(
            "Could not find merge base with main/master branch",
            recovery_suggestion=f"Your branch '{current_branch}' does not appear to be based on 'main' or 'master'.\n"
            f"Please specify the base branch explicitly using --base:\n\n"
            f"  git autosquash --base <branch-name>\n\n"
            f"Find your tracking branch with: git branch -vv{tracking_info}",
        )
        ErrorReporter.report_error(error)
        sys.exit(1)

    return merge_base


def check_repository_state(
    git_ops: GitOps, merge_base: str, auto_accept: bool = False
) -> None:
    """Check repository state and handle uncommitted changes.

    Args:
        git_ops: GitOps instance
        merge_base: Merge base commit hash
        auto_accept: If True, automatically continue without user prompt

    Raises:
        SystemExit: If repository state is invalid
    """
    # Check for commits to work with
    if not git_ops.has_commits_since_merge_base(merge_base):
        error = RepositoryStateError(
            "No commits to process since merge base",
            recovery_suggestion="Make some commits on your branch before running git-autosquash",
        )
        ErrorReporter.report_error(error)
        sys.exit(1)

    # Check working tree status
    status = git_ops.get_working_tree_status()

    # Only warn about stashing when we actually need to stash (both staged and unstaged)
    if status.get("has_staged", False) and status.get("has_unstaged", False):
        print(
            "⚠️  Working tree has both staged and unstaged changes. Unstaged changes will be temporarily stashed while processing staged changes."
        )
        if auto_accept:
            print(
                "✓ Auto-accepting mixed changes (unstaged will be temporarily stashed)"
            )
        else:
            choice = _get_user_choice_for_uncommitted_changes()
            if choice != "continue":
                print("Operation cancelled.")
                sys.exit(0)


def process_hunks_and_mappings(
    git_ops: GitOps,
    merge_base: str,
    line_by_line: bool,
    source: str,
    blame_ref: str,
    context: SquashContext,
) -> tuple[
    List[HunkTargetMapping],
    List[HunkTargetMapping],
    str,
    bool,
    Optional["HunkCommitSplitter"],
]:
    """Process hunks and create target mappings with validation.

    Args:
        git_ops: GitOps instance
        merge_base: Merge base commit hash
        line_by_line: Whether to use line-by-line splitting
        source: What to process (working-tree, index, head, commit SHA, or auto)
        blame_ref: Git ref to use for blame operations
        context: SquashContext for centralized blame/HEAD exclusion logic

    Returns:
        Tuple of (automatic_mappings, fallback_mappings, starting_commit, temp_commit_created, splitter)

    Raises:
        SystemExit: If no hunks found
    """
    from git_autosquash.hunk_commit_splitter import HunkCommitSplitter

    # Phase 1: Normalize source to commit
    normalizer = SourceNormalizer(git_ops)
    starting_commit = normalizer.normalize_to_commit(source)
    print(f"Processing from commit: {starting_commit[:8]}")

    # Phase 2: Split source commit into per-hunk commits (if using --source)
    # This enables reliable 3-way merge during cherry-pick
    splitter: Optional[HunkCommitSplitter] = None
    split_commits: List[str] = []
    if context.source_commit:
        print(
            "DEBUG: Splitting source commit into per-hunk commits for reliable 3-way merge"
        )
        splitter = HunkCommitSplitter(git_ops)
        try:
            split_commits, hunks = splitter.split_commit_into_hunks(starting_commit)
            print(f"DEBUG: Created {len(split_commits)} split commits")
        except Exception as e:
            print(f"DEBUG: Failed to split commit: {e}")
            # Fall back to normal patch-based approach
            splitter = None
            split_commits = []

    # Phase 3: Parse hunks (use hunks from splitter if available)
    if not split_commits:
        hunk_parser = HunkParser(git_ops)
        hunks = hunk_parser.get_diff_hunks(line_by_line, from_commit=starting_commit)

    if not hunks:
        print("No hunks found to process.")
        normalizer.cleanup_temp_commit()
        if splitter:
            splitter.cleanup()
        sys.exit(0)

    # Phase 4: Pre-flight validation
    validator = ProcessingValidator(git_ops)
    validator.validate_hunk_count(starting_commit, hunks)

    # Phase 5: Resolve target commits for hunks with SquashContext
    resolver = HunkTargetResolver(git_ops, merge_base, context, blame_ref=blame_ref)
    mappings = resolver.resolve_targets(hunks)

    # Attach split commit SHAs to mappings (for cherry-pick)
    if split_commits:
        for i, mapping in enumerate(mappings):
            if i < len(split_commits):
                mapping.source_commit_sha = split_commits[i]
                print(
                    f"DEBUG: Mapped hunk {i + 1} to split commit {split_commits[i][:8]}"
                )

    # Separate automatic mappings from those requiring user input
    automatic_mappings = [m for m in mappings if not m.needs_user_selection]
    fallback_mappings = [m for m in mappings if m.needs_user_selection]

    return (
        automatic_mappings,
        fallback_mappings,
        starting_commit,
        normalizer.temp_commit_created,
        splitter,
    )


def handle_automatic_mappings(
    automatic_mappings: List[HunkTargetMapping], auto_accept: bool, git_ops: GitOps
) -> tuple[List[HunkTargetMapping], List[HunkTargetMapping]]:
    """Handle automatic mappings and return approved/ignored lists.

    Args:
        automatic_mappings: List of automatic mappings
        auto_accept: Whether to auto-accept all mappings

    Returns:
        Tuple of (approved_mappings, ignored_mappings)
    """
    if not automatic_mappings:
        return [], []

    if auto_accept:
        print(
            f"\n✓ Auto-accepting {len(automatic_mappings)} hunks with blame-identified targets"
        )
        for mapping in automatic_mappings:
            commit_summary = (
                mapping.target_commit[:8] if mapping.target_commit else "unknown"
            )
            print(f"  → {mapping.hunk.file_path}: {commit_summary}")
        print()
        return automatic_mappings, []
    else:
        # Show automatic mappings and ask for confirmation
        _display_automatic_mappings(automatic_mappings)
        # In non-auto-accept mode, return mappings for normal rebase processing
        # instead of incorrectly applying them to working tree
        return automatic_mappings, []


def run_interactive_ui(
    fallback_mappings: List[HunkTargetMapping],
    git_ops: GitOps,
    merge_base: str,
    context,
    blame_ref: str = "HEAD",
) -> bool:
    """Run the interactive TUI for user selections.

    Args:
        fallback_mappings: Mappings requiring user input
        git_ops: GitOps instance
        merge_base: Merge base commit hash
        context: SquashContext for centralized logic
        blame_ref: Git ref to use for blame operations (default: HEAD)

    Returns:
        True if user approved changes, False if cancelled
    """
    try:
        from git_autosquash.commit_history_analyzer import CommitHistoryAnalyzer
        from git_autosquash.tui.modern_app import ModernAutoSquashApp

        commit_analyzer = CommitHistoryAnalyzer(git_ops, merge_base)

        # Launch the modern TUI app
        app = ModernAutoSquashApp(fallback_mappings, commit_analyzer)
        approved = app.run()

        if approved:
            # Use the same rebase execution path as auto-accept mode for consistency
            result = _execute_rebase(
                app.approved_mappings,
                app.ignored_mappings,
                git_ops,
                merge_base,
                HunkTargetResolver(git_ops, merge_base, context, blame_ref=blame_ref),
                context,
                blame_ref=blame_ref,
            )
            if result:
                print("✓ Successfully applied selected hunks")
                return True
            else:
                print("✗ Failed to apply some hunks")
                return False
        else:
            print("Operation cancelled by user.")
            return False

    except Exception as e:
        if "Cancelled by user" in str(e):
            ErrorReporter.report_error(UserCancelledError("TUI cancelled by user"))
        else:
            error = handle_unexpected_error(e, "TUI execution")
            ErrorReporter.report_error(error)
        return False


def _get_user_friendly_reason(targeting_method) -> str:
    """Convert targeting method enum to user-friendly reason string."""
    from git_autosquash.hunk_target_resolver import TargetingMethod

    reason_map = {
        TargetingMethod.FALLBACK_NEW_FILE: "New file with no git history to analyze",
        TargetingMethod.FALLBACK_EXISTING_FILE: "No suitable target commits found in blame analysis",
        TargetingMethod.FALLBACK_CONSISTENCY: "Requires manual selection (consistency fallback)",
        TargetingMethod.BLAME_MATCH: "Direct blame match (should be auto-accepted)",
        TargetingMethod.CONTEXTUAL_BLAME_MATCH: "Contextual blame match (should be auto-accepted)",
    }

    return reason_map.get(
        targeting_method, f"Unknown targeting method: {targeting_method}"
    )


def _show_dry_run_output(
    automatic_mappings: List[HunkTargetMapping],
    fallback_mappings: List[HunkTargetMapping],
    git_ops: GitOps,
) -> None:
    """Show what would be done in dry run mode without making changes."""
    print("\n=== DRY RUN MODE ===")
    print("Showing what would be done without making any changes\n")

    if automatic_mappings:
        print(
            f"✓ Would auto-accept {len(automatic_mappings)} hunks with blame-identified targets:"
        )
        for mapping in automatic_mappings:
            commit_hash = (
                mapping.target_commit[:8] if mapping.target_commit else "unknown"
            )
            try:
                # Get commit subject for more context
                if mapping.target_commit:
                    result = git_ops.run_git_command(
                        ["log", "-1", "--format=%s", mapping.target_commit]
                    )
                    commit_subject = result.stdout.strip()[:50]
                    if len(result.stdout.strip()) > 50:
                        commit_subject += "..."
                else:
                    commit_subject = "commit subject unavailable"
            except Exception:
                commit_subject = "commit subject unavailable"

            # Use the affected_lines property from DiffHunk
            lines_range = f"{mapping.hunk.new_start}-{mapping.hunk.new_start + mapping.hunk.new_count - 1}"
            print(f"  → {mapping.hunk.file_path}:{lines_range}")
            print(f"    Target: {commit_hash} ({commit_subject})")
        print()

    if fallback_mappings:
        print(
            f"⚠ Would ignore {len(fallback_mappings)} hunks requiring manual target selection:"
        )
        for mapping in fallback_mappings:
            # Convert targeting method to user-friendly reason
            reason = _get_user_friendly_reason(mapping.targeting_method)
            lines_range = f"{mapping.hunk.new_start}-{mapping.hunk.new_start + mapping.hunk.new_count - 1}"
            print(f"  → {mapping.hunk.file_path}:{lines_range}")
            print(f"    Reason: {reason}")
        print()

    if not automatic_mappings and not fallback_mappings:
        print("No hunks found to process.")
        return

    # Summary
    total_hunks = len(automatic_mappings) + len(fallback_mappings)
    print("=== SUMMARY ===")
    print(f"Total hunks analyzed: {total_hunks}")
    print(f"Would be squashed: {len(automatic_mappings)}")
    print(f"Would be ignored: {len(fallback_mappings)}")

    if automatic_mappings:
        print("\nTo actually perform these changes, run:")
        print("git autosquash --auto-accept")


@app.callback(invoke_without_command=True)
def run(
    ctx: typer.Context,
    line_by_line: Annotated[
        bool,
        typer.Option(
            "--line-by-line",
            help="Use line-by-line hunk splitting instead of default git hunks",
        ),
    ] = False,
    auto_accept: Annotated[
        bool,
        typer.Option(
            "--auto-accept",
            help="Automatically accept all hunks with blame-identified targets, bypass TUI",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be done without making changes (requires --auto-accept)",
        ),
    ] = False,
    source: Annotated[
        str,
        typer.Option(
            help="Specify what to process: 'auto' (detect based on tree status), "
            "'working-tree', 'index', 'head', or a commit SHA. "
            "When 'head' or a commit SHA, git blame starts on <commit>~1",
            autocompletion=complete_source_option,
        ),
    ] = "auto",
    base: Annotated[
        Optional[str],
        typer.Option(
            help="Specify the base commit/branch for the merge-base. "
            "Use this when working on feature branches that are not based on main/master. "
            "Example: --base andrewleech/usbd_net or --base origin/develop",
            autocompletion=complete_git_branches,
        ),
    ] = None,
) -> None:
    """Automatically squash changes back into historical commits."""
    # If a subcommand is being invoked, skip the main logic
    if ctx.invoked_subcommand is not None:
        return

    try:
        # Validate argument combinations
        if dry_run and not auto_accept:
            typer.echo("Error: --dry-run requires --auto-accept", err=True)
            raise typer.Exit(code=1)

        # Phase 2: Initialize git operations and validate environment
        git_ops = GitOps()
        current_branch = validate_git_environment(git_ops)
        merge_base = get_merge_base(git_ops, current_branch, base)
        check_repository_state(git_ops, merge_base, auto_accept)

        # Save original HEAD for validation (before any processing)
        original_head_result = git_ops.run_git_command(["rev-parse", "HEAD"])
        original_head = (
            original_head_result.stdout.strip()
            if original_head_result.returncode == 0
            else None
        )

        # Create SquashContext from --source argument
        context = SquashContext.from_source(source, git_ops)
        blame_ref = context.blame_ref

        # Validate context
        validation_errors = context.validate(git_ops)
        if validation_errors:
            typer.echo("Error: Invalid context configuration:", err=True)
            for error in validation_errors:
                typer.echo(f"  • {error}", err=True)
            raise typer.Exit(code=1)

        # Phase 3: Process hunks and create mappings
        (
            automatic_mappings,
            fallback_mappings,
            starting_commit,
            temp_commit_created,
            splitter,
        ) = process_hunks_and_mappings(
            git_ops, merge_base, line_by_line, source, blame_ref, context
        )

        # Store normalizer for cleanup
        normalizer = SourceNormalizer(git_ops)
        normalizer.starting_commit = starting_commit
        normalizer.temp_commit_created = temp_commit_created

        try:
            print(f"Found target commits for {len(automatic_mappings)} hunks")
            if fallback_mappings:
                print(
                    f"Found {len(fallback_mappings)} hunks requiring manual target selection"
                )

            # Phase 4: Handle user interaction
            success = False

            if auto_accept:
                if dry_run:
                    # Dry run mode: show what would be done without making changes
                    _show_dry_run_output(automatic_mappings, fallback_mappings, git_ops)
                    success = True
                else:
                    # Auto-accept mode: process only automatic mappings
                    approved_mappings, ignored_mappings = handle_automatic_mappings(
                        automatic_mappings, auto_accept=True, git_ops=git_ops
                    )

                    # Add fallback mappings to ignored list (they can't be auto-accepted)
                    # These will be preserved in the source commit if using --source
                    ignored_mappings.extend(fallback_mappings)

                    if approved_mappings or ignored_mappings:
                        success = _execute_rebase(
                            approved_mappings,
                            ignored_mappings,
                            git_ops,
                            merge_base,
                            HunkTargetResolver(
                                git_ops, merge_base, context, blame_ref=blame_ref
                            ),
                            context,
                            blame_ref=blame_ref,
                        )
                    else:
                        success = True  # No rebase needed

            else:
                # Interactive mode: combine all mappings for user review
                all_mappings = automatic_mappings + fallback_mappings

                if all_mappings:
                    success = run_interactive_ui(
                        all_mappings,
                        git_ops,
                        merge_base,
                        context,
                        blame_ref=blame_ref,
                    )
                else:
                    print("No hunks found to process.")
                    success = True

            # Phase 5: Post-flight validation
            if success and not dry_run:
                validator = ProcessingValidator(git_ops)
                # Use original HEAD for validation if available, otherwise use starting_commit
                # This handles cases where --source points to a historical commit (not HEAD)
                validation_base = original_head if original_head else starting_commit
                validator.validate_processing(
                    validation_base, description="squash operation"
                )
                print("[+] Validation passed - no corruption detected")

            # Phase 6: Report results
            if success:
                if dry_run:
                    print("\n✓ Dry run completed successfully!")
                else:
                    print("✓ Operation completed successfully!")
            else:
                print("✗ Operation failed or was cancelled.")
                raise typer.Exit(code=1)

        finally:
            # Always cleanup temp commit and split commits
            normalizer.cleanup_temp_commit()
            if splitter:
                splitter.cleanup()

    except GitAutoSquashError as e:
        ErrorReporter.report_error(e)
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        cancel_error = UserCancelledError("git-autosquash operation")
        ErrorReporter.report_error(cancel_error)
        raise typer.Exit(code=130)
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        wrapped = handle_unexpected_error(
            e, "git operation", "Check git installation and repository state"
        )
        ErrorReporter.report_error(wrapped)
        raise typer.Exit(code=1)
    except Exception as e:
        # Check if it's a validation error
        from git_autosquash.validation import ValidationError

        if isinstance(e, ValidationError):
            typer.echo(f"\n✗ VALIDATION FAILED: {e}", err=True)
            typer.echo(
                "This indicates potential data corruption during processing.",
                err=True,
            )
            raise typer.Exit(code=1)

        wrapped = handle_unexpected_error(e, "git-autosquash execution")
        ErrorReporter.report_error(wrapped)
        raise typer.Exit(code=1)


def main() -> None:
    """Entry point wrapper for console_scripts."""
    app()


if __name__ == "__main__":
    main()
