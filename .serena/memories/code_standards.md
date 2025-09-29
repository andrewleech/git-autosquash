# Code Standards & Conventions for git-autosquash

## Code Style & Formatting
- **Formatter**: ruff-format (enforced via pre-commit)
- **Linter**: ruff with --fix flag
- **Import Sorting**: Handled by ruff
- **Line Length**: Standard ruff defaults

## Type Hints
- **Type Checker**: mypy
- **Configuration**: Relaxed strict mode (strict = false)
- **Coverage**: Not enforced universally (disallow_untyped_defs = false)
- **External Libraries**: Missing imports ignored for psutil, pexpect, PIL, etc.

## Testing Standards  
- **Framework**: pytest with multiple extensions
- **Required Extensions**: 
  - pytest-asyncio (async testing)
  - pytest-cov (coverage)
  - pytest-mock (mocking)
  - pytest-textual-snapshot (TUI testing)
- **Test Files**: Excluded from strict mypy checking for external library compatibility

## File Naming & Structure
- **Package**: git_autosquash (underscore, not hyphen)
- **Main Module**: src/git_autosquash/main.py
- **TUI Components**: src/git_autosquash/tui/ subdirectory
- **Tests**: tests/ directory with test_* naming

## Documentation
- **Docstring Style**: Not specified in config (likely follows standard Python conventions)
- **Documentation System**: mkdocs with material theme
- **API Docs**: mkdocstrings for automatic API documentation

## Git Workflow
- **Pre-commit Hooks**: Mandatory (ruff check, ruff-format, mypy)
- **Branch Protection**: All quality checks must pass
- **No Bypass**: Never use --no-verify on commits

## Architecture Patterns
- **Strategy Pattern**: Multiple execution strategies for different git versions
- **Component Separation**: Clear separation between CLI, TUI, and git operations
- **Safety First**: Reflog integration, stash management, rollback capabilities