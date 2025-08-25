"""Tests for fallback target selection logic."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from git_autosquash.blame_analyzer import (
    BlameAnalyzer, 
    HunkTargetMapping, 
    TargetingMethod,
    BlameInfo
)
from git_autosquash.commit_history_analyzer import (
    CommitHistoryAnalyzer,
    CommitInfo,
    CommitSelectionStrategy
)
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.git_ops import GitOps


class TestBlameAnalyzerFallbacks:
    """Test the enhanced BlameAnalyzer with fallback scenarios."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.merge_base = "abc123"
        self.analyzer = BlameAnalyzer(self.git_ops, self.merge_base)

    def create_test_hunk(self, file_path="test.py", has_deletions=False):
        """Create a test hunk."""
        return DiffHunk(
            file_path=file_path,
            old_start=10, old_count=2, new_start=10, new_count=3,
            lines=["@@ -10,2 +10,3 @@", " existing line", "+new line", " another line"],
            context_before=["context before"],
            context_after=["context after"],
            has_deletions=has_deletions
        )

    def test_new_file_detection(self):
        """Test detection of new files."""
        # Mock git diff to return new file
        self.git_ops._run_git_command.return_value = (True, "new_file.py\nanother_new.py")
        
        hunk = self.create_test_hunk("new_file.py")
        mapping = self.analyzer._analyze_single_hunk(hunk)
        
        assert mapping.targeting_method == TargetingMethod.FALLBACK_NEW_FILE
        assert mapping.needs_user_selection is True
        assert mapping.target_commit is None

    def test_existing_file_no_blame(self):
        """Test existing file with no blame information available."""
        # Mock new file check to return False
        self.git_ops._run_git_command.side_effect = [
            (True, "other_file.py"),  # New files list (doesn't include our file)
            (False, "")  # Blame command fails
        ]
        
        hunk = self.create_test_hunk("existing_file.py")
        mapping = self.analyzer._analyze_single_hunk(hunk)
        
        assert mapping.targeting_method == TargetingMethod.FALLBACK_EXISTING_FILE
        assert mapping.needs_user_selection is True
        assert mapping.target_commit is None

    def test_blame_match_with_no_branch_commits(self):
        """Test blame succeeds but commits are outside branch scope."""
        # Mock successful blame but no branch commits
        self.git_ops._run_git_command.side_effect = [
            (True, "other_file.py"),  # New files (doesn't include our file)
            (True, "def123 (author 2023-01-01 10:00:00 +0000 10) old line"),  # Blame succeeds
            (True, "")  # No branch commits
        ]
        
        hunk = self.create_test_hunk("existing_file.py", has_deletions=True)
        mapping = self.analyzer._analyze_single_hunk(hunk)
        
        assert mapping.targeting_method == TargetingMethod.FALLBACK_EXISTING_FILE
        assert mapping.needs_user_selection is True

    def test_file_consistency_fallback(self):
        """Test that subsequent hunks from same file use consistency fallback."""
        # Set up a cached target for the file
        self.analyzer._file_target_cache["test.py"] = "cached123"
        
        hunk = self.create_test_hunk("test.py")
        mapping = self.analyzer._analyze_single_hunk(hunk)
        
        assert mapping.targeting_method == TargetingMethod.FALLBACK_CONSISTENCY
        assert mapping.target_commit == "cached123"
        assert mapping.needs_user_selection is False
        assert mapping.confidence == "medium"

    def test_successful_blame_analysis(self):
        """Test successful blame analysis with branch commits."""
        # Mock successful blame and branch commits
        self.git_ops._run_git_command.side_effect = [
            (True, "other_file.py"),  # New files
            (True, "abc456 (author 2023-01-01 10:00:00 +0000 10) old line\nabc456 (author 2023-01-01 10:00:00 +0000 11) another line"),  # Blame
            (True, "abc456\ndef789"),  # Branch commits
            (True, "1640995200")  # Commit timestamp
        ]
        
        hunk = self.create_test_hunk("existing_file.py", has_deletions=True)
        mapping = self.analyzer._analyze_single_hunk(hunk)
        
        assert mapping.targeting_method == TargetingMethod.BLAME_MATCH
        assert mapping.target_commit == "abc456"
        assert mapping.needs_user_selection is False
        assert mapping.confidence == "high"  # 100% match ratio

    def test_fallback_candidates_generation(self):
        """Test that fallback candidates are properly generated."""
        # Mock branch commits for fallback candidates
        with patch.object(self.analyzer, '_get_ordered_branch_commits') as mock_ordered:
            mock_ordered.return_value = ["commit1", "commit2", "commit3"]
            
            mapping = self.analyzer._create_fallback_mapping(
                self.create_test_hunk("new_file.py"),
                TargetingMethod.FALLBACK_NEW_FILE
            )
            
            assert mapping.fallback_candidates == ["commit1", "commit2", "commit3"]
            assert mapping.needs_user_selection is True

    def test_set_target_for_file_consistency(self):
        """Test file target consistency tracking."""
        self.analyzer.set_target_for_file("test.py", "target123")
        assert self.analyzer._file_target_cache["test.py"] == "target123"
        
        # Clear cache
        self.analyzer.clear_file_cache()
        assert "test.py" not in self.analyzer._file_target_cache


