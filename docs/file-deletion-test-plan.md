# File Deletion Support - Test Coverage Plan

## Overview
Comprehensive test strategy for file deletion features added to git-autosquash. Tests should be added across multiple test files to maintain organizational structure.

## Test Organization

### 1. Unit Tests: test_hunk_parser.py

#### TestDiffHunk - File Deletion Properties
```python
def test_file_deletion_flag_defaults_false():
    """Test is_file_deletion defaults to False for regular hunks."""
    hunk = DiffHunk(
        file_path="test.py",
        old_start=1, old_count=1, new_start=1, new_count=1,
        lines=["@@ -1,1 +1,1 @@", "-old", "+new"],
        context_before=[], context_after=[]
    )
    assert hunk.is_file_deletion is False
    assert hunk.deleted_file_mode is None
    assert hunk.deleted_file_content is None

def test_file_deletion_flag_true():
    """Test is_file_deletion=True with metadata."""
    hunk = DiffHunk(
        file_path="empty.txt",
        old_start=0, old_count=0, new_start=0, new_count=0,
        lines=[],
        context_before=[], context_after=[],
        is_file_deletion=True,
        deleted_file_mode="100644",
        deleted_file_content=""
    )
    assert hunk.is_file_deletion is True
    assert hunk.deleted_file_mode == "100644"
    assert hunk.deleted_file_content == ""

def test_file_deletion_has_deletions_property():
    """Test has_deletions works correctly for file deletions with content."""
    hunk = DiffHunk(
        file_path="file.txt",
        old_start=1, old_count=3, new_start=0, new_count=0,
        lines=["@@ -1,3 +0,0 @@", "-line1", "-line2", "-line3"],
        context_before=[], context_after=[],
        is_file_deletion=True,
        deleted_file_mode="100644"
    )
    assert hunk.is_file_deletion is True
    assert hunk.has_deletions is True
    assert hunk.has_additions is False
```

