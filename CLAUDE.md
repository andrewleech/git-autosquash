# Development Guide for git-autosquash

## Project Structure
```
git-autosquash/
├── src/
│   ├── __init__.py
│   ├── main.py              # CLI entry point and argument parsing
│   ├── git_ops.py           # Git operations (status, blame, rebase)
│   ├── hunk_parser.py       # Diff parsing and hunk splitting
│   ├── blame_analyzer.py    # Git blame analysis and target resolution
│   ├── tui/
│   │   ├── __init__.py
│   │   ├── app.py          # Main Textual application
│   │   ├── screens.py      # Approval screen with diff display
│   │   └── widgets.py      # Custom widgets for hunk/commit display
│   └── rebase_manager.py   # Interactive rebase execution
├── tests/
├── .github/
│   └── workflows/
│       ├── ci.yml          # Build, test, lint
│       └── release.yml     # PyPI deployment on tags
├── .pre-commit-config.yaml # Pre-commit hooks configuration
├── pyproject.toml          # Project config (uv managed)
├── uv.lock                 # Dependency lock file
└── README.md
```

## Development Priorities

### Phase 1: Foundation
1. **Git repository detection and validation**
   - Ensure we're in a git repo
   - Find current branch name
   - Locate master/main branch and calculate merge-base
   - Validate branch has commits to work with

2. **Working tree analysis**
   - Detect clean/staged/unstaged states
   - Implement mixed-state user prompts
   - Handle edge cases (empty repo, detached HEAD)

### Phase 2: Diff Processing
3. **Hunk extraction and parsing**
   - Parse `git diff` output into structured hunks
   - Implement both default and `--line-by-line` modes
   - Store file path, line numbers, and content for each hunk

4. **Git blame integration**
   - Run blame on specific line ranges per hunk
   - Parse blame output to extract commit information
   - Filter commits within branch scope (merge-base to HEAD)

### Phase 3: User Experience (Textual TUI)
5. **Rich terminal interface**
   - Create Textual app with approval screen
   - Display hunk → commit mappings in structured layout
   - Show diff content with syntax highlighting
   - Interactive widgets for approval/rejection per hunk
   - Progress indicators and status displays

### Phase 4: Execution
6. **Interactive rebase automation**
   - Generate appropriate rebase todo lists
   - Execute rebase with hunk applications
   - Handle conflicts gracefully (pause/resume/abort)
   - Manage stash/unstash for staged-only workflows

### Phase 5: CLI & Integration
7. **Command-line interface**
   - Argument parsing (`--line-by-line`, `--help`)
   - Git integration (install as git subcommand)
   - Error handling and user guidance

### Phase 6: CI/CD & Packaging
8. **GitHub Actions setup**
   - CI workflow (test, lint, type-check on multiple Python versions)
   - Release workflow (build and deploy to PyPI on git tags)
   - Badge integration for build status

9. **Package configuration**
   - pyproject.toml with setuptools-scm version management
   - Entry points for git subcommand integration
   - Proper dependency specification

## Key Implementation Notes

### Git Command Strategy
- Use `subprocess` for git commands rather than gitpython for complex operations
- Always check return codes and handle failures gracefully
- Capture both stdout and stderr for error reporting

### Error Handling
- Validate git repo state before any operations
- Provide clear error messages for common failure modes
- Always offer abort/rollback options during rebase conflicts
- Handle edge cases: empty diffs, no target commits found, rebase failures

### User Interface
- Use `argparse` for CLI argument parsing
- **Textual** for rich terminal interface:
  - Syntax-highlighted diff display
  - Interactive hunk approval widgets
  - Split-pane layout (hunks list + diff viewer)
  - Progress bars and status indicators
  - Keyboard shortcuts for efficient navigation
- Fallback to simple CLI prompts if Textual unavailable
- Support standard git-style help and error patterns

### Testing Strategy
- Unit tests for each module (hunk parsing, blame analysis)
- Integration tests with actual git repositories
- Test edge cases: merge conflicts, empty repos, invalid states
- Mock git commands for reliable testing

## Project Management

### Package Management
- **uv** for dependency management and project setup
- **setuptools-scm** for dynamic version generation from git tags
- **pyproject.toml** configuration (no setup.py needed)
- **pre-commit** for automated code quality enforcement

### Repository
- GitHub: https://github.com/andrewleech/git-autosquash
- GitHub Actions for CI/CD pipeline

## Development Commands

```bash
# Initialize project with uv
uv init --package git-autosquash

# Add dependencies
uv add textual gitpython
uv add --dev pytest ruff mypy pre-commit

# Install in development mode
uv pip install -e .

# Setup pre-commit hooks (run once after clone)
uv run pre-commit install

# Run tests
uv run pytest tests/

# Lint and format code (pre-commit does this automatically)
uv run ruff check src/
uv run ruff format src/

# Type checking
uv run mypy src/

# Run all pre-commit hooks manually
uv run pre-commit run --all-files

# Test Textual UI in development
uv run textual console

# Build for distribution
uv build
```

## Git Integration
The final tool should be installable as a git subcommand via PATH or git config.

## Commit Guidelines

**CRITICAL**: Always use pre-commit hooks for all commits. Never bypass with `--no-verify`.

### Commit Process
1. Stage your changes: `git add <files>`
2. Commit normally: `git commit -m "message"`
3. Pre-commit automatically runs: ruff check, ruff format, mypy
4. If pre-commit fails: fix issues and commit again
5. If pre-commit modifies files: review changes and `git add` them, then commit again

### Pre-commit Hook Configuration
- **ruff check**: Linting and code quality checks
- **ruff format**: Code formatting (replaces black)
- **mypy**: Static type checking
- All hooks must pass before commit is allowed

### Never Use
- `git commit --no-verify` - This bypasses quality checks and is strictly forbidden
- Always fix pre-commit issues rather than bypassing them

## Documentation Structure

The project uses MkDocs Material for documentation, hosted on GitHub Pages with automated deployment.

### Site Architecture
```
docs/
├── index.md                 # Project overview and quick start
├── installation.md          # Installation methods and requirements
├── user-guide/
│   ├── getting-started.md   # First-time usage tutorial
│   ├── basic-workflow.md    # Standard usage patterns
│   ├── advanced-usage.md    # Power user features and options
│   └── troubleshooting.md   # Common issues and solutions
├── technical/
│   ├── architecture.md      # System design and component overview
│   ├── api-reference.md     # Code API documentation
│   ├── development.md       # Contributing and development setup
│   └── testing.md          # Test suite and quality assurance
├── examples/
│   ├── basic-scenarios.md   # Common use cases with examples
│   ├── complex-workflows.md # Advanced scenarios and edge cases
│   └── integration.md       # CI/CD and automation examples
└── reference/
    ├── cli-options.md       # Command-line reference
    ├── configuration.md     # Settings and customization
    └── faq.md              # Frequently asked questions
```

### Documentation Development
- Use `mkdocs serve` for local development and live reload
- Auto-generated API documentation from docstrings
- Mermaid diagrams for workflow visualization
- Code examples extracted from test cases for accuracy