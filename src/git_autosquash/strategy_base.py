"""Abstract base class for CLI execution strategies."""

from abc import ABC, abstractmethod
from typing import List, Optional
import logging

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.git_ops import GitOps


class CliStrategy(ABC):
    """Abstract base class for CLI execution strategies.

    This defines the interface that all strategy implementations must follow,
    enabling polymorphic strategy selection and consistent error handling.
    """

    def __init__(self, git_ops: GitOps) -> None:
        """Initialize the strategy with git operations.

        Args:
            git_ops: GitOps instance for git command execution
        """
        self.git_ops = git_ops
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Get the name of this strategy for logging and identification."""
        pass

    @property
    @abstractmethod
    def requires_worktree_support(self) -> bool:
        """Whether this strategy requires git worktree support."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this strategy is available in the current environment.

        Returns:
            True if strategy can be used
        """
        pass

    @abstractmethod
    def apply_ignored_hunks(self, ignored_mappings: List[HunkTargetMapping]) -> bool:
        """Apply ignored hunks using this strategy.

        Args:
            ignored_mappings: List of ignored hunk to commit mappings

        Returns:
            True if successful, False otherwise
        """
        pass

    def get_strategy_info(self) -> dict:
        """Get information about this strategy.

        Returns:
            Dictionary with strategy information
        """
        return {
            "name": self.strategy_name,
            "available": self.is_available(),
            "requires_worktree": self.requires_worktree_support,
        }


class StrategyRegistry:
    """Registry for managing available CLI strategies."""

    def __init__(self) -> None:
        self._strategies: List[CliStrategy] = []
        self._capability_cache: dict = {}

    def register_strategy(self, strategy: CliStrategy) -> None:
        """Register a strategy with the registry.

        Args:
            strategy: Strategy instance to register
        """
        self._strategies.append(strategy)

    def get_available_strategies(self) -> List[CliStrategy]:
        """Get all available strategies in order of preference.

        Returns:
            List of available strategies, ordered by preference
        """
        available = []
        for strategy in self._strategies:
            try:
                if strategy.is_available():
                    available.append(strategy)
            except Exception as e:
                logging.getLogger(__name__).warning(
                    f"Error checking availability of {strategy.strategy_name}: {e}"
                )
        return available

    def get_preferred_strategy(
        self, environment_override: Optional[str] = None
    ) -> Optional[CliStrategy]:
        """Get the preferred strategy for execution.

        Args:
            environment_override: Optional strategy name to force

        Returns:
            Preferred strategy or None if none available
        """
        available_strategies = self.get_available_strategies()

        if not available_strategies:
            return None

        # Honor environment override if specified
        if environment_override:
            for strategy in available_strategies:
                if strategy.strategy_name.lower() == environment_override.lower():
                    return strategy

        # Return first available strategy (they should be registered in preference order)
        return available_strategies[0]

    def execute_with_fallback(
        self,
        ignored_mappings: List[HunkTargetMapping],
        preferred_strategy: Optional[str] = None,
    ) -> bool:
        """Execute ignored hunk application with automatic fallback.

        Args:
            ignored_mappings: Hunks to apply
            preferred_strategy: Optional preferred strategy name

        Returns:
            True if any strategy succeeded
        """
        logger = logging.getLogger(__name__)
        available_strategies = self.get_available_strategies()

        if not available_strategies:
            logger.error("No strategies available for execution")
            return False

        # Reorder strategies if preferred is specified
        if preferred_strategy:
            preferred = None
            others = []
            for strategy in available_strategies:
                if strategy.strategy_name.lower() == preferred_strategy.lower():
                    preferred = strategy
                else:
                    others.append(strategy)
            if preferred:
                available_strategies = [preferred] + others

        # Try strategies in order
        for strategy in available_strategies:
            logger.info(f"Attempting strategy: {strategy.strategy_name}")
            try:
                success = strategy.apply_ignored_hunks(ignored_mappings)
                if success:
                    logger.info(
                        f"✓ Successfully applied hunks using {strategy.strategy_name}"
                    )
                    return True
                else:
                    logger.warning(
                        f"Strategy {strategy.strategy_name} failed, trying next"
                    )
            except Exception as e:
                logger.error(f"Strategy {strategy.strategy_name} raised exception: {e}")
                continue

        logger.error("All strategies failed")
        return False
