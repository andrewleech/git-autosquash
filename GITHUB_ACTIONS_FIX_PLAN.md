# GitHub Actions Failure Fix Plan

## Summary

After v0.1.0 release, identified 5 issues in GitHub Actions workflows:
- **CI Workflow**: 2 test issues, 1 Codecov configuration issue
- **Docs Workflow**: 3 MkDocs strict mode warnings
- **Transient**: GitHub cache service downtime (not our issue)

## Issue Breakdown

### 1. Windows Test Failure (CRITICAL)

**Location**: `tests/test_patch_generation_edge_cases.py:558`
**Error**: `TypeError: argument of type 'NoneType' is not iterable`
**Root Cause**: `diff_result.stdout` is `None` on Windows (encoding/subprocess issue)

```python
# Line 558 - failing assertion
assert "café" in diff_content or "unicode" in diff_content
# diff_content is None on Windows
```

**Impact**: CI fails on Windows platform (33% of test matrix)

**Fix Strategy**:
```python
# Option A: Add None check
diff_content = diff_result.stdout or ""
assert "café" in diff_content or "unicode" in diff_content

# Option B: Handle encoding explicitly
diff_result = git_ops.run_git_command(
    ["show", "--no-merges", scenario["unicode_update_commit"]],
    encoding="utf-8"  # Explicit encoding
)
```

**Effort**: 10 minutes
**Priority**: P0 (blocks CI)

---

### 2. Test Warning: test_error_recovery

**Location**: `tests/test_patch_generation_fix_refactored.py::test_error_recovery`
**Error**: `PytestReturnNotNoneWarning: Test functions should return None, but returned <class 'contextlib._GeneratorContextManager'>`

**Root Cause**: Test function is returning a context manager instead of None

**Fix Strategy**:
```python
# BEFORE
def test_error_recovery():
    return error_boundary("test_patch_application", max_retries=2)

# AFTER
def test_error_recovery():
    with error_boundary("test_patch_application", max_retries=2):
        # test logic here
        pass
```

**Effort**: 15 minutes
**Priority**: P1 (warning only, tests pass)

---

### 3. MkDocs Strict Mode: Missing Type Annotation

**Location**: `src/git_autosquash/main.py:661`
**Error**: `WARNING - griffe: No type or annotation for parameter 'context'`

**Fix Strategy**:
```python
# BEFORE
def some_function(context):
    ...

# AFTER
def some_function(context: SquashContext):
    ...
```

**Effort**: 5 minutes
**Priority**: P1 (docs build fails)

---

### 4. MkDocs Strict Mode: Broken Link

**Location**: `docs/technical/development.md`
**Error**: `WARNING - contains a link '../../CLAUDE.md#screenshot-generation', but target '../CLAUDE.md' is not found`

**Root Cause**: Link points outside docs/ directory (CLAUDE.md is in repo root)

**Fix Strategy**:

Option A - Copy section to docs:
```markdown
<!-- Create docs/development/screenshot-generation.md -->
[screenshot generation](../development/screenshot-generation.md)
```

Option B - Remove link:
```markdown
<!-- Remove or update link in development.md -->
See CLAUDE.md for screenshot generation details (in repo root)
```

**Effort**: 10 minutes
**Priority**: P1 (docs build fails)

---

### 5. MkDocs Strict Mode: Missing Cross-Reference

**Location**: `src/git_autosquash/tui/modern_screens.py:30`
**Error**: `WARNING - Could not find cross-reference target 'Cancel'`

**Root Cause**: Docstring references `Cancel` but it's not a linkable target

**Fix Strategy**:
```python
# BEFORE
"""
Press Cancel to abort.
"""

# AFTER
"""
Press `Cancel` to abort.
"""
# Or remove cross-reference syntax if using autorefs
```

**Effort**: 5 minutes
**Priority**: P1 (docs build fails)

---

### 6. Codecov Upload Failures (OPTIONAL)

**Error**: `error - Upload failed: {"message":"Token required - not valid tokenless upload"}`

**Root Cause**: Missing `CODECOV_TOKEN` secret in GitHub repository settings

**Impact**: Coverage reports not uploaded (non-blocking, tests still pass)

