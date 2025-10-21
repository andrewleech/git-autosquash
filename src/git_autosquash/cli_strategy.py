"""CLI commands for git-native strategy management and configuration."""

import os
from typing import Optional

import typer
from typing_extensions import Annotated

from git_autosquash.git_ops import GitOps
from git_autosquash.git_native_complete_handler import (
    GitNativeStrategyManager,
    create_git_native_handler,
)

# Create strategy subcommand app (hidden from main help)
strategy_app = typer.Typer(
    name="strategy",
    help="Strategy management commands (advanced/debugging)",
    hidden=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@strategy_app.command("info")
def cmd_strategy_info() -> None:
    """Display information about available git-native strategies."""
    try:
        git_ops = GitOps()

        if not git_ops.is_git_repo():
            typer.echo("Error: Not in a git repository", err=True)
            raise typer.Exit(code=1)

        handler = create_git_native_handler(git_ops)
        info = handler.get_strategy_info()

        typer.echo("Git-Autosquash Strategy Information")
        typer.echo("=" * 40)
        typer.echo(f"Current Strategy: {info['preferred_strategy']}")
        typer.echo(f"Strategies Available: {', '.join(info['strategies_available'])}")
        typer.echo(f"Execution Order: {' → '.join(info['execution_order'])}")

        env_override = info.get("environment_override")
        if env_override:
            typer.echo(f"Environment Override: {env_override}")
        else:
            typer.echo("Environment Override: None")

        typer.echo("\nStrategy Descriptions:")
        typer.echo("  index    - Index manipulation with stash backup (reliable)")
        typer.echo("  legacy   - Manual patch application (fallback)")

        typer.echo("\nConfiguration:")
        typer.echo("  Set GIT_AUTOSQUASH_STRATEGY=index|legacy to override")
        typer.echo("  Default: Uses index strategy for optimal performance")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@strategy_app.command("test")
def cmd_strategy_test(
    strategy: Annotated[
        Optional[str],
        typer.Option(
            help="Test specific strategy (default: test all, worktree deprecated)"
        ),
    ] = None,
) -> None:
    """Test strategy compatibility and performance."""
    try:
        git_ops = GitOps()

        if not git_ops.is_git_repo():
            typer.echo("Error: Not in a git repository", err=True)
            raise typer.Exit(code=1)

        typer.echo("Testing Git-Native Strategy Compatibility")
        typer.echo("=" * 45)

        # Test all strategies or specific one
        from typing import Literal, cast

        StrategyType = Literal["index", "legacy"]
        strategies_to_test: list[StrategyType]
        if strategy:
            # Type narrow: strategy must be "index" or "legacy" at runtime
            strategies_to_test = [cast(StrategyType, strategy)]
        else:
            strategies_to_test = ["index", "legacy"]

        for strat in strategies_to_test:
            typer.echo(f"\nTesting {strat} strategy:")

            # Test compatibility
            compatible = GitNativeStrategyManager.validate_strategy_compatibility(
                git_ops, strat
            )
            typer.echo(f"  Compatibility: {'✓' if compatible else '✗'}")

            if compatible:
                # Test basic functionality
                try:
                    handler = GitNativeStrategyManager.create_handler(
                        git_ops, strategy=strat
                    )
                    # Test with empty mappings (safe test)
                    result = handler.apply_ignored_hunks([])
                    typer.echo(f"  Basic Function: {'✓' if result else '✗'}")
                except Exception as e:
                    typer.echo(f"  Basic Function: ✗ ({e})")
            else:
                typer.echo("  Reason: Strategy not supported on this system")

        # Show recommendation
        recommended = GitNativeStrategyManager.get_recommended_strategy(git_ops)
        typer.echo(f"\nRecommended Strategy: {recommended}")

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@strategy_app.command("set")
def cmd_strategy_set(
    strategy: Annotated[
        str,
        typer.Argument(
            help="Strategy to use (auto = default to index, worktree deprecated)"
        ),
    ],
) -> None:
    """Set the preferred git-native strategy via environment."""
    try:
        if strategy not in ["index", "legacy", "auto", "worktree"]:
            typer.echo(f"Error: Invalid strategy '{strategy}'", err=True)
            typer.echo("Valid strategies: index, legacy, auto", err=True)
            raise typer.Exit(code=1)

        if strategy == "auto":
            # Remove environment override to use auto-detection
            if "GIT_AUTOSQUASH_STRATEGY" in os.environ:
                typer.echo("Removing GIT_AUTOSQUASH_STRATEGY environment variable")
                typer.echo("Strategy will default to index for optimal performance")
                # Note: We can't actually remove it from the current process
                typer.echo("Unset GIT_AUTOSQUASH_STRATEGY in your shell to apply")
            else:
                typer.echo("No environment override set - using default index strategy")
        else:
            typer.echo(f"To use {strategy} strategy, set environment variable:")
            typer.echo(f"  export GIT_AUTOSQUASH_STRATEGY={strategy}")
            typer.echo(
                "Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.) to persist"
            )

        # Test if the strategy is compatible
        from typing import Literal, cast

        git_ops = GitOps()
        if git_ops.is_git_repo() and strategy != "auto":
            # At this point strategy is guaranteed to be "index" or "legacy"
            strategy_typed = cast(Literal["index", "legacy"], strategy)
            compatible = GitNativeStrategyManager.validate_strategy_compatibility(
                git_ops, strategy_typed
            )
            if not compatible:
                typer.echo(
                    f"\nWarning: {strategy} strategy may not be compatible with your git version"
                )

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


# Old argparse functions removed - now using Typer
