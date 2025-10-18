# Validation Framework Integration Analysis

**Date:** 2025-10-19
**Phase:** Phase 2 Complete - Integration Analysis
**Status:** Ready for Phase 3 Integration

## Executive Summary

SourceNormalizer and ProcessingValidator are complete with comprehensive test coverage (52 tests total, all passing). This analysis identifies integration points and provides implementation guidance for Phase 3.

---

## Current Architecture

### Entry Point Flow (main.py)

```
main()
  └─> process_hunks_and_mappings()
        ├─> HunkParser.get_diff_hunks(source="auto")
        │     └─> Branches on source type (57 lines, lines 53-110)
        ├─> HunkTargetResolver.resolve_targets()
        └─> Returns (automatic_mappings, fallback_mappings)

main() continues:
  └─> TUI or Auto-approval
  └─> RebaseManager.execute_squash(mappings, context)
        ├─> _handle_working_tree_state()
        ├─> _apply_hunks_to_commit() for each target
        └─> _restore_stash_by_sha()
```

### Key Observation

**SourceNormalizer belongs in main.py**, not RebaseManager. The normalization must happen BEFORE hunk parsing to ensure consistent line numbers.

---

## Integration Points

### 1. main.py: process_hunks_and_mappings() - PRIMARY

**Current Code (approx lines 400-450):**
```python
def process_hunks_and_mappings(
    git_ops: GitOps,
    merge_base: str,
    line_by_line: bool,
    source: str,
    blame_ref: str,
    context: SquashContext,
) -> tuple[List[HunkTargetMapping], List[HunkTargetMapping]]:
    # Parse hunks from source (branches on type)
    hunk_parser = HunkParser(git_ops)
    hunks = hunk_parser.get_diff_hunks(line_by_line=line_by_line, source=source)

    # Resolve targets
    resolver = HunkTargetResolver(git_ops, merge_base, context, blame_ref=blame_ref)
    mappings = resolver.resolve_targets(hunks)

    # Separate automatic vs fallback
    automatic_mappings = [m for m in mappings if not m.needs_user_selection]
    fallback_mappings = [m for m in mappings if m.needs_user_selection]

    return automatic_mappings, fallback_mappings
```

**Required Changes:**

```python
from git_autosquash.source_normalizer import SourceNormalizer
from git_autosquash.validation import ProcessingValidator

def process_hunks_and_mappings(
    git_ops: GitOps,
    merge_base: str,
    line_by_line: bool,
    source: str,
    blame_ref: str,
    context: SquashContext,
) -> tuple[List[HunkTargetMapping], List[HunkTargetMapping], str]:  # Returns starting_commit
    # Phase 1: Normalize source to commit
    normalizer = SourceNormalizer(git_ops)
    starting_commit = normalizer.normalize_to_commit(source)
    logger.info(f"Processing from commit: {starting_commit[:8]}")

    # Phase 2: Parse hunks from normalized commit
    hunk_parser = HunkParser(git_ops)
    hunks = hunk_parser.get_diff_hunks(
        line_by_line=line_by_line,
        from_commit=starting_commit  # NEW PARAMETER
    )

    if not hunks:
        logger.info("No hunks found to process")
        normalizer.cleanup_temp_commit()
        return [], [], starting_commit

    # Phase 3: Pre-flight validation
    validator = ProcessingValidator(git_ops)
    validator.validate_hunk_count(starting_commit, hunks)

    # Phase 4: Resolve targets
    resolver = HunkTargetResolver(git_ops, merge_base, context, blame_ref=blame_ref)
    mappings = resolver.resolve_targets(hunks)

    # Separate automatic vs fallback
    automatic_mappings = [m for m in mappings if not m.needs_user_selection]
    fallback_mappings = [m for m in mappings if m.needs_user_selection]

    return automatic_mappings, fallback_mappings, starting_commit
```

**Impact:** Low - clean insertion point, only adds validation, doesn't change existing logic.

---

### 2. HunkParser.get_diff_hunks() - REFACTOR REQUIRED

**Current Signature:**
```python
def get_diff_hunks(self, line_by_line: bool = False, source: str = "auto") -> List[DiffHunk]:
```

