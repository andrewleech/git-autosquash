# Troubleshooting

This guide helps you diagnose and resolve common issues when using git-autosquash.

## Installation Issues

### Command Not Found

**Symptoms**:
```bash
$ git-autosquash
bash: git-autosquash: command not found
```

**Diagnosis**:
```bash
# Check if installed
which git-autosquash
echo $PATH

# Check pipx installation
pipx list | grep git-autosquash
```

**Solutions**:
```bash
# Reinstall with pipx
pipx install git-autosquash

# Or upgrade if already installed
pipx upgrade git-autosquash

# Ensure pipx bin directory in PATH
pipx ensurepath

# Restart shell
exec $SHELL
```

### Permission Issues

**Symptoms**:
```bash
$ git-autosquash
Permission denied
```

**Solutions**:
```bash
# Check file permissions
ls -la $(which git-autosquash)

# Fix permissions if needed
chmod +x $(which git-autosquash)

# Reinstall if permissions are consistently wrong
pipx uninstall git-autosquash
pipx install git-autosquash
```

## Git Repository Issues

### Not in Git Repository

**Symptoms**:
```bash
$ git-autosquash
Error: Not in a git repository
```

**Diagnosis**:
```bash
# Verify current directory
pwd
git status
```

**Solutions**:
```bash
# Navigate to git repository
cd /path/to/your/repo

# Or initialize new repository if intended
git init
```

### Detached HEAD State

**Symptoms**:
```bash
$ git-autosquash
Error: Cannot operate in detached HEAD state
```

**Diagnosis**:
```bash
git branch
# Shows: * (HEAD detached at abc1234)
```

**Solutions**:
```bash
# Switch to a branch
git checkout main

# Or create new branch from current state
git checkout -b feature/new-work

# Or go back to previous branch
git checkout -
```

### No Merge Base Found

**Symptoms**:
```bash
$ git-autosquash
Error: Cannot find merge base with main/master
```

**Diagnosis**:
```bash
# Check branch relationships
git log --oneline --graph --all -10

# Check remote tracking
git branch -vv
```

**Solutions**:
```bash
# Fetch latest from remote
git fetch origin

# Set upstream if missing
git branch --set-upstream-to=origin/main

# Or specify merge base manually in future
git merge-base HEAD origin/main
```

## Working Directory Issues

### Mixed Staged/Unstaged Changes

**Symptoms**:
TUI shows confusing prompt about mixed changes

**Understanding the prompt**:
```bash
# Mixed staged and unstaged changes detected.
# Choose an option:
#   a) Process all changes (staged + unstaged)
#   s) Stash unstaged changes and process only staged  
#   q) Quit
```

**Recommendations**:
- **Option a**: Most common, processes everything together
- **Option s**: Use when you want to be selective about what gets rebased
- **Option q**: Use to manually stage exactly what you want first

**Manual staging approach**:
```bash
# Exit git-autosquash and stage selectively
git add -p  # Interactive staging

# Stage specific files only
git add src/specific/file.py

# Then run git-autosquash again
git-autosquash
```

### Uncommitted Changes Blocking Operation

**Symptoms**:
```bash
Error: Working directory must be clean or have only staged changes
```

**Solutions**:
```bash
# Stash current changes
git stash push -m "Work in progress"

# Or commit changes first
git commit -m "WIP: Current progress"

# Run git-autosquash
git-autosquash

# Restore stashed changes
git stash pop
```

## Diff Analysis Issues

### No Target Commits Found

**Symptoms**:
```bash
No suitable target commits found for any changes.
All changes will remain as new commits.
```

**Common causes**:
1. All changes are in new files
2. Changes are in code sections not present in branch history
3. Changes are outside the merge-base scope

**Diagnosis**:
```bash
# Check what you've changed
git diff --stat

# Check blame for specific files
git blame src/problematic_file.py

# Check branch history
git log --oneline -10
```

