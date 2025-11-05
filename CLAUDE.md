# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Architecture

### Execution Strategy
The application uses a single split-commit approach for all hunk squashing operations:

1. **HunkCommitSplitter** (src/git_autosquash/hunk_commit_splitter.py) - Splits source commit into per-hunk temporary commits
2. **RebaseManager** (src/git_autosquash/rebase_manager.py) - Orchestrates cherry-pick and rebase operations
3. **Cherry-pick with 3-way merge** - Applies hunks reliably, handling complex cases like removing lines from the commit that added them

**Note:** The git_native_handler.py and git_native_complete_handler.py files are deprecated and not used in production code.

### Key Component Interactions

```
main.py (entry point)
  ├── GitOps (git command wrapper)
  ├── Validation Framework (Integrated - Phase 3 Complete)
  │   ├── SourceNormalizer (normalize inputs to commits)
  │   └── ProcessingValidator (end-to-end validation)
  ├── HunkCommitSplitter (split commits into per-hunk commits)
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
  └── RebaseManager (split-commit execution)
      ├── Cherry-pick split commits (primary)
      └── Patch-based fallback (if split fails)
```

### Validation Framework (Phase 3 Complete - Fully Integrated)

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

**Integration Status:** Fully integrated and production-ready. Merged in commit 3efa98c. See `docs/validation-framework-integration-analysis.md` for implementation details.

**Key Benefits:**
- **Single code path**: All inputs normalized before processing
- **Corruption detection**: Automatic detection via git diff
- **Better debugging**: Always have starting commit for comparison
- **Safer operations**: Validation catches data loss before completion

### File Deletion Support

git-autosquash supports file deletions (including empty files) as first-class operations:

**Implementation:**
- **HunkParser**: Detects `deleted file mode` markers and creates synthetic DiffHunk objects for empty file deletions
- **BlameAnalyzer**: Uses `git log --follow --diff-filter=A` to find the commit that added the file
- **RebaseManager**: Applies deletions using `git rm` during rebase operations
- **TUI**: Displays `[DELETED]` marker and shows deleted file content in preview
- **Validation**: Counts file deletions in pre-flight validation

**DiffHunk Fields:**
- `is_file_deletion`: Boolean flag indicating file deletion
- `deleted_file_mode`: File mode (e.g., "100644")
- `deleted_file_content`: Content from parent commit for TUI preview

**Target Resolution:**
File deletions are automatically targeted to the commit that added the file, with high confidence. This enables automatic squashing of file cleanup operations to their original addition commits.

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

# Man page testing
man -l man/git-autosquash.1             # Preview man page
groff -man -Tascii man/git-autosquash.1 # Validate troff syntax
unzip -l dist/*.whl | grep share/man    # Verify man page in wheel

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
- **pexpect/pyte-based approaches**: Legacy methods with timing and reliability issues

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

### Man Page Maintenance

Man page source: `man/git-autosquash.1` (troff format)

When updating CLI flags or behavior:
1. Update man page OPTIONS section to match `--help` output
2. Update EXAMPLES section if workflow changes
3. Update DESCRIPTION or HOW IT WORKS if algorithm changes
4. Test rendering: `man -l man/git-autosquash.1`
5. Validate syntax: `groff -man -Tascii man/git-autosquash.1`
6. Verify wheel includes it: `unzip -l dist/*.whl | grep share/man`

The man page is automatically installed by pipx via hatchling's shared-data configuration in `pyproject.toml`:
```toml
[tool.hatchling.build.targets.wheel.shared-data]
"man/git-autosquash.1" = "share/man/man1/git-autosquash.1"
```

## Split-Commit Execution Strategy

git-autosquash uses a single, consistent execution strategy for all operations:

### How It Works

1. **Source Normalization** (SourceNormalizer)
   - Converts all inputs (working-tree, index, HEAD, commits) to a single commit
   - Creates temporary commits with --no-verify for working-tree/index sources

2. **Commit Splitting** (HunkCommitSplitter)
   - Splits the source commit into separate temporary commits, one per hunk
   - Each split commit contains exactly one change
   - Creates temporary branch `git-autosquash-split-<hash>`

3. **Cherry-Pick Application** (RebaseManager)
   - For each approved hunk, cherry-picks its split commit using `git cherry-pick --no-commit`
   - Git's 3-way merge handles complex cases:
     - Removing lines from the commit that originally added them
     - Modifying lines across intervening commits
     - Automatic conflict resolution when safe
   - Falls back to patch-based approach only if split-commit fails

4. **Interactive Rebase** (RebaseManager)
   - Rebases through target commits chronologically
   - Amends each target commit with its hunks
   - Continues through all commits in single rebase operation

5. **Validation** (ProcessingValidator)
   - Post-flight `git diff` validation ensures no data corruption

6. **Cleanup**
   - Removes temporary split commits and branches
   - Removes temporary commits created by SourceNormalizer

### Why 3-Way Merge Works

Git's 3-way merge algorithm uses:
- **Base:** Common ancestor of source and target commits
- **Ours:** Target commit state (being amended)
- **Theirs:** Changes from split commit (hunk to apply)

This allows git to understand the full history context, not just text diffs, enabling
reliable application even when line numbers have changed or lines are being removed
from the commit that added them.

## Common Development Tasks

### Modifying the Split-Commit Approach
The split-commit approach is implemented in:
- `HunkCommitSplitter` (src/git_autosquash/hunk_commit_splitter.py) - Commit splitting logic
- `RebaseManager._apply_hunks_to_commit()` (src/git_autosquash/rebase_manager.py:632-732) - Cherry-pick execution
- `main.py process_hunks_and_mappings()` (src/git_autosquash/main.py:566-620) - Orchestration

Note: The split-commit approach is the only production code path. GitNativeCompleteHandler and GitNativeIgnoreHandler are deprecated and not used.

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