**Fix Strategy**:
1. Create Codecov account: https://codecov.io/
2. Add repository to Codecov
3. Copy upload token
4. Add `CODECOV_TOKEN` secret to GitHub repo settings
5. Or disable codecov in `.github/workflows/ci.yml` if not needed

**Effort**: 20 minutes (account setup + configuration)
**Priority**: P2 (optional feature)

---

## Implementation Plan

### Phase 1: Critical Fixes (P0 - 30 minutes)

**Fix Windows Test**:
1. Read `tests/test_patch_generation_edge_cases.py`
2. Add None check for `diff_content` at line 558
3. Verify fix handles None case gracefully
4. Test locally if possible (or rely on CI)

```bash
# Files to modify:
- tests/test_patch_generation_edge_cases.py
```

---

### Phase 2: Docs Fixes (P1 - 20 minutes)

**Fix Type Annotation**:
```bash
# Locate function at main.py:661
grep -n "def.*context" src/git_autosquash/main.py
# Add type annotation
```

**Fix Broken Link**:
```bash
# Option: Remove link or update to valid target
vim docs/technical/development.md
```

**Fix Cross-Reference**:
```bash
# Update docstring in modern_screens.py:30
vim src/git_autosquash/tui/modern_screens.py
```

```bash
# Files to modify:
- src/git_autosquash/main.py (line 661)
- docs/technical/development.md (link to CLAUDE.md)
- src/git_autosquash/tui/modern_screens.py (line 30)
```

---

### Phase 3: Test Warning Fix (P1 - 15 minutes)

**Fix test_error_recovery**:
1. Read test to understand context manager usage
2. Refactor to properly use context manager
3. Ensure test logic is preserved

```bash
# Files to modify:
- tests/test_patch_generation_fix_refactored.py
```

---

### Phase 4: Codecov (P2 - Optional)

**Option A**: Configure Codecov token
**Option B**: Remove codecov from CI workflow

This can be deferred or skipped entirely.

---

## Verification Plan

### Test Locally:
```bash
# Run full test suite
uv run pytest tests/ -v

# Build docs
uv run mkdocs build --strict

# Check for warnings
uv run pytest tests/ --warnings=summary
```

### Test on CI:
```bash
# Push fixes to branch
git checkout -b fix/github-actions-failures
git commit -am "fix: Resolve Windows test and docs build failures"
git push origin fix/github-actions-failures

# Monitor workflows
gh run list --branch fix/github-actions-failures --limit 3
```

### Merge to Main:
```bash
# After CI passes
git checkout main
git merge fix/github-actions-failures
git push origin main
```

---

## Risk Assessment

**Low Risk**:
- Type annotation addition (syntactic only)
- Docs link fixes (content only)
- None check for diff_content (defensive programming)

**Medium Risk**:
- test_error_recovery refactor (logic change)
  - Mitigation: Review test carefully, ensure behavior unchanged

**No Risk**:
- Codecov configuration (optional, external service)

---

## Time Estimate

- **Phase 1**: 30 minutes (Windows test fix)
- **Phase 2**: 20 minutes (3 docs fixes)
- **Phase 3**: 15 minutes (test warning)
- **Phase 4**: 20 minutes (optional, can skip)

**Total**: 1-1.5 hours (excluding optional Codecov)

---

## Success Criteria

1. ✅ CI passes on all platforms (Ubuntu, macOS, Windows)
2. ✅ Docs build succeeds without warnings in strict mode
3. ✅ No pytest warnings about test return values
4. ✅ All 550 tests still passing
5. ⚪ Codecov uploads (optional)

---

## Post-Fix Actions

1. Update CHANGELOG.md with bug fixes
2. Consider v0.1.1 patch release if fixes are significant
3. Monitor CI for 2-3 commits to ensure stability
4. Document Windows testing considerations in CLAUDE.md

---

## Notes

**Transient Issues** (not our fault):
- GitHub Actions cache service was down (400 errors)
- This caused multiple warnings but not actual failures
- Will resolve automatically when service recovers

**Platform Considerations**:
- Windows has different subprocess/encoding behavior
- Future tests should explicitly handle encoding
- Consider adding Windows-specific test fixtures
