"""
Simple tests for patch generation functionality.

Tests the basic functionality of the context-aware patch generation fix.
"""

from pathlib import Path
from typing import Dict
import pytest

from git_autosquash.hunk_parser import HunkParser, DiffHunk
from git_autosquash.rebase_manager import RebaseManager
from tests.base_test_repository import BaseTestRepository, temporary_test_repository
from tests.error_handling_framework import safe_test_operation


class SimplePatchTestRepo(BaseTestRepository):
    """Helper for creating simple test repositories using proper GitOps integration."""

    def __init__(self, repo_path: Path):
        super().__init__(repo_path)

    @safe_test_operation("simple_scenario_creation", max_retries=2)
    def create_simple_scenario(self) -> Dict[str, str]:
        """Create a simple repository with dual changes scenario using GitOps."""

        # Create initial file with two instances of a pattern
        initial_content = """def function_one():
    #if OLD_CONFIG
    return "config1"
    #endif

def function_two():  
    #if OLD_CONFIG
    return "config2"
    #endif
"""

        initial_commit = self.add_commit({"test.py": initial_content}, "Initial commit")

        # Create target commit - modify one instance
        target_content = """def function_one():
    #if NEW_CONFIG
    return "config1"
    #endif

def function_two():  
    #if OLD_CONFIG
    return "config2"
    #endif
"""

        target_commit = self.add_commit(
            {"test.py": target_content}, "Update first config"
        )

        # Create source commit - modify both instances
        source_content = """def function_one():
    #if NEW_CONFIG
    return "config1"
    #endif

def function_two():  
    #if NEW_CONFIG
    return "config2"
    #endif
"""

        source_commit = self.add_commit(
            {"test.py": source_content}, "Update all configs"
        )

        return {
            "initial_commit": initial_commit,
            "target_commit": target_commit,
            "source_commit": source_commit,
        }


@pytest.fixture
def simple_repo():
    """Create a simple temporary git repository for testing."""
    with temporary_test_repository("simple_repo") as temp_repo:
        yield SimplePatchTestRepo(temp_repo.repo_path)


