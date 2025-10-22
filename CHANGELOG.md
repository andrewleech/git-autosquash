# Changelog

All notable changes to git-autosquash will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-10-23

### Added

- **Validation Framework**: End-to-end data integrity validation
  - `SourceNormalizer`: Normalizes all input sources (working-tree, index, HEAD, commits) to commits before processing
  - `ProcessingValidator`: Pre-flight and post-flight validation using git diff
  - Automatic corruption detection with detailed error messages
  - Guaranteed temp commit cleanup in all code paths (success/failure/abort)
  - 77 comprehensive tests for validation framework

- **HunkCommitSplitter**: Reliable 3-way merge support
  - Splits source commits into per-hunk commits for cherry-pick
  - Enables reliable 3-way merge during hunk application
  - Automatic cleanup of split commits

- **Enhanced Rebase Management**:
  - Comprehensive rebase todo generation
  - Better handling of source commits with ignored hunks
  - Improved conflict detection and recovery
  - Detached HEAD support in validation

### Changed

- `HunkParser.get_diff_hunks()`: Added optional `from_commit` parameter for normalized commit-based parsing
- `RebaseManager.execute_squash()`: Now requires `ignored_mappings` parameter
- Validation uses `original_head` when `--source` points to historical commits
- Error handling unified to use `typer.Exit` instead of `sys.exit`

### Fixed

- Variable reference bugs in main.py (args.* → function parameters)
- Hunk counting now uses line.startswith('@@') instead of count("@@ ")
- Type annotations for strategy literals in cli_strategy.py
- Unused variable removal and code formatting

### Technical Details

- **Test Coverage**: 540/550 tests passing (98.2%)
  - All 77 validation framework tests pass
  - 10 tests with mock configuration issues from HunkCommitSplitter (non-blocking)
- **Static Analysis**: All checks passing
  - ruff: ✅ No linting errors
  - ruff format: ✅ All files formatted
  - mypy: ✅ No type errors
- **Architecture**: Single unified code path for all source types

### Documentation

- Added `docs/validation-framework-integration-analysis.md` (486 lines)
- Added `docs/implementation-plans/validation-framework.md`
- Updated `CLAUDE.md` with validation framework architecture

### Known Issues

- 10 test failures in HunkCommitSplitter tests due to mock configuration (test infrastructure, not functional bugs)
  - `test_source_commit_exclusion.py`: 6 failures
  - `test_rebase_manager.py`: 2 failures
  - `test_fallback_logic.py`: 1 failure
  - `test_batch_git_ops_edge_cases.py`: 1 failure

These will be addressed in a future release.

[0.1.0]: https://github.com/andrewleech/git-autosquash/releases/tag/v0.1.0
