# Advanced Usage

This guide covers advanced git-autosquash features and workflows for power users and complex scenarios.

## Advanced Command-Line Options

### Line-by-Line Mode

The `--line-by-line` option provides maximum precision when analyzing changes:

```bash
git-autosquash --line-by-line
```

**When to use**:
- Mixed commits affecting same code section
- Review feedback requiring precise targeting
- Unrelated changes bundled together by git's default hunking

**Performance trade-offs**:
- Slower analysis (each line evaluated separately)
- More granular control
- Better separation of unrelated changes

### Environment Variable Control

Control git-autosquash behavior through environment variables:

```bash
# Disable colors for scripting
NO_COLOR=1 git-autosquash

# Force specific terminal capabilities
TERM=xterm-256color git-autosquash

# Debug git operations
GIT_TRACE=1 git-autosquash
```

## Advanced Workflows

### Multi-Stage Development

For complex features spanning multiple commits:

```bash
# Stage 1: Initial implementation
git commit -m "Add user authentication framework"

# Stage 2: Add OAuth support + fix bugs in Stage 1
# (working directory has mixed changes)
git-autosquash
# OAuth changes stay as new commit
# Bug fixes go back to Stage 1 commit

# Stage 3: Continue with more features
git commit -m "Add OAuth provider configuration"
```

### Handling Large Refactoring

When refactoring affects many files and historical commits:

```bash
# After large refactoring session
git status --porcelain | wc -l
# 50+ modified files

# Use line-by-line for precision
git-autosquash --line-by-line

# Review carefully - large refactorings often have mixed intentions
```

### Branch Cleanup Workflows

#### Pre-merge Cleanup

```bash
# Before creating pull request
git checkout feature/user-dashboard
git-autosquash  # Clean up the branch history

# Verify results
git log --oneline origin/main..HEAD

# Push cleaned branch
git push --force-with-lease origin feature/user-dashboard
```

#### Post-review Cleanup

```bash
# After addressing code review feedback
git-autosquash  # Distribute fixes back to original commits

# Amend latest commit if needed
git commit --amend -m "Add user dashboard with analytics"

# Force push cleaned history
git push --force-with-lease
```

## Complex Scenarios

### Handling Merge Conflicts

When rebase conflicts occur during git-autosquash execution:

```bash
git-autosquash
# ... conflicts detected ...

# Resolve conflicts manually
git status  # Shows conflicted files
vim src/auth/login.py  # Edit and resolve

# Stage resolved files
git add src/auth/login.py

# Continue rebase
git rebase --continue

# git-autosquash will continue with remaining commits
```

**Recovery options**:
```bash
# If conflicts are too complex, abort and try different approach
git rebase --abort

# Try with different hunk splitting
git-autosquash --line-by-line

# Or process fewer changes at once
git stash push -m "Save some changes"
git-autosquash
git stash pop
```

### Working with Shared Branches

**Team coordination**:
```bash
# Before running git-autosquash on shared branch
git fetch origin
git status  # Ensure you're up to date

# Coordinate with team
echo "Running git-autosquash on shared branch, will force-push after"

git-autosquash
git push --force-with-lease origin feature/shared-work

# Notify team to rebase their local copies
echo "Branch rebased, run: git pull --rebase"
```

### Partial Staging Workflows

Control exactly which changes get processed:

```bash
# Stage only specific changes
git add -p src/auth/login.py  # Interactively stage hunks

# Process only staged changes
git-autosquash
# Choose option 's' to stash unstaged and process staged only

# Later, unstash and process remaining changes
git stash pop
git-autosquash
```

## Performance Optimization

### Caching and Performance

git-autosquash includes several performance optimizations:

**Blame caching**:
- Commit metadata cached between runs
- Branch scope filtering cached
- File blame results cached per session

**Large repository strategies**:
```bash
# For very large repos, limit scope
git-autosquash  # Only processes changes since last commit

# For extensive changes, use line-by-line for precision
git-autosquash --line-by-line  # Slower but more accurate
```

### Memory and Disk Usage

**Memory optimization**:
- Diff parsing uses generators for large files
- Blame analysis processes files incrementally
- TUI updates use efficient reactive patterns

**Disk usage considerations**:
- Temporary rebase files in `.git/rebase-merge/`
- Stash entries if using staged-only mode
- Git object database growth during rebase

## Integration Patterns

### Git Hooks Integration

#### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

if ! git diff --cached --quiet; then
    echo "Staged changes detected."
    echo "Consider running 'git-autosquash' to organize changes."
    
    # Optional: Fail commit if working directory is dirty
    if ! git diff --quiet; then
        echo "Working directory has unstaged changes."
        echo "Run 'git-autosquash' first to organize all changes."
        exit 1
    fi
fi
```

#### Pre-push Hook

```bash
#!/bin/bash
# .git/hooks/pre-push

branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" != "main" && "$branch" != "master" ]]; then
    if ! git diff --quiet; then
        echo "Uncommitted changes on branch $branch"
        read -p "Consider running git-autosquash first. Continue? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi
```

### IDE and Editor Integration

#### VS Code Tasks

```json
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "git-autosquash",
            "type": "shell",
            "command": "git-autosquash",
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": true,
                "panel": "new"
            },
            "problemMatcher": []
        },
        {
            "label": "git-autosquash (precise)",
            "type": "shell",
            "command": "git-autosquash",
            "args": ["--line-by-line"],
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always", 
                "focus": true,
                "panel": "new"
            }
        }
    ]
}
```

#### Vim/Neovim

```vim
" Add to .vimrc or init.vim

" Quick git-autosquash
nnoremap <leader>ga :!git-autosquash<CR>

" Line-by-line mode
nnoremap <leader>gA :!git-autosquash --line-by-line<CR>

" Function to check if autosquash would be useful
function! CheckAutosquash()
    let l:status = system('git diff --quiet')
    if v:shell_error != 0
        echo "Changes detected - git-autosquash might be useful"
        call system('git diff --stat')
    else
        echo "No changes to analyze"
    endif
endfunction

command! CheckAutosquash call CheckAutosquash()
```

### Makefile Integration

```makefile
.PHONY: autosquash autosquash-precise check-autosquash

# Standard autosquash
autosquash:
	@echo "Running git-autosquash..."
	@git-autosquash

# Line-by-line precision mode
autosquash-precise:
	@echo "Running git-autosquash with line-by-line precision..."
	@git-autosquash --line-by-line

# Check if autosquash would be useful
check-autosquash:
	@if ! git diff --quiet; then \
		echo "Changes detected:"; \
		git diff --stat; \
		echo "Consider running 'make autosquash'"; \
	else \
		echo "No changes to analyze"; \
	fi

# Pre-commit target
pre-commit: check-autosquash
	@echo "Ready for commit"
```

## Scripting and Automation

### Batch Processing Scripts

```bash
#!/bin/bash
# bulk-autosquash.sh - Process multiple feature branches

branches=(
    "feature/user-auth"
    "feature/dashboard-ui" 
    "feature/api-endpoints"
)

for branch in "${branches[@]}"; do
    echo "Processing branch: $branch"
    git checkout "$branch"
    
    if ! git diff --quiet; then
        echo "Running git-autosquash on $branch..."
        git-autosquash
        
        if [ $? -eq 0 ]; then
            echo "✓ $branch processed successfully"
            git push --force-with-lease origin "$branch"
        else
            echo "✗ $branch failed, skipping push"
        fi
    else
        echo "No changes in $branch, skipping"
    fi
    echo "---"
done

git checkout main
```

### CI/CD Integration

```yaml
# .github/workflows/autosquash-check.yml
name: Check Autosquash Opportunities
on: [pull_request]

jobs:
  check-organization:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          
      - name: Install git-autosquash
        run: pipx install git-autosquash
        
      - name: Check for organization opportunities
        run: |
          if ! git diff --quiet origin/main..HEAD; then
            echo "::notice::Branch has changes that might benefit from git-autosquash"
            echo "::notice::Consider running git-autosquash to organize commits"
            
            # Count potential targets (for metrics)
            echo "Commits in branch: $(git rev-list --count origin/main..HEAD)"
            echo "Files changed: $(git diff --name-only origin/main..HEAD | wc -l)"
          fi
```

## Troubleshooting Advanced Scenarios

### Performance Issues

**Slow blame analysis**:
```bash
# Check repository size
du -sh .git/
git count-objects -vH

# Large repositories may benefit from:
git gc --aggressive  # Cleanup and optimize
git-autosquash --line-by-line  # More precise, potentially faster for complex changes
```

**Memory usage**:
```bash
# Monitor memory usage during operation
/usr/bin/time -v git-autosquash

# For very large changesets, process in smaller batches
git stash push -m "Batch 2" -- src/module2/
git-autosquash  # Process batch 1
git stash pop
git-autosquash  # Process batch 2
```

### Complex Conflict Resolution

**Systematic conflict resolution**:
```bash
git-autosquash
# Conflicts in multiple files...

# Resolve conflicts systematically
git status --porcelain | grep "^UU" | cut -c4- | while read file; do
    echo "Resolving: $file"
    # Open each file individually
    ${EDITOR:-vim} "$file"
    git add "$file"
done

git rebase --continue
```

**Recovery from failed rebase**:
```bash
# If rebase gets too complex
git rebase --abort

# Try different approach
git stash push -m "Complex changes"
git-autosquash  # Process simpler changes first
git stash pop
# Manually organize complex changes
```

### Branch History Issues

**Fixing corrupted branch history**:
```bash
# If git-autosquash results in unexpected history
git reflog  # Find previous state
git reset --hard HEAD@{N}  # Reset to previous state

# Try alternative approaches
git-autosquash --line-by-line  # More precision
# Or process changes manually
```

For more troubleshooting scenarios, see [Troubleshooting Guide](troubleshooting.md).