class TestPatchGenerationBasics:
    """Basic tests for patch generation functionality."""

    def test_rebase_manager_initialization(self, simple_repo):
        """Test that RebaseManager can be initialized correctly."""

        commits = simple_repo.create_simple_scenario()
        git_ops = simple_repo.git_ops

        # Should initialize without errors
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        assert rebase_manager.git_ops == git_ops
        assert rebase_manager.merge_base == commits["initial_commit"]

    def test_hunk_parser_initialization(self, simple_repo):
        """Test that HunkParser can be initialized correctly."""

        git_ops = simple_repo.git_ops

        # Should initialize without errors
        hunk_parser = HunkParser(git_ops)

        assert hunk_parser.git_ops == git_ops

    def test_get_diff_hunks_from_commit(self, simple_repo):
        """Test that we can extract hunks from a commit."""

        commits = simple_repo.create_simple_scenario()
        git_ops = simple_repo.git_ops

        # Get diff from source commit
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", commits["source_commit"]]
        )

        assert diff_result.returncode == 0
        assert len(diff_result.stdout.strip()) > 0, "Should have diff output"

        # Should contain our expected change
        assert "OLD_CONFIG" in diff_result.stdout
        assert "NEW_CONFIG" in diff_result.stdout

    def test_context_aware_methods_exist(self, simple_repo):
        """Test that the context-aware methods exist in RebaseManager."""

        commits = simple_repo.create_simple_scenario()
        git_ops = simple_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Check that new methods exist
        assert hasattr(rebase_manager, "_consolidate_hunks_by_file")
        assert hasattr(rebase_manager, "_extract_hunk_changes")
        assert hasattr(rebase_manager, "_find_target_with_context")
        assert hasattr(rebase_manager, "_create_corrected_patch_for_hunks")

        # Check methods are callable
        assert callable(rebase_manager._consolidate_hunks_by_file)
        assert callable(rebase_manager._extract_hunk_changes)
        assert callable(rebase_manager._find_target_with_context)
        assert callable(rebase_manager._create_corrected_patch_for_hunks)

    def test_diff_hunk_creation(self, simple_repo):
        """Test creating DiffHunk objects directly."""

        # Create a sample hunk
        hunk = DiffHunk(
            file_path="test.py",
            old_start=2,
            old_count=1,
            new_start=2,
            new_count=1,
            lines=["@@ -2,1 +2,1 @@", "-    #if OLD_CONFIG", "+    #if NEW_CONFIG"],
            context_before=[],
            context_after=[],
        )

        assert hunk.file_path == "test.py"
        assert hunk.old_start == 2
        assert hunk.new_start == 2
        assert len(hunk.lines) == 3

    def test_find_target_with_context_basic(self, simple_repo):
        """Test the _find_target_with_context method with basic inputs."""

        commits = simple_repo.create_simple_scenario()
        git_ops = simple_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Checkout target commit to get file content
        git_ops.run_git_command(["checkout", commits["target_commit"]])

        test_file = simple_repo.repo_path / "test.py"
        file_content = test_file.read_text()
        file_lines = file_content.split("\n")

        # Test finding a line
        change = {"old_line": "    #if OLD_CONFIG", "new_line": "    #if NEW_CONFIG"}

        # Should find the line that still has OLD_CONFIG
        result = rebase_manager._find_target_with_context(change, file_lines, set())

        assert result is not None, "Should find the target line"
        assert isinstance(result, int), "Should return line number"
        assert result > 0, "Line number should be positive"

        # Verify the line actually contains our pattern
        target_line = file_lines[result - 1]  # Convert to 0-based
        assert "OLD_CONFIG" in target_line, (
            f"Found line should contain OLD_CONFIG: {target_line}"
        )

    def test_used_lines_tracking(self, simple_repo):
        """Test that used lines tracking prevents duplicates."""

        commits = simple_repo.create_simple_scenario()
        git_ops = simple_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Checkout initial commit where both patterns exist
        git_ops.run_git_command(["checkout", commits["initial_commit"]])

        test_file = simple_repo.repo_path / "test.py"
        file_content = test_file.read_text()
        file_lines = file_content.split("\n")

        # Find all lines with OLD_CONFIG
        old_config_lines = []
        for i, line in enumerate(file_lines):
            if "OLD_CONFIG" in line:
                old_config_lines.append(i + 1)  # Convert to 1-based

        # Should have found multiple instances
        assert len(old_config_lines) >= 2, (
            f"Should find multiple OLD_CONFIG lines: {old_config_lines}"
        )

        # Test finding targets with used lines tracking
        change = {"old_line": "    #if OLD_CONFIG", "new_line": "    #if NEW_CONFIG"}

        used_lines = set()

        # First call should find first instance
        result1 = rebase_manager._find_target_with_context(
            change, file_lines, used_lines
        )
        assert result1 is not None
        used_lines.add(result1)

        # Second call should find different instance
        result2 = rebase_manager._find_target_with_context(
            change, file_lines, used_lines
        )
        assert result2 is not None

        # Results should be different
        assert result1 != result2, (
            f"Should find different lines: {result1} vs {result2}"
        )


class TestPatchGenerationRegression:
    """Ensure patch generation doesn't break existing functionality."""

    def test_single_change_still_works(self, simple_repo):
        """Test that single changes still work correctly."""

        commits = simple_repo.create_simple_scenario()
        git_ops = simple_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Create a single mock hunk
        hunk = DiffHunk(
            file_path="test.py",
            old_start=2,
            old_count=1,
            new_start=2,
            new_count=1,
            lines=["@@ -2,1 +2,1 @@", "-    #if OLD_CONFIG", "+    #if NEW_CONFIG"],
            context_before=[],
            context_after=[],
        )

        # Test consolidation with single hunk
        consolidated = rebase_manager._consolidate_hunks_by_file([hunk])

        assert "test.py" in consolidated
        assert len(consolidated["test.py"]) == 1
        assert consolidated["test.py"][0] == hunk

    def test_empty_hunks_list(self, simple_repo):
        """Test handling of empty hunks list."""

        commits = simple_repo.create_simple_scenario()
        git_ops = simple_repo.git_ops
        rebase_manager = RebaseManager(git_ops, commits["initial_commit"])

        # Test with empty list
        consolidated = rebase_manager._consolidate_hunks_by_file([])

        assert isinstance(consolidated, dict)
        assert len(consolidated) == 0