**Solutions**:
```bash
# For new files - this is expected behavior
# New files have no history to squash into

# For existing files with no targets:
# 1. Check if changes are in code added after branch point
git log --oneline origin/main..HEAD -- src/problematic_file.py

# 2. Try line-by-line mode for more precision
git-autosquash --line-by-line

# 3. Manual inspection - some changes genuinely belong as new commits
```

### Low Confidence Mappings

**Symptoms**:
TUI shows many red (low confidence) mappings

**Causes**:
- Mixed blame results (multiple commits modified same lines)
- Recent commits dominating blame analysis
- Complex refactoring scenarios

**Solutions**:
```bash
# Use line-by-line mode for better granularity
git-autosquash --line-by-line

# Manually review each mapping carefully
# Red mappings often should be rejected

# For complex scenarios, consider manual organization
git add -p  # Stage related changes together
git commit -m "Organize: specific feature"
git-autosquash  # Process remaining changes
```

## TUI (Terminal Interface) Issues

### TUI Not Working

**Symptoms**:
- Blank screen
- Garbled output  
- Immediate exit

**Diagnosis**:
```bash
# Check terminal capabilities
echo $TERM
tput colors

# Test terminal size
tput lines
tput cols
```

**Solutions**:
```bash
# Try with basic terminal mode
TERM=dumb git-autosquash

# Ensure adequate terminal size (minimum 80x24)
resize

# Update terminal if needed
# For tmux users:
tmux kill-session
tmux new-session

# For screen users:
screen -X quit
screen
```

### Keyboard Navigation Issues

**Symptoms**:
- Arrow keys not working
- Shortcuts not responding

**Solutions**:
```bash
# Use alternative navigation
# j/k instead of arrow keys
# Space for toggle instead of Enter

# Check if running in compatible terminal
echo $TERM
# Should show: xterm-256color, screen-256color, or similar

# Try different terminal emulator
# Terminal.app, iTerm2, gnome-terminal, etc.
```

### Display Corruption

**Symptoms**:
- Overlapping text
- Missing content
- Color issues

**Solutions**:
```bash
# Force terminal reset
reset
clear

# Disable colors
NO_COLOR=1 git-autosquash

# Try different terminal
TERM=xterm git-autosquash
```

## Rebase Execution Issues

### Merge Conflicts During Rebase

**Symptoms**:
```bash
⚠️ Rebase conflicts detected:
  src/auth/login.py
  src/ui/dashboard.py
```

**Understanding conflicts**:
Conflicts occur when the same lines were modified in both the target commit and your changes.

**Resolution process**:
```bash
# 1. Check conflict status
git status

# 2. Open conflicted files
vim src/auth/login.py

# 3. Resolve conflicts (remove conflict markers)
#    <<<<<<< HEAD
#    existing code
#    =======
#    your changes
#    >>>>>>> commit-message

# 4. Stage resolved files
git add src/auth/login.py src/ui/dashboard.py

# 5. Continue rebase
git rebase --continue

# git-autosquash will continue processing remaining commits
```

**Abort if needed**:
```bash
# If conflicts are too complex
git rebase --abort

# Try different approach
git-autosquash --line-by-line
```

### Rebase Fails to Complete

**Symptoms**:
```bash
error: could not apply abc1234... commit message
```

**Diagnosis**:
```bash
# Check rebase status
git status

# Check what's happening
cat .git/rebase-merge/msgnum
cat .git/rebase-merge/end
```

**Solutions**:
```bash
# If rebase is stuck
git rebase --skip  # Skip problematic commit
# or
git rebase --abort  # Start over

# Clean up any partial state
git reset --hard HEAD
git clean -fd

# Try git-autosquash again with different options
```

### Force Push Required

**Symptoms**:
After successful git-autosquash, `git push` fails:
```bash
! [rejected] feature-branch -> feature-branch (non-fast-forward)
```

**Understanding**:
git-autosquash rewrites history, so force push is required.

**Safe force push**:
```bash
# Use --force-with-lease for safety
git push --force-with-lease origin feature-branch

# This fails if remote has commits you don't have locally
# (protects against overwriting others' work)
```

