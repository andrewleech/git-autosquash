# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Architecture

### Component Hierarchy
The application follows a layered architecture with three main execution strategies:

1. **GitNativeHandler** (src/git_autosquash/git_native_handler.py) - Simple in-place git operations
2. **GitNativeCompleteHandler** (src/git_autosquash/git_native_complete_handler.py) - Full rebase completion with reflog safety
3. **GitWorktreeHandler** (src/git_autosquash/git_worktree_handler.py) - Isolated worktree operations for complex scenarios

Each strategy extends **CliStrategy** base class and implements the execution flow differently based on complexity and safety requirements.

### Key Component Interactions

```
main.py (entry point)
  ├── GitOps (git command wrapper)
  ├── HunkParser (diff parsing)
  ├── HunkTargetResolver (blame + fallback analysis)
  │   ├── BlameAnalysisEngine
  │   ├── FallbackTargetProvider
  │   └── FileConsistencyTracker
  ├── TUI Components (Textual interface)
  │   ├── EnhancedApp (fallback scenarios)
  │   └── AutoSquashApp (standard flow)
  └── Strategy Execution (rebase management)
```

### Performance & Security Infrastructure

- **BatchGitOperations** (batch_git_ops.py): Eliminates O(n) subprocess calls through batch loading
- **BoundedCache** (bounded_cache.py): Thread-safe LRU caches with configurable size limits
- **Path Security**: Symlink detection and path traversal protection in main.py

## Development Commands

```bash
# Install development environment
uv pip install -e .
uv sync --dev

# Run tests
uv run pytest tests/                    # All tests
uv run pytest tests/test_main.py -v    # Single test file
uv run pytest -k "test_function_name"   # Specific test

# Linting and formatting (pre-commit runs these automatically)
uv run ruff check src/                  # Linting
uv run ruff format src/                 # Format code
uv run mypy src/                        # Type checking

# Pre-commit hooks
uv run pre-commit install               # Setup hooks (once after clone)
uv run pre-commit run --all-files      # Manual run

# Build and release
uv build                                # Build package
uv run twine check dist/*              # Validate package

# Documentation
uv run mkdocs serve                     # Local docs server
uv run mkdocs build                     # Build docs
```

## Test Execution Patterns

```bash
# Performance benchmarks
uv run pytest tests/test_performance_benchmarks.py -v

# Security edge cases
uv run pytest tests/test_security_edge_cases.py

# Integration tests with real git repos
uv run pytest tests/test_main_integration.py

# TUI component tests
uv run pytest tests/test_tui_widgets.py
```

## Critical Implementation Details

### Fallback Target Resolution
When blame analysis fails to find valid targets, the system provides fallback methods:
- **FALLBACK_NEW_FILE**: For new files, offers recent commits or ignore option
- **FALLBACK_EXISTING_FILE**: For existing files without blame matches, offers commits that touched the file
- **FALLBACK_CONSISTENCY**: Subsequent hunks from same file use same target as previous hunks

### Rebase Safety Mechanisms
1. **Reflog tracking**: All operations tracked with descriptive messages
2. **Atomic operations**: State checks before any modifications
3. **Rollback support**: Clear abort paths at every stage
4. **Conflict handling**: Pause/resume/abort with user guidance

### TUI State Management
- **UIStateController**: Centralized state for approval/ignore status
- **Message passing**: Widgets communicate via Textual messages
- **O(1) lookups**: Hashable HunkTargetMapping for efficient widget mapping

### Git Command Execution
- Always use GitOps wrapper, never raw subprocess calls
- Capture both stdout and stderr for proper error handling
- Check return codes and handle failures gracefully
- Use batch operations when processing multiple items

## Common Development Tasks

### Adding a New Execution Strategy
1. Extend `CliStrategy` base class
2. Implement `execute()` method with strategy-specific logic
3. Add to strategy selection in `main.py`
4. Create corresponding tests in `tests/`

### Modifying TUI Components
1. Enhanced UI components are in `tui/enhanced_*` files for fallback scenarios
2. Standard UI components are in `tui/app.py`, `tui/screens.py`, `tui/widgets.py`
3. Use proper Textual CSS variables ($warning, $success, etc.), not hardcoded colors
4. Follow widget composition patterns, avoid manual widget construction

### Working with Git Operations
1. Use `BatchGitOperations` for multiple git commands to avoid O(n) subprocess overhead
2. Implement proper caching with `BoundedCache` classes to prevent memory growth
3. Always validate paths for symlinks and traversal attacks
4. Handle both staged and unstaged changes appropriately

## Pre-commit Requirements

**CRITICAL**: Never use `git commit --no-verify`. All commits must pass:
- **ruff check**: Linting and code quality
- **ruff format**: Code formatting
- **mypy**: Static type checking

If pre-commit fails, fix the issues rather than bypassing. Pre-commit may modify files - review and stage these changes before committing again.

## Project Repository

GitHub: https://github.com/andrewleech/git-autosquash

CI/CD workflows:
- `.github/workflows/ci.yml`: Tests, linting, type checking
- `.github/workflows/release.yml`: PyPI deployment on tags
- `.github/workflows/docs.yml`: Documentation deployment