**New Signature:**
```python
def get_diff_hunks(
    self,
    line_by_line: bool = False,
    from_commit: Optional[str] = None,
    source: str = "auto"  # DEPRECATED, kept for compatibility
) -> List[DiffHunk]:
    """Extract hunks from a commit.

    Args:
        line_by_line: If True, split hunks line-by-line
        from_commit: Commit hash to parse (recommended, use with SourceNormalizer)
        source: DEPRECATED - use from_commit instead

    Returns:
        List of DiffHunk objects
    """
    if from_commit:
        # New path: parse from normalized commit
        result = self.git_ops.run_git_command(["show", "--format=", from_commit])
        if result.returncode != 0:
            return []
        hunks = self._parse_diff_output(result.stdout)
    else:
        # Legacy path: maintain backward compatibility
        hunks = self._get_hunks_from_source(source)  # Existing branching logic

    if line_by_line:
        hunks = self._split_hunks_line_by_line(hunks)

    return hunks
```

**Migration Strategy:**
- Keep `source` parameter for backward compatibility initially
- Add deprecation warning when `source` is used without `from_commit`
- Gradually migrate all call sites to use `from_commit`
- Remove `source` parameter in future major version

**Impact:** Medium - requires refactoring but maintains backward compatibility.

---

### 3. main.py: Post-validation Integration

**Current Flow:**
```python
def main():
    # ... parse args, setup ...

    automatic_mappings, fallback_mappings = process_hunks_and_mappings(...)

    # TUI or auto-approval
    approved_mappings = get_approved_mappings(...)

    # Execute rebase
    rebase_manager = RebaseManager(git_ops, merge_base)
    success = rebase_manager.execute_squash(approved_mappings, context)

    if success:
        print("Success!")
    else:
        print("Failed!")
```

**New Flow:**
```python
def main():
    # ... parse args, setup ...

    # Get starting commit for validation
    automatic_mappings, fallback_mappings, starting_commit = process_hunks_and_mappings(...)

    # Store normalizer for cleanup
    normalizer = SourceNormalizer(git_ops)
    normalizer.starting_commit = starting_commit
    normalizer.temp_commit_created = starting_commit_needs_cleanup  # Track from process_hunks

    try:
        # TUI or auto-approval
        approved_mappings = get_approved_mappings(...)

        # Execute rebase
        rebase_manager = RebaseManager(git_ops, merge_base)
        success = rebase_manager.execute_squash(approved_mappings, context)

        if success:
            # POST-FLIGHT VALIDATION (CRITICAL)
            validator = ProcessingValidator(git_ops)
            validator.validate_processing(starting_commit, description="squash operation")
            logger.info("[+] Validation passed - no corruption detected")
            print("Success!")
        else:
            print("Failed!")

    except ValidationError as e:
        logger.error(f"VALIDATION FAILED: {e}")
        logger.error("Aborting to prevent data corruption")
        # Abort operations
        if rebase_manager.is_rebase_in_progress():
            rebase_manager.abort_operation()
        sys.exit(1)

    finally:
        # Always cleanup temp commit
        normalizer.cleanup_temp_commit()
```

**Impact:** Medium - adds try/except wrapping and validation call after rebase.

---

### 4. SquashContext Updates (Optional)

**Current SquashContext:**
```python
class SquashContext:
    merge_base: str
    blame_ref: str
    source_commit: Optional[str]  # Only set for explicit commit sources
```

**Potential Addition:**
```python
class SquashContext:
    merge_base: str
    blame_ref: str
    source_commit: Optional[str]
    starting_commit: Optional[str]  # NEW: normalized commit for validation
    temp_commit_created: bool = False  # NEW: track if cleanup needed
```

**Decision:** NOT RECOMMENDED. SquashContext is for blame/resolve configuration, not runtime state. Keep normalization state local to main.py flow.

---

## Implementation Plan - Phase 3

### Step 1: Update HunkParser (2 hours)

1. Add `from_commit` parameter to `get_diff_hunks()`
2. Add deprecation warning for `source` parameter
3. Implement commit-based parsing path
4. Keep legacy `source` path for compatibility
5. Update unit tests

**Deliverables:**
- Updated `src/git_autosquash/hunk_parser.py`
- Backward compatibility maintained
- Tests updated

---

### Step 2: Integrate SourceNormalizer in main.py (2 hours)

1. Update `process_hunks_and_mappings()` signature to return `starting_commit`
2. Add SourceNormalizer instantiation
3. Pass `from_commit` to HunkParser
4. Add pre-flight `validate_hunk_count()` call
5. Update all call sites to handle new return value

