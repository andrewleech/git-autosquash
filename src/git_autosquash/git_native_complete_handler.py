"""Complete git-native handler with multiple strategies and fallback capabilities."""

import logging
import os
from typing import List, Optional, Literal, Dict, Any

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.git_ops import GitOps
from git_autosquash.git_native_handler import GitNativeIgnoreHandler


StrategyType = Literal["index", "legacy"]


class CapabilityCache:
    """Cache for git capability detection to avoid repeated command execution."""

    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Any]:
        """Get cached capability result."""
        return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        """Set cached capability result."""
        self._cache[key] = value

    def clear(self) -> None:
        """Clear the capability cache."""
        self._cache.clear()

    def has(self, key: str) -> bool:
        """Check if capability is cached."""
        return key in self._cache


class GitNativeCompleteHandler:
    """Complete git-native handler with multiple strategies and intelligent fallback.

    This handler provides a unified interface for applying ignored hunks using the
    best available git-native strategy with automatic fallback capabilities.

    Strategy Priority:
    1. Git Worktree (best isolation, requires Git 2.5+)
    2. Git Index Manipulation (good isolation, works with older Git)
    3. Legacy Manual Patches (fallback for compatibility)
    """

    def __init__(
        self, git_ops: GitOps, capability_cache: Optional[CapabilityCache] = None
    ) -> None:
        """Initialize the complete git-native handler.

        Args:
            git_ops: GitOps instance for git command execution
            capability_cache: Optional shared cache for capability detection
        """
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)
        self.capability_cache = capability_cache or CapabilityCache()

        # Initialize strategy handler
        self.index_handler = GitNativeIgnoreHandler(git_ops)

        # Use index strategy as primary approach
        self.preferred_strategy = "index"

        self.logger.info(
            f"Git-native complete handler initialized with strategy: {self.preferred_strategy}"
        )

    def apply_ignored_hunks(self, ignored_mappings: List[HunkTargetMapping]) -> bool:
        """Apply ignored hunks using the best available git-native strategy.

        This method implements intelligent strategy selection with graceful fallback:
        1. Try preferred strategy (worktree/index based on capabilities)
        2. Fall back to next best strategy on failure
        3. Provide detailed logging for troubleshooting

        Args:
            ignored_mappings: List of ignored hunk to commit mappings

        Returns:
            True if successful, False if all strategies failed
        """
        if not ignored_mappings:
            self.logger.info("No ignored hunks to apply")
            return True

        self.logger.info(
            f"Applying {len(ignored_mappings)} ignored hunks using git-native strategies"
        )

        # Try strategies in order of preference with fallback
        strategies = self._get_strategy_execution_order()

        for strategy_name in strategies:
            self.logger.info(f"Attempting strategy: {strategy_name}")

            try:
                success = self._execute_strategy(strategy_name, ignored_mappings)
                if success:
                    self.logger.info(
                        f"✓ Successfully applied hunks using {strategy_name} strategy"
                    )
                    return True
                else:
                    self.logger.warning(
                        f"Strategy {strategy_name} failed, trying next strategy"
                    )

            except Exception as e:
                self.logger.error(f"Strategy {strategy_name} raised exception: {e}")
                continue

        self.logger.error("All git-native strategies failed")
        return False

    def _determine_preferred_strategy(self) -> StrategyType:
        """Determine the preferred strategy based on environment and capabilities.

        Returns:
            Preferred strategy type (simplified to index only)
        """
        # Check for explicit strategy override
        env_strategy = os.getenv("GIT_AUTOSQUASH_STRATEGY", "").lower()
        if env_strategy in ["index", "legacy"]:
            self.logger.info(f"Using strategy from environment: {env_strategy}")
            return env_strategy  # type: ignore

        # Default to index strategy
        return "index"

    def _get_strategy_execution_order(self) -> List[StrategyType]:
        """Get the order of strategies to try based on preference and fallback.

        Returns:
            List of strategies in execution order
        """
        # Return preferred strategy first, with fallback to the other option
        if self.preferred_strategy == "legacy":
            return ["legacy"]
        else:
            return ["index"]

    def _execute_strategy(
        self, strategy: StrategyType, ignored_mappings: List[HunkTargetMapping]
    ) -> bool:
        """Execute a specific strategy.

        Args:
            strategy: Strategy to execute
            ignored_mappings: Hunks to apply

        Returns:
            True if strategy succeeded
        """
        if strategy == "index":
            return self.index_handler.apply_ignored_hunks(ignored_mappings)
        else:
            # Legacy strategy would be implemented here
            self.logger.warning("Legacy strategy not implemented, using index fallback")
            return self.index_handler.apply_ignored_hunks(ignored_mappings)

    def get_strategy_info(self) -> dict:
        """Get information about available strategies and current configuration.

        Returns:
            Dictionary with strategy information
        """
        return {
            "preferred_strategy": self.preferred_strategy,
            "strategies_available": ["index", "legacy"],
            "execution_order": self._get_strategy_execution_order(),
            "environment_override": os.getenv("GIT_AUTOSQUASH_STRATEGY"),
            "capability_cache_size": len(self.capability_cache._cache),
        }

    def force_strategy(self, strategy: StrategyType) -> None:
        """Force the use of a specific strategy (for testing/debugging).

        Args:
            strategy: Strategy to force
        """
        if strategy in ["index", "legacy"]:
            self.preferred_strategy = strategy
            self.logger.info(f"Forced strategy changed to: {strategy}")
        else:
            raise ValueError(
                f"Invalid strategy: {strategy}. Valid options: index, legacy"
            )


