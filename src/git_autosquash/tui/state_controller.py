"""Centralized UI state management for git-autosquash TUI.

This controller centralizes all state management logic that was previously
scattered across widgets and screens, providing a single source of truth
for hunk approval and ignore states.
"""

from typing import Dict, List, Set

from git_autosquash.hunk_target_resolver import HunkTargetMapping


class UIStateController:
    """Centralized controller for managing UI state and transitions.

    This controller provides a single interface for:
    - Managing approval and ignore states for hunks
    - Performing bulk operations (approve all, ignore all, etc.)
    - Tracking progress and statistics
    - Ensuring state consistency and validation
    """

    def __init__(self, mappings: List[HunkTargetMapping]) -> None:
        """Initialize the state controller.

        Args:
            mappings: List of hunk mappings to manage state for
        """
        self.mappings = mappings

        # Core state storage - using sets of indices for O(1) lookups
        self._approved: Set[int] = set()
        self._ignored: Set[int] = set()

        # O(1) index lookup for mappings
        self._mapping_to_index: Dict[id, int] = {
            id(mapping): i for i, mapping in enumerate(mappings)
        }

    def is_approved(self, mapping: HunkTargetMapping) -> bool:
        """Check if a hunk is approved for squashing.

        Args:
            mapping: The hunk mapping to check

        Returns:
            True if approved, False otherwise
        """
        index = self._mapping_to_index.get(id(mapping))
        return index is not None and index in self._approved

    def is_ignored(self, mapping: HunkTargetMapping) -> bool:
        """Check if a hunk is ignored (kept in working tree).

        Args:
            mapping: The hunk mapping to check

        Returns:
            True if ignored, False otherwise
        """
        index = self._mapping_to_index.get(id(mapping))
        return index is not None and index in self._ignored

    def set_approved(self, mapping: HunkTargetMapping, approved: bool) -> None:
        """Set the approval state for a hunk.

        Args:
            mapping: The hunk mapping to update
            approved: New approval state
        """
        index = self._mapping_to_index.get(id(mapping))
        if index is not None:
            if approved:
                self._approved.add(index)
            else:
                self._approved.discard(index)

    def set_ignored(self, mapping: HunkTargetMapping, ignored: bool) -> None:
        """Set the ignore state for a hunk.

        Args:
            mapping: The hunk mapping to update
            ignored: New ignore state
        """
        index = self._mapping_to_index.get(id(mapping))
        if index is not None:
            if ignored:
                self._ignored.add(index)
            else:
                self._ignored.discard(index)

    def toggle_approved(self, mapping: HunkTargetMapping) -> bool:
        """Toggle the approval state for a hunk.

        Args:
            mapping: The hunk mapping to toggle

        Returns:
            New approval state after toggle
        """
        new_state = not self.is_approved(mapping)
        self.set_approved(mapping, new_state)
        return new_state

    def approve_all(self) -> None:
        """Approve all hunks and clear ignore states."""
        self._approved = set(range(len(self.mappings)))
        self._ignored.clear()

    def approve_all_toggle(self) -> None:
        """Toggle approval for all hunks (if all approved, unapprove all; otherwise approve all)."""
        if len(self._approved) == len(self.mappings):
            # All approved, clear approvals
            self._approved.clear()
        else:
            # Not all approved, approve all
            self.approve_all()

    def ignore_all_toggle(self) -> None:
        """Toggle ignore for all hunks (if all ignored, unignore all; otherwise ignore all)."""
        if len(self._ignored) == len(self.mappings):
            # All ignored, clear ignores
            self._ignored.clear()
        else:
            # Not all ignored, ignore all and clear approvals
            self._ignored = set(range(len(self.mappings)))
            self._approved.clear()

    def get_approved_mappings(self) -> List[HunkTargetMapping]:
        """Get list of approved mappings.

        Returns:
            List of mappings approved for squashing
        """
        return [self.mappings[i] for i in self._approved]

    def get_ignored_mappings(self) -> List[HunkTargetMapping]:
        """Get list of ignored mappings.

        Returns:
            List of mappings to be ignored (kept in working tree)
        """
        return [self.mappings[i] for i in self._ignored]

    def get_progress_stats(self) -> Dict[str, int]:
        """Get current progress statistics.

        Returns:
            Dictionary with counts for approved, ignored, total, and selected
        """
        return {
            "approved": len(self._approved),
            "ignored": len(self._ignored),
            "selected": len(self._approved) + len(self._ignored),
            "total": len(self.mappings),
        }

    def has_selections(self) -> bool:
        """Check if any hunks are selected (approved or ignored).

        Returns:
            True if any hunks are approved or ignored
        """
        return len(self._approved) > 0 or len(self._ignored) > 0

    def get_mapping_index(self, mapping: HunkTargetMapping) -> int:
        """Get the index of a mapping in the original list.

        Args:
            mapping: The mapping to find the index for

        Returns:
            Index of the mapping in the original list

        Raises:
            KeyError: If mapping is not found
        """
        mapping_id = id(mapping)
        if mapping_id not in self._mapping_to_index:
            raise KeyError(f"Mapping not found: {mapping}")
        return self._mapping_to_index[mapping_id]

    def get_mapping_by_index(self, index: int) -> HunkTargetMapping:
        """Get mapping by index.

        Args:
            index: Index of the mapping

        Returns:
            The mapping at the given index

        Raises:
            IndexError: If index is out of range
        """
        return self.mappings[index]

    def clear_all(self) -> None:
        """Clear all approval and ignore states."""
        self._approved.clear()
        self._ignored.clear()
