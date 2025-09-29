# Development Commands for git-autosquash

## Package Management & Environment
```bash
# Install development environment
uv pip install -e .
uv sync --dev

# Install as tool (for end users)
uv tool install git-autosquash
```

## Testing Commands
```bash
# Run all tests
uv run pytest tests/

# Run specific test file with verbose output
uv run pytest tests/test_main.py -v

# Run specific test function
uv run pytest -k "test_function_name"

# Run with coverage
uv run pytest tests/ --cov

# Performance benchmarks
uv run pytest tests/test_performance_benchmarks.py -v

# Integration tests
uv run pytest tests/test_main_integration.py
```

## Code Quality (Pre-commit enforced)
```bash
# Setup pre-commit hooks (once after clone)
uv run pre-commit install

# Manual pre-commit run
uv run pre-commit run --all-files

# Individual tools
uv run ruff check src/                  # Linting
uv run ruff format src/                 # Format code
uv run mypy src/                        # Type checking
```

## Application Execution
```bash
# Interactive mode (default)
git-autosquash

# Auto-accept mode
git-autosquash --auto-accept

# Dry-run mode
git-autosquash --auto-accept --dry-run

# Line-by-line mode
git-autosquash --line-by-line
```

## Build & Release
```bash
# Build package
uv build

# Validate package
uv run twine check dist/*
```

## Documentation
```bash
# Local docs server
uv run mkdocs serve

# Build docs
uv run mkdocs build
```

## CRITICAL: Pre-commit Requirements
**NEVER use `git commit --no-verify`**. All commits must pass:
- ruff check (linting)
- ruff-format (formatting) 
- mypy (type checking)

If pre-commit fails, fix issues rather than bypass. Pre-commit may modify files - review and stage before committing again.