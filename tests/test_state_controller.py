"""Tests for UIStateController."""

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.tui.state_controller import UIStateController


class TestUIStateController:
    """Test cases for UIStateController."""
    
    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create test hunks
        self.hunk1 = DiffHunk(
            file_path="file1.py",
            old_start=1, old_count=1, new_start=1, new_count=2,
            lines=["@@ -1,1 +1,2 @@", " line 1", "+new line"],
            context_before=[], context_after=[]
        )
        
        self.hunk2 = DiffHunk(
            file_path="file2.py", 
            old_start=5, old_count=1, new_start=5, new_count=1,
            lines=["@@ -5,1 +5,1 @@", "-old", "+new"],
            context_before=[], context_after=[]
        )
        
        self.hunk3 = DiffHunk(
            file_path="file3.py",
            old_start=10, old_count=0, new_start=10, new_count=1,
            lines=["@@ -10,0 +10,1 @@", "+added line"],
            context_before=[], context_after=[]
        )
        
        # Create test mappings
        self.mapping1 = HunkTargetMapping(
            hunk=self.hunk1, target_commit="abc123", confidence="high", blame_info=[]
        )
        self.mapping2 = HunkTargetMapping(
            hunk=self.hunk2, target_commit="def456", confidence="medium", blame_info=[]
        )
        self.mapping3 = HunkTargetMapping(
            hunk=self.hunk3, target_commit="ghi789", confidence="low", blame_info=[]
        )
        
        self.mappings = [self.mapping1, self.mapping2, self.mapping3]
        self.controller = UIStateController(self.mappings)
    
    def test_initial_state(self) -> None:
        """Test initial state is empty."""
        assert not self.controller.is_approved(self.mapping1)
        assert not self.controller.is_approved(self.mapping2)
        assert not self.controller.is_approved(self.mapping3)
        
        assert not self.controller.is_ignored(self.mapping1)
        assert not self.controller.is_ignored(self.mapping2)
        assert not self.controller.is_ignored(self.mapping3)
        
        assert len(self.controller.get_approved_mappings()) == 0
        assert len(self.controller.get_ignored_mappings()) == 0
        assert not self.controller.has_selections()
    
    def test_set_approved(self) -> None:
        """Test setting approval state."""
        self.controller.set_approved(self.mapping1, True)
        
        assert self.controller.is_approved(self.mapping1)
        assert not self.controller.is_approved(self.mapping2)
        assert self.mapping1 in self.controller.get_approved_mappings()
        assert len(self.controller.get_approved_mappings()) == 1
        assert self.controller.has_selections()
        
        # Test unsetting
        self.controller.set_approved(self.mapping1, False)
        assert not self.controller.is_approved(self.mapping1)
        assert len(self.controller.get_approved_mappings()) == 0
        assert not self.controller.has_selections()
    
    def test_set_ignored(self) -> None:
        """Test setting ignore state."""
        self.controller.set_ignored(self.mapping1, True)
        
        assert self.controller.is_ignored(self.mapping1)
        assert not self.controller.is_ignored(self.mapping2)
        assert self.mapping1 in self.controller.get_ignored_mappings()
        assert len(self.controller.get_ignored_mappings()) == 1
        assert self.controller.has_selections()
        
        # Test unsetting
        self.controller.set_ignored(self.mapping1, False)
        assert not self.controller.is_ignored(self.mapping1)
        assert len(self.controller.get_ignored_mappings()) == 0
        assert not self.controller.has_selections()
    
    def test_toggle_approved(self) -> None:
        """Test toggling approval state."""
        # Initial state is False, toggle should make it True
        result = self.controller.toggle_approved(self.mapping1)
        assert result is True
        assert self.controller.is_approved(self.mapping1)
        
        # Toggle again should make it False
        result = self.controller.toggle_approved(self.mapping1)
        assert result is False
        assert not self.controller.is_approved(self.mapping1)
    
    def test_approve_all(self) -> None:
        """Test approving all hunks."""
        # Set some initial state
        self.controller.set_ignored(self.mapping1, True)
        self.controller.set_approved(self.mapping2, True)
        
        self.controller.approve_all()
        
        # All should be approved, none ignored
        for mapping in self.mappings:
            assert self.controller.is_approved(mapping)
            assert not self.controller.is_ignored(mapping)
        
        assert len(self.controller.get_approved_mappings()) == 3
        assert len(self.controller.get_ignored_mappings()) == 0
    
    def test_approve_all_toggle(self) -> None:
        """Test toggling approval for all hunks."""
        # Initially none approved, toggle should approve all
        self.controller.approve_all_toggle()
        
        for mapping in self.mappings:
            assert self.controller.is_approved(mapping)
        
        # All approved, toggle should unapprove all
        self.controller.approve_all_toggle()
        
        for mapping in self.mappings:
            assert not self.controller.is_approved(mapping)
        
        # Partially approved, toggle should approve all
        self.controller.set_approved(self.mapping1, True)
        self.controller.approve_all_toggle()
        
        for mapping in self.mappings:
            assert self.controller.is_approved(mapping)
    
    def test_ignore_all_toggle(self) -> None:
        """Test toggling ignore for all hunks."""
        # Initially none ignored, toggle should ignore all
        self.controller.ignore_all_toggle()
        
        for mapping in self.mappings:
            assert self.controller.is_ignored(mapping)
            assert not self.controller.is_approved(mapping)  # Should clear approvals
        
        # All ignored, toggle should unignore all
        self.controller.ignore_all_toggle()
        
        for mapping in self.mappings:
            assert not self.controller.is_ignored(mapping)
        
        # Partially ignored, toggle should ignore all
        self.controller.set_ignored(self.mapping1, True)
        self.controller.set_approved(self.mapping2, True)
        self.controller.ignore_all_toggle()
        
        for mapping in self.mappings:
            assert self.controller.is_ignored(mapping)
            assert not self.controller.is_approved(mapping)  # Should clear approvals
    
    def test_progress_stats(self) -> None:
        """Test progress statistics calculation."""
        stats = self.controller.get_progress_stats()
        assert stats == {"approved": 0, "ignored": 0, "selected": 0, "total": 3}
        
        self.controller.set_approved(self.mapping1, True)
        self.controller.set_ignored(self.mapping2, True)
        
        stats = self.controller.get_progress_stats()
        assert stats == {"approved": 1, "ignored": 1, "selected": 2, "total": 3}
    
    def test_mapping_index_lookup(self) -> None:
        """Test mapping index lookup functionality."""
        assert self.controller.get_mapping_index(self.mapping1) == 0
        assert self.controller.get_mapping_index(self.mapping2) == 1
        assert self.controller.get_mapping_index(self.mapping3) == 2
        
        assert self.controller.get_mapping_by_index(0) == self.mapping1
        assert self.controller.get_mapping_by_index(1) == self.mapping2
        assert self.controller.get_mapping_by_index(2) == self.mapping3
    
    def test_clear_all(self) -> None:
        """Test clearing all state."""
        # Set some state
        self.controller.set_approved(self.mapping1, True)
        self.controller.set_ignored(self.mapping2, True)
        
        assert self.controller.has_selections()
        
        self.controller.clear_all()
        
        assert not self.controller.has_selections()
        assert len(self.controller.get_approved_mappings()) == 0
        assert len(self.controller.get_ignored_mappings()) == 0
        
        for mapping in self.mappings:
            assert not self.controller.is_approved(mapping)
            assert not self.controller.is_ignored(mapping)
    
    def test_mixed_state_operations(self) -> None:
        """Test complex state operations with mixed approved/ignored states."""
        # Set up mixed state
        self.controller.set_approved(self.mapping1, True)
        self.controller.set_ignored(self.mapping2, True)
        # mapping3 remains unselected
        
        # Verify initial state
        assert self.controller.is_approved(self.mapping1)
        assert self.controller.is_ignored(self.mapping2)
        assert not self.controller.is_approved(self.mapping3)
        assert not self.controller.is_ignored(self.mapping3)
        
        # Test has_selections
        assert self.controller.has_selections()
        
        # Test progress stats
        stats = self.controller.get_progress_stats()
        assert stats["approved"] == 1
        assert stats["ignored"] == 1
        assert stats["selected"] == 2
        assert stats["total"] == 3
        
        # Test getting mappings
        approved = self.controller.get_approved_mappings()
        ignored = self.controller.get_ignored_mappings()
        
        assert len(approved) == 1
        assert len(ignored) == 1
        assert self.mapping1 in approved
        assert self.mapping2 in ignored