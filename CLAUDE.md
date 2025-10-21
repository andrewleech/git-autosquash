# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Architecture

### Component Hierarchy
The application follows a simplified architecture with index-based execution:

1. **GitNativeHandler** (src/git_autosquash/git_native_handler.py) - Simple in-place git operations
2. **GitNativeCompleteHandler** (src/git_autosquash/git_native_complete_handler.py) - Full rebase completion with reflog safety

The architecture has been simplified from the previous three-strategy approach. The worktree strategy has been removed as it provided no meaningful benefits over the index strategy while adding significant complexity.

### Key Component Interactions

```
main.py (entry point)
  ├── GitOps (git command wrapper)
  ├── Validation Framework (Integrated - Phase 3 Complete)
  │   ├── SourceNormalizer (normalize inputs to commits)
  │   └── ProcessingValidator (end-to-end validation)
  ├── HunkParser (diff parsing)
  ├── HunkTargetResolver (blame + fallback analysis)
  │   ├── BlameAnalysisEngine
  │   ├── FallbackTargetProvider
  │   └── FileConsistencyTracker
  ├── TUI Components (Textual interface)
  │   ├── ModernAutoSquashApp (3-panel workflow)
  │   ├── ModernApprovalScreen (main UI screen)
  │   ├── UIStateController (state management)
  │   └── UI Controllers (widget management)
  └── Strategy Execution (rebase management)
      ├── GitNativeCompleteHandler (orchestrator)
      └── GitNativeIgnoreHandler (index strategy)
```

### Validation Framework (Phase 2 Complete)

The validation framework provides strong safety guarantees against data corruption:

**SourceNormalizer** (src/git_autosquash/source_normalizer.py)
- Normalizes all input sources (working-tree, index, HEAD, commit refs) to a single commit
- Creates temporary commits with `--no-verify` for working-tree/index sources
- Stores parent SHA explicitly for safe cleanup
- Handles edge cases: empty diffs, detached HEAD, concurrent modifications
- 30 comprehensive tests covering all edge cases

**ProcessingValidator** (src/git_autosquash/validation.py)
- Pre-flight validation: `validate_hunk_count()` checks hunk counts match
- Post-flight validation: `validate_processing()` uses `git diff <start> <end>` to guarantee no corruption
- Provides detailed error messages with recovery instructions
- Works correctly in detached HEAD state
- 22 comprehensive tests covering all validation scenarios

**Integration Status:** Phase 2 complete, Phase 3 integration pending. See `docs/validation-framework-integration-analysis.md` for integration plan.

**Key Benefits:**
- **Single code path**: All inputs normalized before processing
- **Corruption detection**: Automatic detection via git diff
- **Better debugging**: Always have starting commit for comparison
- **Safer operations**: Validation catches data loss before completion

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

# Screenshot generation
python scripts/generate_screenshots.py  # Generate all screenshots
python scripts/generate_screenshots.py --hero-only  # Hero only
```

## Screenshot Generation

**OFFICIAL APPROACH**: Use `scripts/generate_screenshots.py` for all screenshot generation.

This is the recommended and supported method for capturing screenshots of the git-autosquash TUI. It uses Textual's built-in screenshot capabilities (`app.run_test()` with Pilot) to generate character-perfect SVG screenshots.

### Why Textual's Native Screenshots?

- **Character-accurate**: Captures Textual's internal rendering, not terminal emulation
- **High quality**: SVG output is scalable and perfect for documentation
- **Reliable**: No cursor positioning issues that plague terminal capture tools
- **Programmatic**: Full control over app state and interactions
- **Maintainable**: Uses official Textual testing framework

### Do NOT Use:

- **termshot**: Has known cursor positioning issues that break with complex TUI apps like Textual
- **pexpect** (tests/pexpect_screenshot_capture.py): Legacy approach, replaced by Textual native
- **pyte** (tests/pyte_screenshot_capture.py): Legacy approach with timing issues
- **capture_readme_screenshots.py**: Legacy wrapper around pexpect, superseded by new script

### Usage Examples:

```bash
# Generate all screenshots (hero + workflow)
python scripts/generate_screenshots.py

# Generate only hero screenshot for quick testing
python scripts/generate_screenshots.py --hero-only

# Custom output directory
python scripts/generate_screenshots.py --output-dir docs/images

# Custom terminal size
python scripts/generate_screenshots.py --width 140 --height 50
```

### Programmatic Usage:

```python
from scripts.generate_screenshots import TextualScreenshotGenerator

async def capture_custom_screenshot():
    generator = TextualScreenshotGenerator(
        output_dir=Path("screenshots"),
        terminal_size=(120, 40)
    )

    # Capture with custom interactions
    await generator.capture_app_screenshot(
        name="my_screenshot",
        interactions=[
            {"type": "wait", "duration": 1.0},
            {"type": "key", "keys": ["j", "space", "tab"]},
            {"type": "wait", "duration": 0.5},
        ]
    )

    generator.cleanup()
```

### Converting SVG to PNG:

If PNG format is needed for certain platforms:

```bash
# Using Inkscape
inkscape screenshot.svg --export-filename=screenshot.png --export-width=1920

# Using ImageMagick
convert -density 300 screenshot.svg screenshot.png

# Using cairosvg (Python)
cairosvg screenshot.svg -o screenshot.png -d 300
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

## Strategy Management Commands

git-autosquash includes hidden subcommands for managing execution strategies. These are not shown in the main help output to avoid confusing regular users, but are available for debugging and advanced configuration:

### `git-autosquash strategy-info`
**Purpose**: Display current strategy information and system capabilities
**Output**: Shows active strategy, available strategies, execution order, and environment overrides
**Use case**: Debugging strategy selection issues

### `git-autosquash strategy-test [--strategy STRATEGY]`
**Purpose**: Test strategy compatibility and functionality
**Options**:
- `--strategy index|legacy` - Test specific strategy (default: test all)
**Use case**: Troubleshooting git-autosquash failures, verifying system compatibility

### `git-autosquash strategy-set {index|legacy|auto}`
**Purpose**: Configure preferred execution strategy
**Strategies**:
- `index` - Index manipulation with stash backup (recommended, requires git 2.0+)
- `legacy` - Manual patch application (fallback for older git versions)
- `auto` - Remove override, use auto-detection (default)
**Effect**: Shows environment variable command to set strategy preference
**Use case**: Forcing specific strategy when auto-detection fails

### Implementation Notes
- These subcommands are implemented in `src/git_autosquash/cli_strategy.py`
- They are hidden from main help via `add_help=False` on the subparser
- The commands are fully functional but not advertised to end users
- Strategy selection happens automatically in `GitNativeCompleteHandler` based on git version and capabilities
- Most users should never need these commands - they're for advanced troubleshooting
- The worktree strategy has been removed due to architectural simplification

## Common Development Tasks

### Adding a New Execution Strategy
1. Extend the `GitNativeCompleteHandler` class
2. Implement strategy-specific logic in new handler classes
3. Add to strategy selection in `GitNativeCompleteHandler`
4. Create corresponding tests in `tests/`

Note: The architecture now uses a simplified index-based approach. Consider whether additional complexity is truly necessary before adding new strategies.

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