#### TestHunkParser - Deletion Detection
```python
@patch.object(GitOps, "_run_git_command")
def test_parse_empty_file_deletion(mock_run):
    """Test parsing diff with empty file deletion."""
    diff_output = """diff --git a/empty.txt b/empty.txt
deleted file mode 100644
index e69de29..0000000
"""
    mock_run.return_value = (True, diff_output)

    parser = HunkParser(GitOps())
    hunks = parser.get_diff_hunks(from_commit="abc123")

    assert len(hunks) == 1
    assert hunks[0].is_file_deletion is True
    assert hunks[0].file_path == "empty.txt"
    assert hunks[0].deleted_file_mode == "100644"
    assert len(hunks[0].lines) == 0
    assert hunks[0].old_count == 0
    assert hunks[0].new_count == 0

@patch.object(GitOps, "_run_git_command")
def test_parse_nonempty_file_deletion(mock_run):
    """Test parsing diff with non-empty file deletion."""
    diff_output = """diff --git a/file.txt b/file.txt
deleted file mode 100644
index 9daeafb..0000000
--- a/file.txt
+++ /dev/null
@@ -1,3 +0,0 @@
-line 1
-line 2
-line 3
"""
    mock_run.return_value = (True, diff_output)

    parser = HunkParser(GitOps())
    hunks = parser.get_diff_hunks(from_commit="abc123")

    assert len(hunks) == 1
    assert hunks[0].is_file_deletion is True
    assert hunks[0].file_path == "file.txt"
    assert hunks[0].deleted_file_mode == "100644"
    assert len(hunks[0].lines) == 4  # Header + 3 deletion lines
    assert hunks[0].old_count == 3
    assert hunks[0].new_count == 0

@patch.object(GitOps, "_run_git_command")
def test_parse_mixed_deletions_and_modifications(mock_run):
    """Test parsing diff with both file deletions and regular hunks."""
    diff_output = """diff --git a/deleted.txt b/deleted.txt
deleted file mode 100644
index e69de29..0000000
diff --git a/modified.py b/modified.py
index abc123..def456 100644
--- a/modified.py
+++ b/modified.py
@@ -10,3 +10,3 @@
 context
-old line
+new line
 context
"""
    mock_run.return_value = (True, diff_output)

    parser = HunkParser(GitOps())
    hunks = parser.get_diff_hunks(from_commit="abc123")

    assert len(hunks) == 2
    # First hunk: file deletion
    assert hunks[0].is_file_deletion is True
    assert hunks[0].file_path == "deleted.txt"
    # Second hunk: regular modification
    assert hunks[1].is_file_deletion is False
    assert hunks[1].file_path == "modified.py"

@patch.object(GitOps, "_run_git_command")
def test_parse_multiple_file_deletions(mock_run):
    """Test parsing diff with multiple file deletions."""
    diff_output = """diff --git a/empty1.txt b/empty1.txt
deleted file mode 100644
index e69de29..0000000
diff --git a/empty2.txt b/empty2.txt
deleted file mode 100644
index e69de29..0000000
"""
    mock_run.return_value = (True, diff_output)

    parser = HunkParser(GitOps())
    hunks = parser.get_diff_hunks(from_commit="abc123")

    assert len(hunks) == 2
    assert all(h.is_file_deletion for h in hunks)
    assert hunks[0].file_path == "empty1.txt"
    assert hunks[1].file_path == "empty2.txt"

@patch.object(GitOps, "_run_git_command")
def test_deleted_file_content_retrieval(mock_run):
    """Test that deleted file content is retrieved for preview."""
    # First call: diff output
    # Second call: show parent:file for content
    diff_output = """diff --git a/file.txt b/file.txt
deleted file mode 100644
index e69de29..0000000
"""
    mock_run.side_effect = [
        (True, diff_output),
        (True, "deleted content\nline 2\n")  # Content retrieval
    ]

    parser = HunkParser(GitOps())
    hunks = parser.get_diff_hunks(from_commit="abc123")

    assert len(hunks) == 1
    assert hunks[0].deleted_file_content == "deleted content\nline 2\n"
    # Verify second call was made with correct args
    assert mock_run.call_count == 2
    assert "abc123~1:file.txt" in mock_run.call_args_list[1][0]

@patch.object(GitOps, "_run_git_command")
def test_deleted_file_content_truncation_large_file(mock_run):
    """Test that large deleted files are truncated to prevent memory issues."""
    diff_output = """diff --git a/large.txt b/large.txt
deleted file mode 100644
index e69de29..0000000
"""
    # Create 200KB of content (should be truncated to 100KB)
    large_content = "x" * (200 * 1024)

    mock_run.side_effect = [
        (True, diff_output),
        (True, large_content)
    ]

    parser = HunkParser(GitOps())
    hunks = parser.get_diff_hunks(from_commit="abc123")

    assert len(hunks) == 1
    content = hunks[0].deleted_file_content
    assert content is not None
    assert len(content) < len(large_content)
    assert "[Content truncated" in content

@patch.object(GitOps, "_run_git_command")
def test_deleted_file_content_retrieval_failure(mock_run):
    """Test graceful handling when deleted file content cannot be retrieved."""
    diff_output = """diff --git a/file.txt b/file.txt
deleted file mode 100644
index e69de29..0000000
"""
    mock_run.side_effect = [
        (True, diff_output),
        (False, "")  # Content retrieval fails
    ]

    parser = HunkParser(GitOps())
    hunks = parser.get_diff_hunks(from_commit="abc123")

    assert len(hunks) == 1
    assert hunks[0].deleted_file_content is None  # Fails gracefully
```

### 2. Unit Tests: test_blame_analyzer.py

