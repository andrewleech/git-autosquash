# Test Strategy: Context-Aware Patch Generation Fix

## Overview

This document outlines the comprehensive test strategy for validating the context-aware patch generation fix that resolves the critical issue where multiple hunks with identical content changes targeting the same commit would generate duplicate conflicting patches.

## The Problem Being Tested

### Original Issue
- **Symptom**: `git apply` failures with "patch does not apply" errors
- **Root Cause**: Multiple hunks with identical changes (e.g., `MICROPY_PY___FILE__` → `MICROPY_MODULE___FILE__`) would find the same target line, generating duplicate patches for the same location
- **Impact**: Prevented squashing of commits with multiple similar changes

### The Fix
- **Context-Aware Matching**: Track used lines to prevent duplicate targeting
- **Used Line Set**: Maintain `Set[int]` of already-targeted line numbers
- **Multiple Candidate Handling**: When multiple matching lines exist, select first unused candidate

## Test File Structure

```
tests/
├── test_patch_generation_fix.py           # Core functionality tests
├── test_patch_generation_regression.py    # Regression prevention tests  
├── test_patch_generation_performance.py   # Performance benchmarks
├── conftest_patch_generation.py          # Shared fixtures and utilities
└── TEST_STRATEGY_PATCH_GENERATION.md     # This document
```

## Test Coverage Matrix

| Test Category | File | Key Test Cases | Purpose |
|---------------|------|----------------|---------|
| **Core Fix** | `test_patch_generation_fix.py` | MicroPython scenario reproduction, context-aware matching, used line tracking | Validate the fix works |
| **Regression** | `test_patch_generation_regression.py` | Single hunk unchanged, backwards compatibility, error handling | Prevent breaking existing functionality |
| **Performance** | `test_patch_generation_performance.py` | Large files, many hunks, memory usage, scalability | Ensure no performance regressions |

## Detailed Test Cases

### 1. Core Functionality Tests (`test_patch_generation_fix.py`)

#### `TestContextAwarePatchGeneration`
- **`test_context_aware_patch_generation_prevents_duplicates`**
  - Reproduces exact MicroPython scenario with two `MICROPY_PY___FILE__` → `MICROPY_MODULE___FILE__` changes
  - Verifies patch has 2 separate hunks targeting different line numbers
  - Confirms patch applies cleanly with `git apply --check`

- **`test_used_line_tracking`**
  - Tests that used line tracking prevents duplicate targeting
  - Validates behavior in both target commit state (1 instance) and intermediate state (2 instances)

- **`test_multiple_candidates_selection`**
  - Tests selection logic when multiple identical lines exist
  - Verifies first unused candidate selection
  - Ensures third call returns None when no more candidates

#### `TestPatchGenerationEdgeCases`
- **`test_empty_hunks_list`** - Handles empty input gracefully
- **`test_file_read_failure_handling`** - Handles missing files
- **`test_malformed_hunk_handling`** - Processes unexpected input formats
- **`test_precommit_hook_integration`** - Works with pre-commit hook modifications

#### `TestIntegrationWithRealGitOperations`
- **`test_end_to_end_patch_application`** - Full git workflow integration
- **`test_performance_with_large_files`** - Real git repo with large files

### 2. Regression Prevention Tests (`test_patch_generation_regression.py`)

#### `TestPatchGenerationRegression`
- **`test_single_hunk_unchanged_behavior`** - Single hunk scenarios work as before
- **`test_different_files_unchanged_behavior`** - Multi-file hunks unchanged
- **`test_context_lines_generation_unchanged`** - Context generation unchanged
- **`test_hunk_extraction_edge_cases`** - Various hunk formats handled

#### `TestNegativeScenarios`
- **`test_file_permission_errors`** - Graceful failure on permission issues
- **`test_binary_file_handling`** - Appropriate binary file handling
- **`test_corrupted_hunk_data`** - Handles corrupted input data

#### `TestBackwardsCompatibility`
- **`test_legacy_hunk_format_support`** - Legacy formats still work
- **`test_existing_workflow_unchanged`** - Existing API methods unchanged

### 3. Performance Tests (`test_patch_generation_performance.py`)

#### `TestPatchGenerationPerformance`
- **`test_large_file_patch_generation_time`** - Max 2 second generation time
- **`test_many_hunks_memory_usage`** - Max 50MB memory increase
- **`test_used_lines_set_performance`** - Efficient set operations
- **`test_stress_test_patch_generation`** - Maximum realistic scenario

#### `TestPatchGenerationBenchmarks`
- **`test_benchmark_single_vs_multiple_hunks`** - Efficiency comparison
- **`test_benchmark_file_size_scalability`** - Scalability analysis

