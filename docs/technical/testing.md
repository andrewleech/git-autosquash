# Testing Guide

This guide covers the comprehensive testing strategy for git-autosquash, including test categories, fixtures, and best practices.

## Test Architecture

### Test Categories

```
tests/
├── unit/                    # Fast, isolated component tests
├── integration/             # Cross-component interaction tests  
├── tui/                     # Terminal UI behavior tests
├── performance/             # Performance and scalability tests
├── regression/              # Tests for previously fixed bugs
└── fixtures/                # Shared test data and utilities
```

### Testing Philosophy

1. **Fast Feedback**: Unit tests run in milliseconds
2. **Realistic Scenarios**: Integration tests use real git repositories
3. **Edge Case Coverage**: Handle unusual git states and user inputs
4. **Performance Validation**: Ensure scalability with large repositories
5. **Regression Prevention**: Lock in fixes for reported bugs

## Unit Testing

### Core Component Tests

#### Git Operations (`test_git_ops.py`)

```python
import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess
from pathlib import Path

from git_autosquash.git_ops import GitOps, GitError

class TestGitOps:
    """Test GitOps facade functionality."""
    
    def test_init_valid_repository(self, tmp_git_repo):
        """Test initialization with valid git repository."""
        git_ops = GitOps(tmp_git_repo)
        assert git_ops.repo_path == tmp_git_repo
    
    def test_init_invalid_repository(self, tmp_path):
        """Test initialization fails with invalid repository."""
        with pytest.raises(ValueError, match="Not a git repository"):
            GitOps(tmp_path)
    
    @patch('subprocess.run')
    def test_get_current_branch_success(self, mock_run, tmp_git_repo):
        """Test successful branch detection."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="feature/test-branch",
            stderr=""
        )
        
        git_ops = GitOps(tmp_git_repo)
        branch = git_ops.get_current_branch()
        
        assert branch == "feature/test-branch"
        mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_get_current_branch_detached_head(self, mock_run, tmp_git_repo):
        """Test branch detection in detached HEAD state."""
        mock_run.return_value = Mock(
            returncode=128,
            stdout="",
            stderr="fatal: ref HEAD is not a symbolic ref"
        )
        
        git_ops = GitOps(tmp_git_repo)
        with pytest.raises(GitError, match="detached HEAD"):
            git_ops.get_current_branch()
    
    def test_working_tree_states(self, git_repo_with_changes):
        """Test working tree state detection."""
        git_ops = GitOps(git_repo_with_changes.path)
        
        # Clean state
        status = git_ops.get_working_tree_status()
        assert not status.has_changes
        
        # Add unstaged changes
        git_repo_with_changes.create_file("new.py", "content")
        status = git_ops.get_working_tree_status()
        assert status.has_unstaged_changes
        assert not status.has_staged_changes
        
        # Stage changes
        git_repo_with_changes.stage_file("new.py")
        status = git_ops.get_working_tree_status()
        assert status.has_staged_changes
        assert not status.has_unstaged_changes
```

#### Hunk Parser (`test_hunk_parser.py`)

```python
import pytest
from git_autosquash.hunk_parser import HunkParser, DiffHunk

class TestHunkParser:
    """Test diff parsing and hunk extraction."""
    
    def test_parse_basic_diff(self):
        """Test parsing basic git diff output."""
        diff_output = """
diff --git a/src/example.py b/src/example.py
index 1234567..abcdefg 100644
--- a/src/example.py
+++ b/src/example.py
@@ -10,6 +10,8 @@ def example_function():
     if condition:
-        return None
+        return {"error": "Invalid input"}
+        
+    # Added validation
     return result
"""
        
        parser = HunkParser()
        hunks = parser.parse_diff(diff_output)
        
        assert len(hunks) == 1
        hunk = hunks[0]
        assert hunk.file_path == "src/example.py"
        assert hunk.old_start == 10
        assert hunk.old_count == 6
        assert hunk.new_start == 10
        assert hunk.new_count == 8
        assert len(hunk.lines) == 6
    
    def test_parse_line_by_line_mode(self):
        """Test line-by-line hunk splitting."""
        diff_output = """
diff --git a/src/example.py b/src/example.py
@@ -1,4 +1,4 @@
 def function():
-    old_line1
-    old_line2  
+    new_line1
+    new_line2
"""
        
        parser = HunkParser()
        hunks = parser.parse_diff(diff_output, line_by_line=True)
        
        # Should split into separate hunks per line change
        assert len(hunks) == 2
        assert hunks[0].lines[0].content == "-    old_line1"
        assert hunks[0].lines[1].content == "+    new_line1"
        assert hunks[1].lines[0].content == "-    old_line2"
        assert hunks[1].lines[1].content == "+    new_line2"
    
    def test_parse_binary_file(self):
        """Test handling binary file changes."""
        diff_output = """
diff --git a/image.png b/image.png
index 1234567..abcdefg 100644
Binary files a/image.png and b/image.png differ
"""
        
        parser = HunkParser()
        hunks = parser.parse_diff(diff_output)
        
        # Binary files should be ignored
        assert len(hunks) == 0
    
    def test_parse_new_file(self):
        """Test handling new file creation."""
        diff_output = """
diff --git a/new_file.py b/new_file.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,3 @@
+def new_function():
+    """New functionality."""
+    pass
"""
        
        parser = HunkParser()
        hunks = parser.parse_diff(diff_output)
        
        assert len(hunks) == 1
        hunk = hunks[0]
        assert hunk.file_path == "new_file.py"
        assert hunk.is_new_file
        assert all(line.content.startswith('+') for line in hunk.lines)
```