#### TestBlameAnalyzer - File Deletion Targeting
```python
@patch.object(GitOps, "_run_git_command")
@patch.object(BlameAnalyzer, "_get_branch_commits")
def test_file_deletion_targets_addition_commit(mock_branch, mock_run):
    """Test that file deletions are targeted to the commit that added the file."""
    mock_branch.return_value = {"commit1", "commit2", "commit3"}

    # Mock git log output finding the addition commit
    mock_run.return_value = (True, "commit2\n")

    git_ops = Mock(spec=GitOps)
    git_ops._run_git_command = mock_run
    analyzer = BlameAnalyzer(git_ops, "merge_base", "HEAD")

    hunk = DiffHunk(
        file_path="deleted.txt",
        old_start=0, old_count=0, new_start=0, new_count=0,
        lines=[],
        context_before=[], context_after=[],
        is_file_deletion=True,
        deleted_file_mode="100644"
    )

    mapping = analyzer._analyze_single_hunk(hunk)

    assert mapping.target_commit == "commit2"
    assert mapping.targeting_method.value == "file_deletion"
    assert mapping.confidence == "high"
    assert mapping.needs_user_selection is False

@patch.object(GitOps, "_run_git_command")
def test_find_file_addition_commit_with_follow(mock_run):
    """Test _find_file_addition_commit uses --follow for renamed files."""
    mock_run.return_value = (True, "commit1\ncommit2\n")

    git_ops = Mock(spec=GitOps)
    git_ops._run_git_command = mock_run
    analyzer = BlameAnalyzer(git_ops, "base", "HEAD")

    result = analyzer._find_file_addition_commit("file.txt")

    assert result == "commit2"  # Oldest (last) commit
    # Verify --follow flag was used
    call_args = mock_run.call_args[0]
    assert "log" in call_args
    assert "--follow" in call_args
    assert "--diff-filter=A" in call_args

@patch.object(GitOps, "_run_git_command")
def test_find_file_addition_commit_not_found(mock_run):
    """Test _find_file_addition_commit returns None when file not found."""
    mock_run.return_value = (True, "")

    git_ops = Mock(spec=GitOps)
    git_ops._run_git_command = mock_run
    analyzer = BlameAnalyzer(git_ops, "base", "HEAD")

    result = analyzer._find_file_addition_commit("nonexistent.txt")

    assert result is None

@patch.object(GitOps, "_run_git_command")
def test_find_file_addition_commit_git_failure(mock_run):
    """Test _find_file_addition_commit handles git command failure."""
    mock_run.return_value = (False, "")

    git_ops = Mock(spec=GitOps)
    git_ops._run_git_command = mock_run
    analyzer = BlameAnalyzer(git_ops, "base", "HEAD")

    result = analyzer._find_file_addition_commit("file.txt")

    assert result is None

@patch.object(BlameAnalyzer, "_find_file_addition_commit")
@patch.object(BlameAnalyzer, "_get_branch_commits")
def test_file_deletion_falls_back_when_addition_not_found(mock_branch, mock_find):
    """Test fallback when file addition commit cannot be found."""
    mock_branch.return_value = {"commit1"}
    mock_find.return_value = None

    git_ops = Mock(spec=GitOps)
    analyzer = BlameAnalyzer(git_ops, "base", "HEAD")

    hunk = DiffHunk(
        file_path="deleted.txt",
        old_start=0, old_count=0, new_start=0, new_count=0,
        lines=[],
        context_before=[], context_after=[],
        is_file_deletion=True,
        deleted_file_mode="100644"
    )

    mapping = analyzer._analyze_single_hunk(hunk)

    assert mapping.targeting_method.value == "fallback_existing_file"
    assert mapping.needs_user_selection is True
```

### 3. Unit Tests: test_rebase_manager.py

