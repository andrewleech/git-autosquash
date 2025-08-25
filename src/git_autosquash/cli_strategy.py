"""CLI commands for git-native strategy management and configuration."""

import argparse
import os
import sys

from git_autosquash.git_ops import GitOps
from git_autosquash.git_native_complete_handler import (
    GitNativeStrategyManager,
    create_git_native_handler,
)


def cmd_strategy_info(args: argparse.Namespace) -> int:
    """Display information about available git-native strategies.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        git_ops = GitOps()

        if not git_ops.is_git_repo():
            print("Error: Not in a git repository", file=sys.stderr)
            return 1

        handler = create_git_native_handler(git_ops)
        info = handler.get_strategy_info()

        print("Git-Autosquash Strategy Information")
        print("=" * 40)
        print(f"Current Strategy: {info['preferred_strategy']}")
        print(f"Worktree Available: {'✓' if info['worktree_available'] else '✗'}")
        print(f"Strategies Available: {', '.join(info['strategies_available'])}")
        print(f"Execution Order: {' → '.join(info['execution_order'])}")

        env_override = info.get("environment_override")
        if env_override:
            print(f"Environment Override: {env_override}")
        else:
            print("Environment Override: None")

        print("\nStrategy Descriptions:")
        print("  worktree - Complete isolation using git worktree (best)")
        print("  index    - Index manipulation with stash backup (good)")
        print("  legacy   - Manual patch application (fallback)")

        print("\nConfiguration:")
        print("  Set GIT_AUTOSQUASH_STRATEGY=worktree|index to override")
        print("  Default: Auto-detect based on git capabilities")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_strategy_test(args: argparse.Namespace) -> int:
    """Test strategy compatibility and performance.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        git_ops = GitOps()

        if not git_ops.is_git_repo():
            print("Error: Not in a git repository", file=sys.stderr)
            return 1

        strategy = args.strategy if hasattr(args, "strategy") else None

        print("Testing Git-Native Strategy Compatibility")
        print("=" * 45)

        # Test all strategies or specific one
        strategies_to_test = [strategy] if strategy else ["worktree", "index", "legacy"]

        for strat in strategies_to_test:
            print(f"\nTesting {strat} strategy:")

            # Test compatibility
            compatible = GitNativeStrategyManager.validate_strategy_compatibility(
                git_ops, strat
            )
            print(f"  Compatibility: {'✓' if compatible else '✗'}")

            if compatible:
                # Test basic functionality
                try:
                    handler = GitNativeStrategyManager.create_handler(
                        git_ops, strategy=strat
                    )
                    # Test with empty mappings (safe test)
                    result = handler.apply_ignored_hunks([])
                    print(f"  Basic Function: {'✓' if result else '✗'}")
                except Exception as e:
                    print(f"  Basic Function: ✗ ({e})")
            else:
                print("  Reason: Strategy not supported on this system")

        # Show recommendation
        recommended = GitNativeStrategyManager.get_recommended_strategy(git_ops)
        print(f"\nRecommended Strategy: {recommended}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_strategy_set(args: argparse.Namespace) -> int:
    """Set the preferred git-native strategy via environment.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for success)
    """
    try:
        strategy = args.strategy

        if strategy not in ["worktree", "index", "legacy", "auto"]:
            print(f"Error: Invalid strategy '{strategy}'", file=sys.stderr)
            print("Valid strategies: worktree, index, legacy, auto", file=sys.stderr)
            return 1

        if strategy == "auto":
            # Remove environment override to use auto-detection
            if "GIT_AUTOSQUASH_STRATEGY" in os.environ:
                print("Removing GIT_AUTOSQUASH_STRATEGY environment variable")
                print("Strategy will be auto-detected based on git capabilities")
                # Note: We can't actually remove it from the current process
                print("Unset GIT_AUTOSQUASH_STRATEGY in your shell to apply")
            else:
                print("No environment override set - already using auto-detection")
        else:
            print(f"To use {strategy} strategy, set environment variable:")
            print(f"  export GIT_AUTOSQUASH_STRATEGY={strategy}")
            print(
                "Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.) to persist"
            )

        # Test if the strategy is compatible
        git_ops = GitOps()
        if git_ops.is_git_repo() and strategy != "auto":
            compatible = GitNativeStrategyManager.validate_strategy_compatibility(
                git_ops, strategy
            )
            if not compatible:
                print(
                    f"\nWarning: {strategy} strategy may not be compatible with your git version"
                )

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def add_strategy_subcommands(subparsers):
    """Add strategy management subcommands to argument parser.

    Args:
        subparsers: Subparser object from main argument parser
    """
    # Strategy info command
    info_parser = subparsers.add_parser(
        "strategy-info", help="Show git-native strategy information"
    )
    info_parser.set_defaults(func=cmd_strategy_info)

    # Strategy test command
    test_parser = subparsers.add_parser(
        "strategy-test", help="Test strategy compatibility"
    )
    test_parser.add_argument(
        "--strategy",
        choices=["worktree", "index", "legacy"],
        help="Test specific strategy (default: test all)",
    )
    test_parser.set_defaults(func=cmd_strategy_test)

    # Strategy set command
    set_parser = subparsers.add_parser("strategy-set", help="Set preferred strategy")
    set_parser.add_argument(
        "strategy",
        choices=["worktree", "index", "legacy", "auto"],
        help="Strategy to use (auto = auto-detect)",
    )
    set_parser.set_defaults(func=cmd_strategy_set)


def main_strategy_cli() -> None:
    """Main entry point for strategy CLI when called directly."""
    parser = argparse.ArgumentParser(
        prog="git-autosquash-strategy",
        description="Manage git-autosquash native strategies",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    add_strategy_subcommands(subparsers)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    sys.exit(args.func(args))