**Deliverables:**
- Updated `src/git_autosquash/main.py`
- Normalizer integrated before parsing
- Pre-flight validation active

---

### Step 3: Add Post-flight Validation (1 hour)

1. Wrap rebase execution in try/except
2. Add `ProcessingValidator.validate_processing()` after success
3. Handle ValidationError with abort logic
4. Add cleanup in finally block

**Deliverables:**
- Post-flight validation active
- Proper error handling
- Temp commit cleanup guaranteed

---

### Step 4: Integration Testing (2 hours)

1. Test with all source types (working-tree, index, HEAD, commit refs)
2. Test validation failure scenarios
3. Test cleanup after errors
4. Test temp commit removal
5. Performance testing

**Deliverables:**
- Integration tests passing
- All source types validated
- Error paths tested

---

### Step 5: Documentation (1 hour)

1. Update CLAUDE.md with validation framework
2. Update architecture docs
3. Add validation error handling guide
4. Update user-facing docs

**Deliverables:**
- Documentation complete
- Examples provided

**Total Estimated Time: 8 hours**

---

## Decision Points

### Q1: When to validate?

**Decision: Validate in main.py, not RebaseManager**

**Rationale:**
- RebaseManager only sees mappings, not original source
- Validation needs starting_commit which is determined in main.py
- Keeps RebaseManager focused on rebase orchestration
- Cleaner separation of concerns

---

### Q2: How to handle validation failures?

**Decision: Abort immediately, cleanup, exit with error**

**Rationale:**
- Data corruption is unacceptable
- User needs clear error message with recovery instructions
- Automatic rollback prevents bad state
- Manual intervention required for investigation

---

### Q3: Backward compatibility strategy?

**Decision: Add new parameters, keep old ones deprecated**

**Rationale:**
- Gradual migration reduces risk
- Existing code continues to work
- Clear path to full migration
- Can remove deprecated code in major version bump

---

## Risk Assessment

### Low Risk
- SourceNormalizer integration (isolated, well-tested)
- Pre-flight validation (optional check, doesn't block)
- Temp commit cleanup (safe operation)

### Medium Risk
- HunkParser refactoring (touches core parsing logic)
- Post-flight validation (blocks on errors)
- Try/except wrapping (changes control flow)

### Mitigation
- Comprehensive integration tests
- Staged rollout (validate but don't block initially)
- Feature flag for validation (environment variable)
- Extensive manual testing

---

## Testing Strategy

### Unit Tests
- ✓ SourceNormalizer (30 tests passing)
- ✓ ProcessingValidator (22 tests passing)
- ⏳ HunkParser with from_commit parameter
- ⏳ Integration points in main.py

### Integration Tests
- ⏳ End-to-end with working-tree source
- ⏳ End-to-end with index source
- ⏳ End-to-end with HEAD source
- ⏳ End-to-end with commit refs
- ⏳ Validation failure scenarios
- ⏳ Cleanup after errors

### Manual Testing
- ⏳ Real repositories with various source types
- ⏳ Large commits (performance)
- ⏳ Binary files
- ⏳ Unicode content
- ⏳ Merge conflicts

---

## Success Criteria

**Phase 3 Complete When:**
1. ✓ All source types normalized correctly
2. ✓ Pre-flight validation catches hunk count mismatches
3. ✓ Post-flight validation catches corruption
4. ✓ Temp commits cleaned up in all paths (success, error, abort)
5. ✓ Validation errors provide clear recovery instructions
6. ✓ All integration tests passing
7. ✓ Documentation complete

---

## Open Questions

1. **Should validation be optional initially?**
   - Pro: Safer rollout, can disable if issues found
   - Con: Two code paths to maintain
   - **Recommendation:** Make it mandatory from the start - the implementation is solid

2. **Should we log validation timing?**
   - Pro: Can detect performance issues
   - Con: Extra logging noise
   - **Recommendation:** Log at debug level only

3. **What to do if cleanup fails?**
   - Current: Log warning, provide manual instructions
   - Alternative: Attempt multiple cleanup strategies
   - **Recommendation:** Keep current approach - cleanup failure is non-critical

---

## Conclusion

The validation framework is ready for integration. Primary work is in main.py and HunkParser. Integration is low-medium risk with comprehensive test coverage. Estimated 8 hours for full Phase 3 integration.

**Next Phase:** Implement Phase 3 integration following this plan.