#### TestRebaseManager - File Deletion Application
```python
def test_apply_hunks_with_file_deletion():
    """Test _apply_hunks_to_commit handles file deletions with git rm."""
    git_ops = Mock(spec=GitOps)
    # Mock git ls-files to confirm file exists
    # Mock git rm to succeed
    ls_result = Mock(returncode=0, stdout="", stderr="")
    rm_result = Mock(returncode=0, stdout="", stderr="")
    git_ops.run_git_command.side_effect = [ls_result, rm_result]

    manager = RebaseManager(git_ops, "merge_base")

    hunk = DiffHunk(
        file_path="deleted.txt",
        old_start=0, old_count=0, new_start=0, new_count=0,
        lines=[],
        context_before=[], context_after=[],
        is_file_deletion=True,
        deleted_file_mode="100644"
    )

    # Mock the rebase setup
    with patch.object(manager, "_start_rebase_edit", return_value=True):
        with patch.object(manager, "_amend_commit"):
            with patch.object(manager, "_continue_rebase"):
                result = manager._apply_hunks_to_commit(
                    "target_commit",
                    [hunk],
                    ["split_commit"]
                )

    assert result is True
    # Verify git rm was called
    rm_call = [c for c in git_ops.run_git_command.call_args_list
               if "rm" in c[0][0]]
    assert len(rm_call) == 1
    assert "deleted.txt" in rm_call[0][0][0]

def test_apply_hunks_file_already_deleted():
    """Test idempotent handling when file already deleted."""
    git_ops = Mock(spec=GitOps)
    # Mock git ls-files to indicate file doesn't exist
    ls_result = Mock(returncode=1, stdout="", stderr="error: pathspec")
    git_ops.run_git_command.return_value = ls_result

    manager = RebaseManager(git_ops, "merge_base")

    hunk = DiffHunk(
        file_path="deleted.txt",
        old_start=0, old_count=0, new_start=0, new_count=0,
        lines=[],
        context_before=[], context_after=[],
        is_file_deletion=True,
        deleted_file_mode="100644"
    )

    with patch.object(manager, "_start_rebase_edit", return_value=True):
        with patch.object(manager, "_amend_commit"):
            with patch.object(manager, "_continue_rebase"):
                result = manager._apply_hunks_to_commit(
                    "target_commit",
                    [hunk],
                    ["split_commit"]
                )

    assert result is True
    # Verify git rm was NOT called (file already gone)
    rm_calls = [c for c in git_ops.run_git_command.call_args_list
                if len(c[0]) > 0 and "rm" in c[0][0]]
    assert len(rm_calls) == 0

def test_apply_hunks_misaligned_lists():
    """Test assertion catches misalignment between split_commits and hunks."""
    git_ops = Mock(spec=GitOps)
    manager = RebaseManager(git_ops, "merge_base")

    hunks = [Mock(spec=DiffHunk), Mock(spec=DiffHunk)]
    split_commits = ["commit1"]  # Mismatched length

    with patch.object(manager, "_start_rebase_edit", return_value=True):
        with pytest.raises(subprocess.SubprocessError) as exc_info:
            manager._apply_hunks_to_commit("target", hunks, split_commits)

    assert "mismatch" in str(exc_info.value).lower()

def test_apply_mixed_deletions_and_modifications():
    """Test applying both file deletions and regular hunks in same commit."""
    git_ops = Mock(spec=GitOps)
    ls_result = Mock(returncode=0)
    rm_result = Mock(returncode=0)
    cherry_result = Mock(returncode=0)
    git_ops.run_git_command.side_effect = [
        ls_result, rm_result,  # File deletion
        cherry_result  # Regular hunk
    ]

    manager = RebaseManager(git_ops, "merge_base")

    deletion_hunk = DiffHunk(
        file_path="deleted.txt", old_start=0, old_count=0,
        new_start=0, new_count=0, lines=[],
        context_before=[], context_after=[],
        is_file_deletion=True, deleted_file_mode="100644"
    )

    regular_hunk = DiffHunk(
        file_path="modified.py", old_start=10, old_count=1,
        new_start=10, new_count=1,
        lines=["@@ -10,1 +10,1 @@", "-old", "+new"],
        context_before=[], context_after=[],
        is_file_deletion=False
    )

    with patch.object(manager, "_start_rebase_edit", return_value=True):
        with patch.object(manager, "_amend_commit"):
            with patch.object(manager, "_continue_rebase"):
                result = manager._apply_hunks_to_commit(
                    "target",
                    [deletion_hunk, regular_hunk],
                    ["split1", "split2"]
                )

    assert result is True
    # Verify both git rm and cherry-pick were called
    assert git_ops.run_git_command.call_count >= 3
```

### 4. Unit Tests: test_validation.py

