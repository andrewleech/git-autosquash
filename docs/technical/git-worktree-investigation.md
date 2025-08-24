# Git Worktree Investigation for Enhanced Hunk Processing

## Current Approach Analysis

Our current git-native handler uses index manipulation within the main working tree:

1. **Capture index state** using `git write-tree`
2. **Stage hunks individually** using `git apply --cached` 
3. **Generate combined patch** using `git diff --cached`
4. **Restore index** using `git read-tree`
5. **Apply final patch** to working tree using `git apply`

### Limitations of Current Index-Based Approach

1. **Index Pollution**: Temporarily modifies the main repository's index
2. **Race Conditions**: Other git operations during processing could interfere
3. **Complex State Management**: Need to carefully restore index state
4. **Single Threading**: Only one operation can safely modify index at a time

## Git Worktree Alternative

Git worktree provides isolated working directories that share the same repository but have:
- **Separate working tree**: Each worktree has its own file checkout
- **Separate index**: Each worktree maintains its own staging area
- **Shared object database**: All worktrees share commits, branches, tags
- **Shared references**: All worktrees see the same branches and remotes

### Potential Benefits

1. **Complete Isolation**: Each hunk processing operation in separate worktree
2. **Parallel Processing**: Multiple worktrees can process hunks simultaneously
3. **No Index Contamination**: Main repository index remains untouched
4. **Atomic Operations**: Each worktree can be created/destroyed atomically
5. **Simplified Cleanup**: Remove worktree removes all associated state

### Proposed Worktree-Based Approach

```python
class GitWorktreeIgnoreHandler:
    \"\"\"Enhanced ignore handler using git worktree for complete isolation.\"\"\"
    
    def apply_ignored_hunks(self, ignored_mappings: List[HunkTargetMapping]) -> bool:
        \"\"\"Apply ignored hunks using isolated git worktrees.\"\"\"
        
        # Phase 1: Create comprehensive backup (same as current)
        backup_stash = self._create_comprehensive_backup()
        
        try:
            # Phase 2: Create temporary worktree for hunk processing  
            worktree_path = self._create_temporary_worktree()
            
            # Phase 3: Apply hunks in isolated environment
            success = self._apply_hunks_in_worktree(ignored_mappings, worktree_path)
            
            if success:
                # Phase 4: Extract processed changes back to main worktree
                self._extract_changes_from_worktree(worktree_path)
                return True
            else:
                # Phase 5: Restore from backup on failure
                self._restore_from_stash(backup_stash)
                return False
                
        finally:
            # Phase 6: Cleanup temporary worktree and backup
            self._cleanup_worktree(worktree_path)
            self._cleanup_stash(backup_stash)
```

### Implementation Details

#### 1. Temporary Worktree Creation

```python
def _create_temporary_worktree(self) -> str:
    \"\"\"Create temporary worktree for isolated hunk processing.\"\"\"
    
    # Generate unique worktree path
    timestamp = int(time.time())
    worktree_name = f"git-autosquash-temp-{timestamp}"
    worktree_path = f"/tmp/{worktree_name}"
    
    # Create detached worktree at current HEAD
    success, _ = self.git_ops._run_git_command(
        "worktree", "add", "--detach", worktree_path, "HEAD"
    )
    
    if success:
        return worktree_path
    else:
        raise RuntimeError("Failed to create temporary worktree")
```

#### 2. Isolated Hunk Application

```python  
def _apply_hunks_in_worktree(self, mappings: List[HunkTargetMapping], worktree_path: str) -> bool:
    \"\"\"Apply hunks within isolated worktree environment.\"\"\"
    
    # Create git operations instance for the worktree
    worktree_git_ops = GitOps(worktree_path)
    
    # Apply each hunk directly to worktree files
    for mapping in mappings:
        hunk_patch = self._create_minimal_patch_for_hunk(mapping.hunk)
        
        # Apply patch directly in worktree (no --cached needed)
        success, error = worktree_git_ops._run_git_command_with_input(
            "apply", input_text=hunk_patch
        )
        
        if not success:
            self.logger.error(f"Failed to apply hunk in worktree: {error}")
            return False
    
    return True
```

#### 3. Change Extraction

```python
def _extract_changes_from_worktree(self, worktree_path: str) -> bool:
    \"\"\"Extract processed changes from worktree back to main repository.\"\"\"
    
    # Generate patch of all changes in worktree
    worktree_git_ops = GitOps(worktree_path)
    success, patch_content = worktree_git_ops._run_git_command(
        "diff", "HEAD"
    )
    
    if not success or not patch_content.strip():
        self.logger.warning("No changes found in worktree to extract")
        return True
    
    # Apply the extracted patch to main working tree
    success, error = self.git_ops._run_git_command_with_input(
        "apply", input_text=patch_content
    )
    
    if success:
        self.logger.info("Successfully extracted changes from worktree")
        return True
    else:
        self.logger.error(f"Failed to extract changes from worktree: {error}")
        return False
```

