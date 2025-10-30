# git-autosquash

[![Tests](https://github.com/andrewleech/git-autosquash/actions/workflows/ci.yml/badge.svg)](https://github.com/andrewleech/git-autosquash/actions/workflows/ci.yml)
[![Documentation](https://github.com/andrewleech/git-autosquash/actions/workflows/docs.yml/badge.svg)](https://andrewleech.github.io/git-autosquash/)
[![PyPI version](https://badge.fury.io/py/git-autosquash.svg)](https://badge.fury.io/py/git-autosquash)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**Automatically squash changes back into historical commits where they belong.**

git-autosquash eliminates "cleanup" commits by analyzing git blame to determine which historical commits should receive your current changes. Instead of accumulating "fix lint", "address PR feedback", or "update tests" commits, it distributes improvements back to their logical origin points.

![git-autosquash Interactive TUI](screenshots/readme/hero_screenshot.png)

## What It Does

- Analyzes your working directory changes using git blame
- Maps each change to the commit that last modified those lines
- Presents an interactive interface for review and approval
- Executes git rebase to squash changes into target commits
- Maintains clean, logical git history

## Why You Need It

Common scenario: You're working on a feature branch and need to address code review feedback, fix lint errors, or update tests across multiple files. Instead of creating noisy cleanup commits, git-autosquash pushes each fix back to the commit that originally introduced the code.

**Before**: Messy history with fix commits
```
* fix lint errors in auth module
* address PR feedback on validation
* update tests for new API
* feat: implement user authentication
* feat: add input validation
* feat: update user API
```

**After**: Clean history with integrated improvements
```
* feat: implement user authentication (includes lint fixes)
* feat: add input validation (includes PR feedback)
* feat: update user API (includes test updates)
```

## Installation

```bash
# Recommended: Install with uv (fastest, modern Python package manager)
uv tool install git-autosquash

# Or with pipx for isolated environment
pipx install git-autosquash

# Or with pip
pip install git-autosquash
```

## Usage

```bash
# Interactive mode (default): Review and approve changes in TUI
git-autosquash

# Auto-accept mode: Skip TUI for high-confidence targets
git-autosquash --auto-accept

# Dry-run mode: Preview what would be done without making changes
git-autosquash --auto-accept --dry-run

# Line-by-line precision mode
git-autosquash --line-by-line
```

## How It Works

git-autosquash uses a split-commit approach with git's 3-way merge for reliable hunk squashing:

### 1. Blame Analysis
Traces each modified line back to the commit that last modified it using `git blame`.

### 2. Source Normalization
Converts all input sources (working tree, staged changes, HEAD commit) to a single commit for consistent processing.

### 3. Commit Splitting
Creates temporary commits, one per hunk, enabling git's 3-way merge to work reliably.

### 4. Cherry-Pick with 3-Way Merge
Applies each hunk by cherry-picking its split commit:
- Uses `git cherry-pick --no-commit` for reliable 3-way merge
- Handles complex cases like removing lines from the commit that added them
- Git understands full history context, not just text diffs

### 5. Interactive Rebase
Rebases through target commits chronologically, amending each with its hunks in a single pass.

### 6. Validation
Post-flight validation via `git diff` ensures no data was lost or corrupted during processing.

This approach is more reliable than patch-based methods because git's 3-way merge can handle historical context changes that would cause simple text patches to fail.

For complete documentation, architecture details, and advanced usage patterns, see: **https://andrewleech.github.io/git-autosquash/**

## Working Tree State Handling

git-autosquash intelligently handles different working tree states:

- **Clean working tree**: Processes the HEAD commit for splitting up recent changes
- **Staged changes only**: Processes staged changes directly (no stashing needed)
- **Unstaged changes only**: Processes unstaged changes directly (no stashing needed)
- **Both staged and unstaged**: Temporarily stashes unstaged changes, processes staged changes, then restores unstaged changes

This smart handling ensures you can run git-autosquash at any time without losing work, while processing the most appropriate set of changes for your current workflow.

### Key Features

- **Smart Targeting**: git blame analysis identifies logical target commits
- **Interactive TUI**: Rich terminal interface with diff previews
- **Safety First**: All changes require explicit approval
- **Automatic Rollback**: Full git reflog integration for recovery
- **Conflict Resolution**: Clear guidance when merge conflicts occur
- **Multiple Modes**: Interactive, auto-accept, and dry-run options

### Data Integrity Validation

git-autosquash includes built-in validation to ensure data integrity throughout the process:

- **Pre-flight validation**: Verifies all changes are captured before processing
- **Post-flight validation**: Uses `git diff` to guarantee no data was lost, added, or corrupted
- **Automatic verification**: Validation runs automatically on every operation

When validation passes, you'll see: `[+] Validation passed - no corruption detected`

If validation fails, git-autosquash will halt and provide clear error messages with recovery instructions. This ensures you never lose work due to unexpected issues during the squash process.

## Documentation

**Complete documentation**: https://andrewleech.github.io/git-autosquash/

- **[Getting Started](https://andrewleech.github.io/git-autosquash/user-guide/getting-started/)** - First session walkthrough
- **[CLI Reference](https://andrewleech.github.io/git-autosquash/reference/cli-options/)** - All command-line options
- **[Advanced Usage](https://andrewleech.github.io/git-autosquash/user-guide/advanced-usage/)** - Complex workflows and edge cases
- **[Development Guide](https://andrewleech.github.io/git-autosquash/technical/development/)** - Contributing and development setup

## Use Cases

- Code review feedback distribution
- Lint and formatting fix integration
- Test update consolidation
- Documentation synchronization
- Security patch application
- Refactoring optimization placement

## Status

Production-ready with full test coverage. All core functionality implemented and actively maintained.

## Contributing

See [Development Guide](https://andrewleech.github.io/git-autosquash/technical/development/) for setup, testing, and contribution guidelines.

## Support

- **Issues**: [GitHub Issues](https://github.com/andrewleech/git-autosquash/issues)
- **Documentation**: https://andrewleech.github.io/git-autosquash/
- **Discussions**: [GitHub Discussions](https://github.com/andrewleech/git-autosquash/discussions)