class TestCommitHistoryAnalyzer:
    """Test the CommitHistoryAnalyzer functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.merge_base = "abc123"
        self.analyzer = CommitHistoryAnalyzer(self.git_ops, self.merge_base)

    def test_get_branch_commits(self):
        """Test retrieval of branch commits."""
        self.git_ops._run_git_command.return_value = (True, "commit1\ncommit2\ncommit3")
        
        commits = self.analyzer._get_branch_commits()
        
        # Should be reversed (most recent first)
        assert commits == ["commit3", "commit2", "commit1"]

    def test_commit_info_loading(self):
        """Test loading commit information."""
        self.git_ops._run_git_command.side_effect = [
            (True, "abc1234|Test commit|John Doe|1640995200"),  # Basic info
            (True, "parent abc000\n")  # Cat-file (not a merge)
        ]
        
        commit_info = self.analyzer.get_commit_info("abc1234567")
        
        assert commit_info.commit_hash == "abc1234567"
        assert commit_info.short_hash == "abc1234"
        assert commit_info.subject == "Test commit"
        assert commit_info.author == "John Doe"
        assert commit_info.timestamp == 1640995200
        assert commit_info.is_merge is False

    def test_merge_commit_detection(self):
        """Test detection of merge commits."""
        self.git_ops._run_git_command.return_value = (
            True, 
            "parent abc000\nparent def111\nauthor John Doe"
        )
        
        is_merge = self.analyzer._is_merge_commit("merge123")
        assert is_merge is True

    def test_commit_suggestions_by_recency(self):
        """Test commit suggestions ordered by recency."""
        # Mock branch commits
        with patch.object(self.analyzer, '_get_branch_commits') as mock_commits:
            mock_commits.return_value = ["recent", "old", "merge"]
            
            # Mock commit info loading
            def mock_get_info(commit_hash):
                if commit_hash == "recent":
                    return CommitInfo(commit_hash, "rec123", "Recent", "Author", 1640995300, False)
                elif commit_hash == "old":
                    return CommitInfo(commit_hash, "old123", "Old", "Author", 1640995100, False)
                else:  # merge
                    return CommitInfo(commit_hash, "mer123", "Merge", "Author", 1640995200, True)
            
            with patch.object(self.analyzer, 'get_commit_info', side_effect=mock_get_info):
                suggestions = self.analyzer.get_commit_suggestions(CommitSelectionStrategy.RECENCY)
                
                # Should be ordered: recent (highest timestamp), old, merge (merge commits last)
                assert len(suggestions) == 3
                assert suggestions[0].commit_hash == "recent"
                assert suggestions[1].commit_hash == "old" 
                assert suggestions[2].commit_hash == "merge"

    def test_commit_suggestions_by_file_relevance(self):
        """Test commit suggestions ordered by file relevance."""
        # Mock file-touching commits
        self.git_ops._run_git_command.side_effect = [
            (True, "file_commit1\nfile_commit2"),  # Commits touching file
            (True, "all1\nall2\nall3")  # All branch commits
        ]
        
        with patch.object(self.analyzer, '_order_by_recency') as mock_order:
            mock_order.side_effect = lambda commits: [
                CommitInfo(c, c[:7], f"Subject {c}", "Author", 1000, False) 
                for c in commits
            ]
            
            suggestions = self.analyzer.get_commit_suggestions(
                CommitSelectionStrategy.FILE_RELEVANCE, "test.py"
            )
            
            # Should have file-relevant commits first
            assert suggestions[0].commit_hash == "file_commit1"
            assert suggestions[1].commit_hash == "file_commit2"

    def test_new_file_detection(self):
        """Test new file detection."""
        self.git_ops._run_git_command.return_value = (True, "new_file.py\nanother_new.py")
        
        is_new = self.analyzer.is_new_file("new_file.py")
        assert is_new is True
        
        is_new = self.analyzer.is_new_file("existing_file.py")
        assert is_new is False

    def test_commit_display_formatting(self):
        """Test commit display string formatting."""
        with patch.object(self.analyzer, 'get_commit_info') as mock_info:
            mock_info.return_value = CommitInfo(
                "abc123", "abc1234", "Test commit", "Author", 1000, True
            )
            
            display = self.analyzer.get_commit_display_info("abc123")
            assert display == "abc1234 Test commit (merge)"


class TestFallbackIntegration:
    """Test integration between blame analyzer and commit history analyzer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.merge_base = "abc123"
        self.blame_analyzer = BlameAnalyzer(self.git_ops, self.merge_base)
        self.commit_analyzer = CommitHistoryAnalyzer(self.git_ops, self.merge_base)

    def test_end_to_end_new_file_fallback(self):
        """Test complete flow for new file fallback."""
        # Create test hunks
        hunks = [
            DiffHunk(
                file_path="new_file.py",
                old_start=0, old_count=0, new_start=1, new_count=2,
                lines=["@@ -0,0 +1,2 @@", "+line1", "+line2"],
                context_before=[], context_after=[]
            )
        ]
        
        # Mock new file detection
        self.git_ops._run_git_command.side_effect = [
            (True, "new_file.py"),  # New files list
            (True, "commit1\ncommit2\ncommit3"),  # Branch commits
        ]
        
        # Analyze hunks
        mappings = self.blame_analyzer.analyze_hunks(hunks)
        
        assert len(mappings) == 1
        mapping = mappings[0]
        assert mapping.targeting_method == TargetingMethod.FALLBACK_NEW_FILE
        assert mapping.needs_user_selection is True
        assert mapping.fallback_candidates is not None
        assert len(mapping.fallback_candidates) >= 1

    def test_mixed_blame_and_fallback_scenario(self):
        """Test scenario with both successful blame matches and fallbacks."""
        # Create mixed hunks
        hunks = [
            # Successful blame match
            DiffHunk(
                file_path="existing_file.py", 
                old_start=10, old_count=1, new_start=10, new_count=1,
                lines=["@@ -10,1 +10,1 @@", "-old line", "+new line"],
                context_before=[], context_after=[], has_deletions=True
            ),
            # New file fallback
            DiffHunk(
                file_path="new_file.py",
                old_start=0, old_count=0, new_start=1, new_count=1,
                lines=["@@ -0,0 +1,1 @@", "+new line"],
                context_before=[], context_after=[]
            )
        ]
        
        # Mock git commands for mixed scenario
        self.git_ops._run_git_command.side_effect = [
            (True, "new_file.py"),  # New files (includes second file)
            (True, "target123 (author 2023-01-01 10:00:00 +0000 10) old line"),  # Blame for first file
            (True, "target123"),  # Branch commits
            (True, "1640995200"),  # Commit timestamp
            (True, "commit1\ncommit2"),  # Branch commits for fallback
        ]
        
        mappings = self.blame_analyzer.analyze_hunks(hunks)
        
        assert len(mappings) == 2
        
        # First should be successful blame match
        assert mappings[0].targeting_method == TargetingMethod.BLAME_MATCH
        assert mappings[0].target_commit == "target123"
        assert mappings[0].needs_user_selection is False
        
        # Second should be fallback
        assert mappings[1].targeting_method == TargetingMethod.FALLBACK_NEW_FILE
        assert mappings[1].needs_user_selection is True
        assert mappings[1].fallback_candidates is not None

    def test_file_consistency_across_multiple_hunks(self):
        """Test that multiple hunks from same file maintain consistency."""
        hunks = [
            DiffHunk(
                file_path="test.py", old_start=5, old_count=1, new_start=5, new_count=1,
                lines=["@@ -5,1 +5,1 @@", "-line1", "+new line1"],
                context_before=[], context_after=[], has_deletions=True
            ),
            DiffHunk(
                file_path="test.py", old_start=15, old_count=1, new_start=15, new_count=2,
                lines=["@@ -15,1 +15,2 @@", " existing", "+new line2"],
                context_before=[], context_after=[]
            )
        ]
        
        # Mock successful blame for first hunk
        self.git_ops._run_git_command.side_effect = [
            (True, ""),  # New files (empty)
            (True, "target456 (author 2023-01-01 10:00:00 +0000 5) line1"),  # Blame first hunk
            (True, "target456"),  # Branch commits
            (True, "1640995200"),  # Commit timestamp
        ]
        
        mappings = self.blame_analyzer.analyze_hunks(hunks)
        
        assert len(mappings) == 2
        
        # First hunk should get blame match
        assert mappings[0].targeting_method == TargetingMethod.BLAME_MATCH
        assert mappings[0].target_commit == "target456"
        
        # Second hunk should use consistency fallback (same target)
        assert mappings[1].targeting_method == TargetingMethod.FALLBACK_CONSISTENCY
        assert mappings[1].target_commit == "target456"
        assert mappings[1].needs_user_selection is False
        assert mappings[1].confidence == "medium"


