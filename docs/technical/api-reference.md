# API Reference

This section provides detailed API documentation for git-autosquash's core components. The documentation is auto-generated from docstrings to ensure accuracy.

## Core Components

### GitOps

The central interface for all Git operations with proper error handling.

::: git_autosquash.git_ops
    options:
      show_root_heading: true
      show_source: true
      heading_level: 4

### HunkParser

Parses Git diff output into structured hunk objects.

::: git_autosquash.hunk_parser
    options:
      show_root_heading: true
      show_source: true
      heading_level: 4

### BlameAnalyzer

Analyzes Git blame information to determine target commits for hunks.

::: git_autosquash.blame_analyzer
    options:
      show_root_heading: true
      show_source: true
      heading_level: 4

### RebaseManager

Orchestrates interactive rebase operations to apply approved hunks.

::: git_autosquash.rebase_manager
    options:
      show_root_heading: true
      show_source: true
      heading_level: 4

## CLI Entry Point

### Main

Command-line interface and entry point for git-autosquash.

::: git_autosquash.main
    options:
      show_root_heading: true
      show_source: true
      heading_level: 4

## TUI Components

### AutoSquashApp

Main Textual application for the interactive approval workflow.

::: git_autosquash.tui.app
    options:
      show_root_heading: true
      show_source: true
      heading_level: 4

### ApprovalScreen

Interactive screen for reviewing and approving hunk to commit mappings.

::: git_autosquash.tui.screens
    options:
      show_root_heading: true
      show_source: true
      heading_level: 4

### Widgets

Custom widgets for the TUI interface.

::: git_autosquash.tui.widgets
    options:
      show_root_heading: true
      show_source: true
      heading_level: 4

## Usage Examples

### Basic API Usage

Here's how to use the core components programmatically:

```python
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.blame_analyzer import BlameAnalyzer

# Initialize components
git_ops = GitOps(".")
hunk_parser = HunkParser(git_ops)
blame_analyzer = BlameAnalyzer(git_ops, "main")

# Get diff hunks
hunks = hunk_parser.get_diff_hunks()

# Analyze hunks to find target commits
mappings = blame_analyzer.analyze_hunks(hunks)

# Print results
for mapping in mappings:
    print(f"{mapping.hunk.file_path}: {mapping.target_commit} ({mapping.confidence})")
```

### Custom TUI Integration

```python
from git_autosquash.tui.app import AutoSquashApp

# Create custom TUI with your mappings
app = AutoSquashApp(mappings)
approved = app.run()

if approved and app.approved_mappings:
    print(f"User approved {len(app.approved_mappings)} hunks")
    # Process approved mappings...
```

### Rebase Execution

```python
from git_autosquash.rebase_manager import RebaseManager, RebaseConflictError

try:
    rebase_manager = RebaseManager(git_ops, merge_base)
    success = rebase_manager.execute_squash(approved_mappings)
    
    if success:
        print("Squash operation completed successfully!")
    else:
        print("Operation was cancelled by user")
        
except RebaseConflictError as e:
    print(f"Conflicts in: {', '.join(e.conflicted_files)}")
    # Handle conflicts...
```

## Type Definitions

### Common Types

```python
from typing import List, Dict, Optional, Set

# Confidence levels
ConfidenceLevel = Literal["high", "medium", "low"]

# Working tree status
WorkingTreeStatus = Dict[str, bool]  # {"is_clean": bool, "has_staged": bool, "has_unstaged": bool}

# Rebase status information
RebaseStatus = Dict[str, Any]  # {"in_progress": bool, "conflicted_files": List[str], ...}
```

### Error Types

All components raise specific exception types for different error conditions:

- **GitOps**: `subprocess.SubprocessError` for Git command failures
- **HunkParser**: `ValueError` for parsing errors
- **BlameAnalyzer**: `subprocess.SubprocessError` for blame failures  
- **RebaseManager**: `RebaseConflictError` for merge conflicts
- **TUI**: Standard Textual exceptions for interface errors

## Configuration Options

### Environment Variables

git-autosquash respects these environment variables:

- `GIT_SEQUENCE_EDITOR`: Custom editor for interactive rebase (automatically managed)
- `TERM`: Terminal type for TUI rendering
- `NO_COLOR`: Disable colored output when set

### Git Configuration

The following Git configuration affects git-autosquash behavior:

- `core.editor`: Default editor for conflict resolution
- `merge.tool`: Merge tool for resolving conflicts
- `rebase.autoStash`: Automatic stashing during rebase (overridden by git-autosquash)

## Performance Considerations

### Caching

Several operations are cached for performance:

- **Branch commits**: Expensive `git rev-list` operations
- **Commit timestamps**: `git show` calls for chronological ordering
- **Commit summaries**: `git log` output for display

### Memory Usage

- **Diff parsing**: Streams large diffs to avoid memory issues
- **Blame analysis**: Processes hunks individually to limit memory usage
- **TUI rendering**: Efficient widget updates and syntax highlighting

### Git Operation Optimization

- **Batch operations**: Groups related Git commands where possible
- **Subprocess management**: Proper timeout and resource cleanup
- **Working directory**: Minimal file I/O and temporary file usage

## Testing the API

The API components are extensively tested. To run tests for specific components:

```bash
# Test specific components
uv run pytest tests/test_git_ops.py -v
uv run pytest tests/test_hunk_parser.py -v
uv run pytest tests/test_blame_analyzer.py -v
uv run pytest tests/test_rebase_manager.py -v

# Test with coverage
uv run pytest --cov=git_autosquash tests/
```

## Contributing to the API

When extending the API:

1. **Follow existing patterns**: Maintain consistency with current design
2. **Add comprehensive docstrings**: Use Google style docstrings
3. **Include type annotations**: Full typing for all public methods
4. **Write tests**: Unit tests with appropriate mocking
5. **Update documentation**: This reference updates automatically from docstrings