#### 4. Cleanup

```python
def _cleanup_worktree(self, worktree_path: str) -> None:
    \"\"\"Remove temporary worktree and associated metadata.\"\"\"
    
    if not worktree_path:
        return
        
    # Remove worktree (this also cleans up git metadata)
    success, output = self.git_ops._run_git_command(
        "worktree", "remove", "--force", worktree_path
    )
    
    if success:
        self.logger.debug(f"Cleaned up temporary worktree: {worktree_path}")
    else:
        self.logger.warning(f"Failed to cleanup worktree {worktree_path}: {output}")
        # Attempt manual cleanup
        try:
            import shutil
            shutil.rmtree(worktree_path, ignore_errors=True)
        except Exception as e:
            self.logger.warning(f"Manual worktree cleanup failed: {e}")
```

## Performance Analysis

### Current Index Approach Performance

**Operations per hunk application:**
- 1x write-tree (capture index)
- 1x hash-object (blob info)
- 1x rev-parse (blob info) 
- 1x ls-files (blob info)
- 1x apply --cached (stage hunk)
- 1x read-tree (restore index)
- 1x diff --cached (generate patch)
- 1x apply --check + 1x apply (validate + apply)

**Total: ~8 git operations per batch + 1 per hunk**

### Proposed Worktree Approach Performance

**Operations per hunk application:**
- 1x worktree add (create isolated environment)
- 1x apply per hunk (direct application, no staging needed)
- 1x diff HEAD (extract changes)
- 1x apply (apply to main worktree)
- 1x worktree remove (cleanup)

**Total: ~5 git operations per batch + 1 per hunk**

### Benefits Analysis

1. **Reduced Complexity**: No index state management
2. **Better Isolation**: Complete separation from main repository state
3. **Potential Parallelization**: Multiple worktrees can be processed simultaneously
4. **Simpler Error Recovery**: Worktree removal cleans all state
5. **More Natural Git Operations**: Direct file application vs index manipulation

## Security Considerations

### Temporary Directory Security

```python
def _create_secure_worktree_path(self) -> str:
    \"\"\"Create secure temporary directory for worktree.\"\"\"
    
    import tempfile
    import os
    
    # Create secure temporary directory
    temp_dir = tempfile.mkdtemp(prefix="git-autosquash-", suffix="-worktree")
    
    # Ensure proper permissions (owner only)
    os.chmod(temp_dir, 0o700)
    
    return temp_dir
```

### Path Validation

Same path validation as current approach, but applied within worktree context:

```python
def _validate_worktree_paths(self, mappings: List[HunkTargetMapping], worktree_path: str) -> bool:
    \"\"\"Validate paths within worktree context.\"\"\"
    
    worktree_root = Path(worktree_path).resolve()
    
    for mapping in mappings:
        file_path = Path(mapping.hunk.file_path)
        
        # Same validation as current approach
        if file_path.is_absolute():
            return False
            
        resolved_path = (worktree_root / file_path).resolve()
        try:
            resolved_path.relative_to(worktree_root)
        except ValueError:
            return False
    
    return True
```

## Compatibility Analysis

### Git Version Requirements

Git worktree was introduced in Git 2.5.0 (July 2015). Most modern systems should support it.

```python
def _check_worktree_support(self) -> bool:
    \"\"\"Check if git worktree is supported.\"\"\"
    
    success, output = self.git_ops._run_git_command("worktree", "--help")
    return success and "add" in output
```

### Fallback Strategy

```python
def apply_ignored_hunks(self, ignored_mappings: List[HunkTargetMapping]) -> bool:
    \"\"\"Apply hunks with worktree if available, fallback to index approach.\"\"\"
    
    if self._check_worktree_support():
        self.logger.debug("Using git worktree approach for hunk processing")
        return self._apply_with_worktree(ignored_mappings)
    else:
        self.logger.debug("Falling back to index-based approach")
        return self._apply_with_index(ignored_mappings)
```

## Recommendation

The git worktree approach offers significant advantages:

1. **Complete Isolation**: No interference with main repository state
2. **Simplified Implementation**: Fewer state management concerns  
3. **Better Error Handling**: Atomic cleanup via worktree removal
4. **Future Extensibility**: Foundation for parallel processing

### Implementation Plan

1. **Phase 1**: Implement worktree-based handler alongside current approach
2. **Phase 2**: Add feature flag for selecting approach  
3. **Phase 3**: Performance testing and validation
4. **Phase 4**: Gradual migration with fallback support
5. **Phase 5**: Full replacement after validation period

The worktree approach represents a significant improvement in architecture while maintaining the security and reliability benefits of the current git-native implementation.