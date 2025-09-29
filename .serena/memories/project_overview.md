# git-autosquash Project Overview

## Purpose
git-autosquash automatically squashes changes back into historical commits where they belong. It eliminates "cleanup" commits by analyzing git blame to determine which historical commits should receive current changes, maintaining clean logical git history.

## Tech Stack
- **Language**: Python 3.12+
- **CLI Framework**: argparse (entry point: `git_autosquash.main:main`)
- **TUI Framework**: Textual 5.3.0+ for interactive terminal interface
- **Package Manager**: uv (modern Python package manager)
- **Build System**: hatchling with hatch-vcs for version management
- **Testing**: pytest with asyncio, cov, mock, textual-snapshot extensions
- **Type Checking**: mypy with relaxed configuration
- **Linting/Formatting**: ruff
- **Pre-commit**: Enforced hooks for quality control
- **Documentation**: mkdocs-material

## Architecture Overview
- **Core Components**: git operations, blame analysis, hunk parsing, rebase management
- **TUI Components**: Modern app with interactive approval screens
- **Strategy Pattern**: Multiple execution strategies (index-based, legacy fallback)
- **Safety Features**: Reflog integration, stash management, conflict resolution

## Key Features
- Smart git blame targeting
- Interactive TUI with diff previews
- Multiple modes: interactive, auto-accept, dry-run
- Working tree state handling (staged/unstaged/mixed)
- Automatic rollback capabilities
- Line-by-line precision mode

## Production Status
Production-ready with full test coverage, actively maintained