#### Blame Analyzer (`test_blame_analyzer.py`)

```python
import pytest
from unittest.mock import Mock, patch
from git_autosquash.blame_analyzer import BlameAnalyzer, BlameResult

class TestBlameAnalyzer:
    """Test git blame analysis and target resolution."""
    
    @patch('subprocess.run')
    def test_analyze_hunk_basic(self, mock_run, tmp_git_repo):
        """Test basic blame analysis for a hunk."""
        # Mock git blame output
        blame_output = """
abc123 src/example.py 1 1 Alice 2023-01-15 Fix validation logic
abc123 src/example.py 2 2 Alice 2023-01-15 Fix validation logic
def456 src/example.py 3 3 Bob   2023-02-20 Add error handling
"""
        mock_run.return_value = Mock(
            returncode=0,
            stdout=blame_output,
            stderr=""
        )
        
        analyzer = BlameAnalyzer(GitOps(tmp_git_repo))
        hunk = Mock()
        hunk.file_path = "src/example.py"
        hunk.blame_range = (1, 3)
        
        result = analyzer.analyze_hunk(hunk, branch_commits=['abc123', 'def456'])
        
        assert result.target_commit == 'abc123'  # Most frequent
        assert result.confidence > 0.7  # High confidence
        assert len(result.commit_frequency) == 2
    
    def test_confidence_calculation(self):
        """Test confidence score calculation."""
        analyzer = BlameAnalyzer(Mock())
        
        # High confidence: all lines from same commit
        result = analyzer._calculate_confidence(
            commit_counts={'abc123': 5},
            total_lines=5
        )
        assert result > 0.9
        
        # Medium confidence: majority from one commit
        result = analyzer._calculate_confidence(
            commit_counts={'abc123': 3, 'def456': 2},
            total_lines=5
        )
        assert 0.5 < result < 0.8
        
        # Low confidence: even split
        result = analyzer._calculate_confidence(
            commit_counts={'abc123': 2, 'def456': 2, 'ghi789': 1},
            total_lines=5
        )
        assert result < 0.5
    
    def test_frequency_over_recency_selection(self):
        """Test that frequency takes precedence over recency."""
        analyzer = BlameAnalyzer(Mock())
        
        # Commit abc123: older but more frequent
        # Commit def456: newer but less frequent  
        commit_counts = {'abc123': 4, 'def456': 1}
        commit_dates = {'abc123': '2023-01-01', 'def456': '2023-12-01'}
        
        target = analyzer._select_target_commit(commit_counts, commit_dates)
        
        # Should select most frequent, not most recent
        assert target == 'abc123'
```

### Test Fixtures

#### Repository Fixtures (`conftest.py`)