class TestFallbackEdgeCases:
    """Test edge cases in fallback logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.git_ops = Mock(spec=GitOps)
        self.analyzer = BlameAnalyzer(self.git_ops, "merge_base")

    def test_empty_branch_commits(self):
        """Test behavior when no branch commits exist."""
        self.git_ops._run_git_command.side_effect = [
            (True, ""),  # New files (empty)
            (False, ""),  # Blame fails
            (True, ""),  # Empty branch commits
        ]
        
        hunk = DiffHunk(
            file_path="test.py", old_start=1, old_count=1, new_start=1, new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
            context_before=[], context_after=[]
        )
        
        mapping = self.analyzer._analyze_single_hunk(hunk)
        
        assert mapping.targeting_method == TargetingMethod.FALLBACK_EXISTING_FILE
        assert mapping.needs_user_selection is True
        assert mapping.fallback_candidates == []  # No candidates available

    def test_git_command_failures(self):
        """Test handling of git command failures."""
        # All git commands fail
        self.git_ops._run_git_command.return_value = (False, "error")
        
        hunk = DiffHunk(
            file_path="test.py", old_start=1, old_count=1, new_start=1, new_count=1,
            lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
            context_before=[], context_after=[]
        )
        
        mapping = self.analyzer._analyze_single_hunk(hunk)
        
        # Should gracefully handle failures
        assert mapping.targeting_method == TargetingMethod.FALLBACK_EXISTING_FILE
        assert mapping.needs_user_selection is True

    def test_cache_behavior(self):
        """Test caching behavior across multiple analyses."""
        analyzer = BlameAnalyzer(self.git_ops, "merge_base")
        
        # First call should populate cache
        self.git_ops._run_git_command.return_value = (True, "new_file.py")
        result1 = analyzer._is_new_file("new_file.py")
        
        # Second call should use cache (no additional git command)
        result2 = analyzer._is_new_file("new_file.py")
        
        assert result1 is True
        assert result2 is True
        # Git command should only be called once due to caching
        assert self.git_ops._run_git_command.call_count == 1