# git-autosquash

[![Tests](https://github.com/andrewleech/git-autosquash/actions/workflows/ci.yml/badge.svg)](https://github.com/andrewleech/git-autosquash/actions/workflows/ci.yml)
[![Documentation](https://github.com/andrewleech/git-autosquash/actions/workflows/docs.yml/badge.svg)](https://github.com/andrewleech/git-autosquash/actions/workflows/docs.yml)
[![PyPI version](https://badge.fury.io/py/git-autosquash.svg)](https://badge.fury.io/py/git-autosquash)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

**Automatically squash changes back into historical commits where they belong.**

git-autosquash is a powerful tool that analyzes your working directory changes and automatically distributes them back to the commits where those code sections were last modified. Instead of creating noisy "fix lint errors", "cleanup tests", or "address review feedback" commits, it uses git blame analysis to intelligently squash improvements back into their logical historical commits.

**Perfect for common scenarios like**: You've been working on a feature branch and now need to fix lint errors, test failures, or code review feedback. Rather than committing all fixes into a final "cleanup" commit, git-autosquash lets you push each fix back to the original commit that introduced the issue, maintaining clean and logical git history.

## ( Key Features

- **<� Smart Targeting**: Uses git blame to find the exact commits where code was last modified
- **=� Interactive TUI**: Rich terminal interface with syntax-highlighted diff viewer  
- **= Safety First**: Default unapproved state with user confirmation for all changes
- **� Conflict Resolution**: Clear guidance when merge conflicts occur during rebase
- **=� Progress Tracking**: Real-time feedback with detailed commit summaries
- **= Rollback Support**: Full git reflog integration for easy recovery

## =� Quick Start

### Installation

```bash
# Recommended: Install with uv (fastest, modern Python package manager)
uv tool install git-autosquash

# Or with pipx for isolated environment
pipx install git-autosquash

# Or with pip
pip install git-autosquash
```

### Basic Usage

```bash
# Make some changes to your code
vim src/auth.py src/ui.py

# Run git-autosquash to organize changes
git-autosquash

# Review proposed changes in the TUI, approve what makes sense
# Changes are automatically squashed into their target commits!
```

### Example: Lint and Test Cleanup

```bash
# You've finished your feature work
git checkout -b feature/user-dashboard
# ... implemented new dashboard functionality ...

# Now you run tests and linting before pushing
npm run test    # Some tests fail due to old issues
npm run lint    # Linting errors in various files

# Fix all the issues
vim src/auth.py      # Fix failing test in auth module
vim src/api.py       # Fix lint errors in API endpoints  
vim src/dashboard.py # Fix test in new dashboard code

# Instead of: git commit -m "fix lint and test errors"

git-autosquash
# TUI shows:
#  src/dashboard.py:15-30 � abc1234 "Add user dashboard" (HIGH confidence)
#  src/auth.py:45-47 � def5678 "Fix login validation" (MEDIUM confidence)  
#  src/utils.py:12 � No target (new functionality)

# After approval:
# - Dashboard improvements squashed into original dashboard commit
# - Auth bug fix squashed into original auth commit  
# - Utils changes remain as new development
```

## =� Documentation

**Complete documentation is available at: https://andrewleech.github.io/git-autosquash/**

### Quick Links

- **[Getting Started](https://andrewleech.github.io/git-autosquash/user-guide/getting-started/)** - Your first git-autosquash session
- **[Basic Workflow](https://andrewleech.github.io/git-autosquash/user-guide/basic-workflow/)** - Common usage patterns
- **[CLI Reference](https://andrewleech.github.io/git-autosquash/reference/cli-options/)** - Command-line options and flags
- **[FAQ](https://andrewleech.github.io/git-autosquash/reference/faq/)** - Frequently asked questions
- **[API Reference](https://andrewleech.github.io/git-autosquash/technical/api-reference/)** - Developer documentation

### Documentation Sections

- **User Guides**: Installation, getting started, advanced usage, troubleshooting
- **Examples**: Real-world scenarios, complex workflows, IDE integration  
- **Technical**: Architecture, development guide, testing strategy
- **Reference**: CLI options, configuration, FAQ, API documentation

## =� How It Works

1. **Analysis**: Parses your working directory changes into structured hunks
2. **Blame Investigation**: Uses `git blame` to find which commits last modified each line
3. **Target Resolution**: Applies frequency-based algorithm to select target commits
4. **Interactive Review**: Presents findings in rich TUI with confidence indicators
5. **Safe Execution**: Performs interactive rebase only on user-approved changes

## =� Use Cases

### Perfect for:
- **Bug fixes during feature work** - Squash fixes back into original implementations
- **Code review feedback** - Distribute improvements to their logical commits
- **Refactoring sessions** - Integrate optimizations with original code
- **Documentation updates** - Keep docs synchronized with code changes

### Example: Code Review Workflow
```bash
# After addressing review feedback across multiple files
git-autosquash

# TUI automatically maps:
# - Security fix � Original security implementation commit
# - Performance improvement � Original algorithm commit  
# - Documentation update � Original feature commit
# - New functionality � Remains as new commits

# Result: Clean history where each commit tells complete story
```

## =' Command-Line Options

```bash
git-autosquash [OPTIONS]

Options:
  --line-by-line    Use line-by-line hunk splitting for maximum precision
  --version         Show version information
  --help           Show help message
```

### Precision Modes

- **Standard**: Uses git's default hunk boundaries (faster, good for most cases)
- **Line-by-line**: Analyzes each changed line individually (slower, maximum precision)

## >� Development Status

git-autosquash is actively developed and functional. All core features are implemented and tested:

-  Git repository analysis and validation
-  Diff parsing with both standard and line-by-line modes  
-  Git blame analysis with intelligent target resolution
-  Rich terminal interface with Textual framework
-  Interactive rebase execution with conflict handling
-  Comprehensive error handling and recovery

## > Contributing

We welcome contributions! Please see our [Development Guide](https://andrewleech.github.io/git-autosquash/technical/development/) for details on:

- Setting up the development environment
- Code standards and pre-commit hooks  
- Testing strategy and guidelines
- Submitting pull requests

### Quick Development Setup

```bash
git clone https://github.com/andrewleech/git-autosquash.git
cd git-autosquash

# Install in development mode
uv pip install -e ".[dev]"

# Install pre-commit hooks (required)
uv run pre-commit install

# Run tests
uv run pytest
```

## =� License

[License information to be added]

## =O Acknowledgments

- Built with [Textual](https://textual.textualize.io/) for the rich terminal interface
- Powered by [uv](https://github.com/astral-sh/uv) for fast dependency management  
- Documentation built with [MkDocs Material](https://squidfunk.github.io/mkdocs-material/)

## =� Support

- **Documentation**: https://andrewleech.github.io/git-autosquash/
- **Issues**: [GitHub Issues](https://github.com/andrewleech/git-autosquash/issues)
- **Discussions**: [GitHub Discussions](https://github.com/andrewleech/git-autosquash/discussions)

---

**Made with d for developers who care about clean Git history**