```python
import pytest
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

class GitRepoFixture:
    """Helper class for managing test git repositories."""
    
    def __init__(self, path: Path):
        self.path = path
        self._setup_git_config()
    
    def _setup_git_config(self):
        """Configure git for testing."""
        subprocess.run([
            "git", "config", "user.email", "test@example.com"
        ], cwd=self.path, check=True)
        subprocess.run([
            "git", "config", "user.name", "Test User" 
        ], cwd=self.path, check=True)
    
    def create_file(self, filename: str, content: str) -> Path:
        """Create file with content."""
        file_path = self.path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return file_path
    
    def commit_file(self, filename: str, content: str, message: str) -> str:
        """Create file and commit it."""
        self.create_file(filename, content)
        subprocess.run(["git", "add", filename], cwd=self.path, check=True)
        subprocess.run([
            "git", "commit", "-m", message
        ], cwd=self.path, check=True)
        
        # Return commit hash
        result = subprocess.run([
            "git", "rev-parse", "HEAD"
        ], cwd=self.path, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    
    def stage_file(self, filename: str):
        """Stage file for commit."""
        subprocess.run(["git", "add", filename], cwd=self.path, check=True)

@pytest.fixture
def tmp_git_repo(tmp_path):
    """Create temporary git repository."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    
    subprocess.run(["git", "init"], cwd=repo_path, check=True)
    
    return GitRepoFixture(repo_path)

@pytest.fixture
def git_repo_with_history(tmp_git_repo):
    """Create git repository with commit history."""
    # Create initial commit
    tmp_git_repo.commit_file("README.md", "# Test Project", "Initial commit")
    
    # Create feature commits
    commits = []
    commits.append(tmp_git_repo.commit_file(
        "src/auth.py", 
        "def authenticate(user): pass",
        "Add authentication module"
    ))
    commits.append(tmp_git_repo.commit_file(
        "src/ui.py",
        "def render_login(): pass", 
        "Add login UI"
    ))
    commits.append(tmp_git_repo.commit_file(
        "src/auth.py",
        "def authenticate(user): return validate(user)",
        "Fix authentication logic"
    ))
    
    tmp_git_repo.commits = commits
    return tmp_git_repo

@pytest.fixture
def git_repo_with_changes(git_repo_with_history):
    """Repository with uncommitted changes."""
    # Modify existing files
    git_repo_with_history.create_file(
        "src/auth.py",
        "def authenticate(user): return validate_secure(user)"
    )
    git_repo_with_history.create_file(
        "src/new_module.py",
        "def new_feature(): pass"
    )
    
    return git_repo_with_history
```

## Integration Testing

### Full Workflow Tests

```python
class TestFullWorkflow:
    """Test complete git-autosquash workflows."""
    
    def test_basic_bug_fix_workflow(self, git_repo_with_changes):
        """Test bug fix gets squashed into original commit."""
        from git_autosquash.main import run_autosquash
        
        # Setup: Repository has bug fix in working directory
        # that should go back to original auth commit
        
        result = run_autosquash(
            git_repo_with_changes.path,
            line_by_line=False,
            approve_all=True  # Auto-approve for testing
        )
        
        assert result.success
        assert len(result.applied_mappings) > 0
        
        # Verify the fix was applied to the correct commit
        git_log = subprocess.run([
            "git", "log", "--oneline", "--grep=authentication"
        ], cwd=git_repo_with_changes.path, capture_output=True, text=True)
        
        # Auth commit should now contain the fix
        assert "validate_secure" in get_commit_content(
            git_repo_with_changes.path, 
            git_repo_with_changes.commits[0]
        )
    
    def test_mixed_changes_workflow(self, git_repo_with_changes):
        """Test mixed new features and bug fixes."""
        # Add both new feature and bug fix
        git_repo_with_changes.create_file("src/new_feature.py", "# New feature")
        
        result = run_autosquash(
            git_repo_with_changes.path,
            approve_all=True
        )
        
        # Bug fix should be squashed, new feature should remain
        assert result.success
        assert any(m.is_squashed for m in result.applied_mappings)
        assert any(not m.is_squashed for m in result.applied_mappings)
    
    def test_conflict_resolution_workflow(self, git_repo_with_conflicts):
        """Test handling of rebase conflicts."""
        result = run_autosquash(
            git_repo_with_conflicts.path,
            handle_conflicts=True  # Test automatic conflict resolution
        )
        
        # Should detect conflicts and provide resolution guidance
        assert not result.success  # Conflicts prevent completion
        assert len(result.conflicts) > 0
        assert result.conflict_resolution_steps  # Guidance provided
    
    def test_performance_large_repository(self, large_git_repo):
        """Test performance with large repository."""
        import time
        
        start_time = time.time()
        result = run_autosquash(large_git_repo.path)
        duration = time.time() - start_time
        
        # Performance requirements
        assert duration < 60.0  # Complete within 1 minute
        assert result.success
        assert len(result.processed_hunks) > 100  # Substantial work
```

