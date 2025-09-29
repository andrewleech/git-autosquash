# Task Completion Checklist for git-autosquash

## When a Task is Completed

### Code Quality Requirements
1. **Pre-commit Hooks MUST Pass** (NEVER bypass with --no-verify)
   - `ruff check src/` (linting)
   - `ruff format src/` (formatting)  
   - `mypy src/` (type checking)

2. **Testing Requirements**
   - Run relevant tests: `uv run pytest tests/test_[module].py -v`
   - For new features: ensure test coverage exists
   - For bug fixes: add regression tests

### Development Workflow
```bash
# Before committing
uv run pre-commit run --all-files

# Testing workflow
uv run pytest tests/ --cov  # Full test suite with coverage
uv run pytest tests/test_specific.py -v  # Targeted testing

# If pre-commit modifies files
git add .  # Stage the hook modifications
git commit  # Commit again (pre-commit will run again)
```

### Architecture Compliance
- Follow Strategy Pattern for execution strategies
- Use GitOps wrapper, never raw subprocess
- Implement proper error handling with rollback
- Use BatchGitOperations for O(n) efficiency
- Follow TUI component separation

### Documentation Updates
- Update docstrings for new/modified methods
- Add type hints (mypy compliance)
- Update CLAUDE.md if architecture changes

### Production Readiness Checks
- Verify reflog integration for rollback safety
- Ensure stash management prevents data loss  
- Test error paths and cleanup procedures
- Validate input sanitization and security