## Test Fixtures and Utilities

### `conftest_patch_generation.py` Fixtures

#### Repository Management
- **`clean_temp_repo`** - Clean temporary git repository
- **`git_repo_builder`** - Builder pattern for complex git histories
- **`git_config_user`** - Standard git user configuration

#### Content Generation
- **`micropy_test_files`** - Standard MicroPython file content variations
- **`standard_hunk_patterns`** - Common diff patterns for testing
- **`hunk_factory`** - Factory for creating test hunks

#### Utilities
- **`create_git_history()`** - Build git history with specific commits
- **`create_hunk_from_pattern()`** - Generate DiffHunk from pattern
- **`GitRepoBuilder`** - Class for building complex test repositories

## Test Execution

### Local Development
```bash
# Run all patch generation tests
pytest tests/test_patch_generation*.py -v

# Run only core functionality tests
pytest tests/test_patch_generation_fix.py -v

# Run performance tests (may take longer)
pytest tests/test_patch_generation_performance.py -v -m performance

# Run specific test case
pytest tests/test_patch_generation_fix.py::TestContextAwarePatchGeneration::test_context_aware_patch_generation_prevents_duplicates -v
```

### CI Environment
```bash
# Standard test run
pytest tests/test_patch_generation_fix.py tests/test_patch_generation_regression.py

# Performance benchmarks (optional, longer running)
pytest tests/test_patch_generation_performance.py -m benchmark
```

## Key Assertions and Validation Points

### Correctness Validation
1. **Patch Structure**: Verify patch has expected number of hunks
2. **Line Number Uniqueness**: Ensure different hunks target different lines
3. **Git Apply Success**: Confirm patch applies cleanly with `git apply`
4. **Content Verification**: Check final file content has correct transformations

### Performance Validation
1. **Time Limits**: Patch generation < 2 seconds for realistic scenarios
2. **Memory Usage**: < 50MB memory increase for large scenarios
3. **Scalability**: Reasonable scaling with file size and hunk count

### Regression Prevention
1. **API Compatibility**: Existing methods still work
2. **Single Hunk Behavior**: No change for simple cases
3. **Error Handling**: Graceful failure modes maintained

## Test Data and Scenarios

### MicroPython Reproduction Scenario
- **Initial State**: File without `__file__` support
- **Target Commit**: Adds single `#if MICROPY_PY___FILE__` instance
- **Intermediate Commit**: Adds second `#if MICROPY_PY___FILE__` instance  
- **Source Commit**: Changes both to `#if MICROPY_MODULE___FILE__`

### Edge Case Scenarios
- Files with 100+ identical patterns
- Very long lines (1000+ characters)
- Binary files (should be skipped)
- Permission errors (should be handled gracefully)
- Malformed diff hunks (should not crash)

### Performance Scenarios
- 10,000 line files with scattered patterns
- 100 hunks targeting same file
- Multiple files with many patterns each
- Large used_lines sets (100k+ entries)

## Success Criteria

### Functional Requirements ✅
- [x] MicroPython scenario generates 2 distinct hunks
- [x] Patches apply successfully with `git apply`
- [x] Used line tracking prevents duplicate targeting
- [x] Multiple candidates handled intelligently
- [x] Backwards compatibility maintained

### Non-Functional Requirements ✅
- [x] Performance: < 2s for realistic scenarios
- [x] Memory: < 50MB increase for stress tests
- [x] Scalability: Reasonable growth with input size
- [x] Reliability: Graceful error handling
- [x] Maintainability: Clear test structure and documentation

## Running in Different Environments

### Local Development
- All tests should pass on developer machines
- Uses temporary directories for git repositories
- Cleans up automatically after test completion

### CI/CD Pipeline
- Fast subset for pull request validation
- Full test suite for main branch
- Performance benchmarks optional/nightly

### Docker/Containerized
- Tests work in containerized environments
- No external dependencies beyond git
- Deterministic and isolated

## Maintenance and Evolution

### Adding New Test Cases
1. Identify the scenario to test
2. Choose appropriate test file based on category
3. Use existing fixtures and utilities
4. Follow naming conventions: `test_<scenario>_<expected_behavior>`

### Updating for Code Changes
- Update fixtures if internal APIs change
- Add new edge cases as they're discovered
- Maintain performance baselines
- Document any breaking changes

### Monitoring Test Health
- Track test execution times
- Monitor flaky test patterns
- Update test data for new edge cases
- Regular review of test coverage

This comprehensive test strategy ensures the context-aware patch generation fix is thoroughly validated, prevents regressions, and maintains high performance standards.