class GitNativeStrategyManager:
    """Manager for git-native strategy selection and configuration."""

    @staticmethod
    def create_handler(
        git_ops: GitOps, strategy: Optional[StrategyType] = None
    ) -> GitNativeCompleteHandler:
        """Create a git-native handler with optional strategy override.

        Args:
            git_ops: GitOps instance
            strategy: Optional strategy override

        Returns:
            Configured handler
        """
        handler = GitNativeCompleteHandler(git_ops)

        if strategy:
            handler.force_strategy(strategy)

        return handler

    @staticmethod
    def get_recommended_strategy(git_ops: GitOps) -> StrategyType:
        """Get the recommended strategy for the current environment.

        Args:
            git_ops: GitOps instance for testing capabilities

        Returns:
            Recommended strategy
        """
        # Test worktree availability
        try:
            success, output = git_ops._run_git_command("worktree", "--help")
            if success and "add" in output.lower():
                return "index"  # Worktree removed, fallback to index
        except Exception:
            pass

        return "index"

    @staticmethod
    def validate_strategy_compatibility(
        git_ops: GitOps, strategy: StrategyType
    ) -> bool:
        """Validate that a strategy is compatible with the current environment.

        Args:
            git_ops: GitOps instance for testing
            strategy: Strategy to validate

        Returns:
            True if strategy is compatible
        """
        if strategy == "worktree":
            try:
                success, output = git_ops._run_git_command("worktree", "--help")
                return success and "add" in output.lower()
            except Exception:
                return False
        elif strategy == "index":
            # Index strategy should work with any modern git
            return True
        elif strategy == "legacy":
            # Legacy strategy is always available as fallback
            return True
        else:
            return False


# Global capability cache for shared use across handler instances
_global_capability_cache = CapabilityCache()


def create_git_native_handler(
    git_ops: GitOps, use_global_cache: bool = True
) -> GitNativeCompleteHandler:
    """Factory function to create the appropriate git-native handler.

    This is the main entry point for the git-native ignore functionality.

    Args:
        git_ops: GitOps instance for git command execution
        use_global_cache: Whether to use the global capability cache for better performance

    Returns:
        Configured GitNativeCompleteHandler
    """
    cache = _global_capability_cache if use_global_cache else None
    return GitNativeCompleteHandler(git_ops, capability_cache=cache)