**If force-with-lease fails**:
```bash
# Fetch and check what changed
git fetch origin
git log HEAD..origin/feature-branch

# If safe to proceed
git push --force origin feature-branch

# If others have pushed commits, coordinate with team first
```

## Performance Issues

### Slow Blame Analysis

**Symptoms**:
git-autosquash hangs or runs very slowly

**Causes**:
- Large repository history
- Many files changed
- Large individual files

**Solutions**:
```bash
# Check repository size
du -sh .git/
git count-objects -vH

# Optimize git repository
git gc --aggressive
git prune

# Process changes in smaller batches
git stash push -m "Batch 2" -- src/large_module/
git-autosquash  # Process remaining
git stash pop
git-autosquash  # Process batch 2
```

### Memory Issues

**Symptoms**:
```bash
MemoryError: Unable to allocate array
# or system becomes unresponsive
```

**Solutions**:
```bash
# Monitor memory usage
/usr/bin/time -v git-autosquash

# Process fewer files at once
git add src/specific_module/
git-autosquash
# Process only staged changes

# Increase system swap if needed
sudo swapon --show
```

### TUI Performance Issues

**Symptoms**:
- Slow scrolling
- Laggy keyboard response
- High CPU usage

**Solutions**:
```bash
# Reduce terminal complexity
TERM=xterm git-autosquash

# Use smaller terminal window
# Reduce number of visible items

# Try fallback text mode
# (git-autosquash automatically falls back if TUI fails)
```

## Error Messages and Solutions

### "fatal: ambiguous argument"

**Full error**:
```bash
fatal: ambiguous argument 'HEAD~1': unknown revision or path not found.
```

**Cause**: Branch has only one commit

**Solutions**:
```bash
# Check commit count
git rev-list --count HEAD

# If only one commit, nothing to squash into
# This is expected behavior

# Add more commits to have squash targets
git commit -m "Add more functionality"
# Then git-autosquash will have targets
```

### "error: pathspec did not match any file(s)"

**Cause**: File was renamed or deleted

**Solutions**:
```bash
# Check git status
git status --porcelain

# Handle renames properly
git add -A  # Stage all changes including renames
git-autosquash
```

### "fatal: refusing to merge unrelated histories"

**Cause**: Branch history is disconnected from main

**Solutions**:
```bash
# Check branch relationships
git log --oneline --graph --all -20

# If branches are truly unrelated, this is expected
# git-autosquash requires shared history

# To force relationship (dangerous):
git rebase --root --onto main
```

## Recovery Procedures

### Recovering from Failed git-autosquash

If git-autosquash leaves repository in unexpected state:

```bash
# 1. Check reflog for previous state
git reflog -10

# 2. Reset to previous good state
git reset --hard HEAD@{N}  # Replace N with appropriate number

# 3. Verify state
git status
git log --oneline -5

# 4. Try alternative approach
git-autosquash --line-by-line  # More conservative
```

### Emergency Abort

If git-autosquash seems stuck or unresponsive:

```bash
# 1. Kill process (Ctrl+C in terminal)

# 2. Check for ongoing rebase
git status

# 3. Abort any ongoing rebase
git rebase --abort

# 4. Clean working directory
git reset --hard HEAD
git clean -fd

# 5. Check repository state
git status
git log --oneline -5
```

## Getting Help

### Diagnostic Information

When reporting issues, include:

```bash
# Version information
git-autosquash --version
git --version
python --version

# System information
uname -a
echo $TERM

# Repository state
git status --porcelain
git log --oneline -10
git diff --stat

# Error output
git-autosquash 2>&1 | tee error.log
```

### Debug Mode

Enable verbose output for troubleshooting:

```bash
# Git operation tracing
GIT_TRACE=1 git-autosquash

# More detailed git tracing
GIT_TRACE=2 GIT_TRACE_SETUP=1 git-autosquash

# Python traceback for errors
python -X dev -c "import subprocess; subprocess.run(['git-autosquash'])"
```

For issues not covered here, please report them at https://github.com/andrewleech/git-autosquash/issues with diagnostic information included.