#### TestProcessingValidator - File Deletion Counting
```python
def test_validate_hunk_count_with_empty_file_deletion():
    """Test hunk count validation includes empty file deletions."""
    git_ops = Mock(spec=GitOps)

    diff_output = """diff --git a/empty.txt b/empty.txt
deleted file mode 100644
index e69de29..0000000
"""

    result = Mock(returncode=0, stdout=diff_output, stderr="")
    git_ops.run_git_command.return_value = result

    validator = ProcessingValidator(git_ops)

    # One empty file deletion = 1 hunk
    hunks = [
        DiffHunk(
            file_path="empty.txt",
            old_start=0, old_count=0, new_start=0, new_count=0,
            lines=[],
            context_before=[], context_after=[],
            is_file_deletion=True,
            deleted_file_mode="100644"
        )
    ]

    # Should not raise
    validator.validate_hunk_count("abc123", hunks)

def test_validate_hunk_count_with_mixed_deletions():
    """Test hunk count with both empty file deletions and content hunks."""
    git_ops = Mock(spec=GitOps)

    diff_output = """diff --git a/empty.txt b/empty.txt
deleted file mode 100644
index e69de29..0000000
diff --git a/file.txt b/file.txt
deleted file mode 100644
index abc..def 100644
--- a/file.txt
+++ /dev/null
@@ -1,3 +0,0 @@
-line1
-line2
-line3
"""

    result = Mock(returncode=0, stdout=diff_output, stderr="")
    git_ops.run_git_command.return_value = result

    validator = ProcessingValidator(git_ops)

    # 1 empty file deletion + 1 content hunk = 2 hunks
    hunks = [
        DiffHunk(file_path="empty.txt", old_start=0, old_count=0,
                 new_start=0, new_count=0, lines=[],
                 context_before=[], context_after=[],
                 is_file_deletion=True, deleted_file_mode="100644"),
        DiffHunk(file_path="file.txt", old_start=1, old_count=3,
                 new_start=0, new_count=0,
                 lines=["@@ -1,3 +0,0 @@", "-line1", "-line2", "-line3"],
                 context_before=[], context_after=[],
                 is_file_deletion=True, deleted_file_mode="100644")
    ]

    # Should not raise
    validator.validate_hunk_count("abc123", hunks)

def test_validate_hunk_count_detects_missing_file_deletion():
    """Test validation fails when file deletion is missing from hunks."""
    git_ops = Mock(spec=GitOps)

    diff_output = """diff --git a/empty.txt b/empty.txt
deleted file mode 100644
index e69de29..0000000
"""

    result = Mock(returncode=0, stdout=diff_output, stderr="")
    git_ops.run_git_command.return_value = result

    validator = ProcessingValidator(git_ops)

    # Empty list - should detect mismatch
    hunks = []

    with pytest.raises(ValidationError) as exc_info:
        validator.validate_hunk_count("abc123", hunks)

    assert "mismatch" in str(exc_info.value).lower()
```

### 5. Integration Tests: test_file_deletion_integration.py (NEW FILE)