### Complex Scenario Tests

```python
class TestComplexScenarios:
    """Test challenging real-world scenarios."""
    
    def test_security_fix_distribution(self, repo_with_security_issues):
        """Test security fixes distributed to multiple commits."""
        # Setup: Security fixes affect multiple historical commits
        security_fixes = [
            ("src/auth.py", "Fix SQL injection vulnerability"),
            ("src/ui.py", "Fix XSS vulnerability"),
            ("src/api.py", "Fix authentication bypass")
        ]
        
        for filename, _ in security_fixes:
            add_security_fix(repo_with_security_issues, filename)
        
        result = run_autosquash(
            repo_with_security_issues.path,
            line_by_line=True  # Precision for security
        )
        
        # Each fix should go to appropriate historical commit
        assert len(result.applied_mappings) == 3
        for mapping in result.applied_mappings:
            assert mapping.confidence > 0.7  # High confidence required
            assert mapping.target_commit in repo_with_security_issues.security_commits
    
    def test_refactoring_distribution(self, repo_with_refactoring):
        """Test refactoring improvements distributed correctly."""
        # Apply performance improvements across multiple files
        improvements = apply_performance_improvements(repo_with_refactoring)
        
        result = run_autosquash(
            repo_with_refactoring.path,
            line_by_line=True
        )
        
        # Improvements should go back to original implementations
        for improvement in improvements:
            mapping = find_mapping_for_file(result, improvement.filename)
            assert mapping.target_commit == improvement.original_commit
    
    def test_cross_cutting_concerns(self, repo_with_cross_cutting):
        """Test changes affecting multiple modules."""
        # Add logging improvements across all modules
        add_logging_improvements(repo_with_cross_cutting)
        
        result = run_autosquash(repo_with_cross_cutting.path)
        
        # Logging should be distributed to each module's original commit
        logging_mappings = [m for m in result.applied_mappings 
                          if "logging" in m.description.lower()]
        
        assert len(logging_mappings) > 3  # Multiple modules affected
        # Each should target different commits
        target_commits = {m.target_commit for m in logging_mappings}
        assert len(target_commits) > 1
```

## TUI Testing

### Widget Testing

```python
import pytest
from textual.app import App
from textual.widgets import Button

# NOTE: Legacy widgets removed - use modern interface components

class TestHunkMappingWidget:
    """Test hunk mapping widget behavior."""
    
    async def test_approval_toggle(self):
        """Test approval state toggling."""
        widget = HunkMappingWidget(test_mapping)
        
        # Initially not approved
        assert not widget.approved
        
        # Toggle approval
        await widget.action_toggle_approval()
        assert widget.approved
        
        # Toggle back
        await widget.action_toggle_approval()
        assert not widget.approved
    
    async def test_confidence_display(self):
        """Test confidence level display."""
        high_confidence = create_test_mapping(confidence=0.9)
        medium_confidence = create_test_mapping(confidence=0.6)
        low_confidence = create_test_mapping(confidence=0.3)
        
        high_widget = HunkMappingWidget(high_confidence)
        medium_widget = HunkMappingWidget(medium_confidence)
        low_widget = HunkMappingWidget(low_confidence)
        
        # Check confidence styling
        assert "high" in str(high_widget.confidence_style)
        assert "medium" in str(medium_widget.confidence_style)
        assert "low" in str(low_widget.confidence_style)

class TestDiffViewer:
    """Test diff viewer component."""
    
    async def test_syntax_highlighting(self):
        """Test syntax highlighting for different file types."""
        python_diff = create_python_diff()
        javascript_diff = create_javascript_diff()
        
        python_viewer = DiffViewer(python_diff)
        js_viewer = DiffViewer(javascript_diff)
        
        # Check syntax highlighting applied
        assert python_viewer.lexer_name == "python"
        assert js_viewer.lexer_name == "javascript"
    
    async def test_line_navigation(self):
        """Test navigation within diff content."""
        viewer = DiffViewer(large_diff_content)
        
        # Navigate to specific line
        await viewer.action_goto_line(50)
        assert viewer.current_line == 50
        
        # Navigate with keyboard
        await viewer.key_j()  # Down
        assert viewer.current_line == 51
        
        await viewer.key_k()  # Up  
        assert viewer.current_line == 50
```

### Screen Testing