```python
"""Integration tests for file deletion support."""

import pytest
from pathlib import Path
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.blame_analyzer import BlameAnalyzer
from git_autosquash.rebase_manager import RebaseManager
from tests.conftest import temporary_test_repository


class TestFileDeletionIntegration:
    """End-to-end integration tests for file deletion features."""

    def test_empty_file_deletion_end_to_end(self):
        """Test complete flow: parse -> analyze -> apply for empty file deletion."""
        with temporary_test_repository("deletion_test") as repo:
            # Setup: create file, commit, delete, commit
            empty_file = repo / "empty.txt"
            empty_file.touch()

            git_ops = GitOps(str(repo))
            git_ops.run_git_command(["add", "empty.txt"])
            git_ops.run_git_command(["commit", "-m", "Add empty file"])

            addition_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            git_ops.run_git_command(["rm", "empty.txt"])
            git_ops.run_git_command(["commit", "-m", "Delete empty file"])

            deletion_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            # Parse deletion
            parser = HunkParser(git_ops)
            hunks = parser.get_diff_hunks(from_commit=deletion_sha)

            assert len(hunks) == 1
            assert hunks[0].is_file_deletion is True
            assert hunks[0].file_path == "empty.txt"

            # Analyze for target
            base = git_ops.run_git_command(
                ["rev-parse", f"{deletion_sha}~1"]
            ).stdout.strip()
            analyzer = BlameAnalyzer(git_ops, base, f"{deletion_sha}~1")
            mappings = analyzer.analyze_hunks(hunks)

            assert len(mappings) == 1
            assert mappings[0].target_commit == addition_sha
            assert mappings[0].targeting_method.value == "file_deletion"

    def test_nonempty_file_deletion_end_to_end(self):
        """Test complete flow for non-empty file deletion."""
        with temporary_test_repository("deletion_test") as repo:
            # Setup
            test_file = repo / "test.txt"
            test_file.write_text("line 1\nline 2\nline 3\n")

            git_ops = GitOps(str(repo))
            git_ops.run_git_command(["add", "test.txt"])
            git_ops.run_git_command(["commit", "-m", "Add test file"])

            addition_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            git_ops.run_git_command(["rm", "test.txt"])
            git_ops.run_git_command(["commit", "-m", "Delete test file"])

            deletion_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            # Parse and verify content is captured
            parser = HunkParser(git_ops)
            hunks = parser.get_diff_hunks(from_commit=deletion_sha)

            assert len(hunks) == 1
            assert hunks[0].is_file_deletion is True
            assert hunks[0].has_deletions is True
            assert "line 1" in "\n".join(hunks[0].lines)

    def test_binary_file_deletion(self):
        """Test deletion of binary files."""
        with temporary_test_repository("deletion_test") as repo:
            # Create binary file
            binary_file = repo / "binary.bin"
            binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

            git_ops = GitOps(str(repo))
            git_ops.run_git_command(["add", "binary.bin"])
            git_ops.run_git_command(["commit", "-m", "Add binary"])

            git_ops.run_git_command(["rm", "binary.bin"])
            git_ops.run_git_command(["commit", "-m", "Delete binary"])

            deletion_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            # Parse - should handle binary gracefully
            parser = HunkParser(git_ops)
            hunks = parser.get_diff_hunks(from_commit=deletion_sha)

            assert len(hunks) >= 1
            deletion_hunk = [h for h in hunks if h.file_path == "binary.bin"][0]
            assert deletion_hunk.is_file_deletion is True

    def test_performance_many_file_deletions(self):
        """Test performance with many file deletions in single commit."""
        with temporary_test_repository("deletion_test") as repo:
            git_ops = GitOps(str(repo))

            # Create 50 files
            for i in range(50):
                (repo / f"file{i}.txt").write_text(f"content {i}")

            git_ops.run_git_command(["add", "."])
            git_ops.run_git_command(["commit", "-m", "Add 50 files"])

            # Delete all
            for i in range(50):
                git_ops.run_git_command(["rm", f"file{i}.txt"])

            git_ops.run_git_command(["commit", "-m", "Delete all files"])
            deletion_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            # Parse - should complete in reasonable time
            import time
            start = time.time()

            parser = HunkParser(git_ops)
            hunks = parser.get_diff_hunks(from_commit=deletion_sha)

            elapsed = time.time() - start

            assert len(hunks) == 50
            assert all(h.is_file_deletion for h in hunks)
            assert elapsed < 5.0  # Should complete in under 5 seconds
```

## Test Execution Priority

1. **Critical (Must have before merge):**
   - Empty file deletion parsing
   - Non-empty file deletion parsing
   - File addition commit discovery
   - Memory truncation for large files
   - Hunk count validation

2. **Important (Should have soon):**
   - Mixed deletions and modifications
   - Multiple file deletions
   - Rebase application of deletions
   - Idempotent deletion handling

3. **Nice to have:**
   - Binary file deletion
   - Performance with many deletions
   - Renamed file deletion tracking

## Test Coverage Metrics

Target coverage for new code:
- `hunk_parser.py` deletion code: 95%+
- `blame_analyzer.py` `_find_file_addition_commit()`: 90%+
- `rebase_manager.py` deletion handling: 90%+
- `validation.py` deletion counting: 95%+

## Running Tests

```bash
# Run all file deletion tests
pytest tests/test_hunk_parser.py::TestDiffHunk -k deletion
pytest tests/test_hunk_parser.py::TestHunkParser -k deletion
pytest tests/test_blame_analyzer.py -k file_deletion
pytest tests/test_rebase_manager.py -k deletion
pytest tests/test_validation.py -k deletion
pytest tests/test_file_deletion_integration.py -v

# Run with coverage
pytest --cov=git_autosquash --cov-report=term-missing tests/test_file_deletion_integration.py
```