```python
# NOTE: Legacy interfaces removed - use modern_app and modern_screens
from git_autosquash.tui.modern_app import ModernAutoSquashApp
from git_autosquash.tui.modern_screens import ModernSelectionScreen

class TestApprovalScreen:
    """Test approval screen interactions."""
    
    async def test_keyboard_navigation(self):
        """Test keyboard navigation between mappings."""
        mappings = create_test_mappings(5)
        screen = ApprovalScreen(mappings)
        
        # Navigate down
        await screen.key_j()
        await screen.key_j()
        assert screen.selected_index == 2
        
        # Navigate up
        await screen.key_k()
        assert screen.selected_index == 1
    
    async def test_bulk_approval(self):
        """Test bulk approval/rejection."""
        mappings = create_test_mappings(3)
        screen = ApprovalScreen(mappings)
        
        # Approve all
        await screen.key_a()
        
        approved = screen.get_approved_mappings()
        assert len(approved) == 3
        
        # Toggle all (should reject all)
        await screen.key_a()
        
        approved = screen.get_approved_mappings()
        assert len(approved) == 0
    
    async def test_execution_flow(self):
        """Test execution after approval."""
        mappings = create_test_mappings(2, auto_approve=True)
        screen = ApprovalScreen(mappings)
        
        # Execute
        result = await screen.action_execute()
        
        assert result is not None
        assert len(result) == 2  # Both mappings approved
        assert all(m.approved for m in result)

class TestAutoSquashApp:
    """Test main application flow."""
    
    async def test_app_initialization(self):
        """Test application starts correctly."""
        app = AutoSquashApp()
        
        # Should initialize with approval screen
        await app.startup()
        assert isinstance(app.current_screen, ApprovalScreen)
    
    async def test_error_handling(self):
        """Test error handling in TUI."""
        app = AutoSquashApp()
        
        # Simulate git error
        with patch('git_autosquash.git_ops.GitOps') as mock_git:
            mock_git.side_effect = GitError("Test error")
            
            await app.startup()
            
            # Should show error screen
            assert "error" in str(app.current_screen).lower()
```

## Performance Testing

### Scalability Tests

```python
class TestPerformance:
    """Test performance with various repository sizes."""
    
    def test_small_repository_performance(self, small_repo):
        """Test performance with small repository (< 100 commits)."""
        start_time = time.time()
        result = run_autosquash(small_repo.path)
        duration = time.time() - start_time
        
        assert duration < 5.0  # Should complete in under 5 seconds
        assert result.success
    
    def test_medium_repository_performance(self, medium_repo):
        """Test performance with medium repository (100-1000 commits).""" 
        start_time = time.time()
        result = run_autosquash(medium_repo.path)
        duration = time.time() - start_time
        
        assert duration < 30.0  # Should complete in under 30 seconds
        assert result.success
    
    def test_large_repository_performance(self, large_repo):
        """Test performance with large repository (1000+ commits)."""
        start_time = time.time()
        result = run_autosquash(large_repo.path)
        duration = time.time() - start_time
        
        assert duration < 120.0  # Should complete in under 2 minutes
        assert result.success
    
    def test_memory_usage(self, large_repo):
        """Test memory usage remains reasonable."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        result = run_autosquash(large_repo.path)
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be reasonable (< 500MB)
        assert memory_increase < 500 * 1024 * 1024
        assert result.success
```

## Running Tests

### Local Testing

```bash
# Run all tests
uv run pytest

# Run specific test categories  
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/tui/
uv run pytest tests/performance/

# Run with coverage
uv run pytest --cov=src/git_autosquash --cov-report=html

# Run tests in parallel
uv run pytest -n auto

# Run tests with verbose output
uv run pytest -v

# Run specific test
uv run pytest tests/unit/test_blame_analyzer.py::TestBlameAnalyzer::test_confidence_calculation
```

### Continuous Integration

Tests are automatically run on:
- All pull requests
- Pushes to main branch
- Multiple Python versions (3.9, 3.10, 3.11, 3.12)
- Multiple operating systems (Ubuntu, macOS, Windows)

### Test Coverage Goals

- **Unit tests**: 95% code coverage
- **Integration tests**: Cover all major workflows
- **TUI tests**: Cover all user interactions
- **Performance tests**: Validate scalability requirements
- **Regression tests**: Lock in all bug fixes

The comprehensive test suite ensures git-autosquash remains reliable and performant across diverse git repository scenarios and user workflows.