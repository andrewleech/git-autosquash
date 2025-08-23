# Frequently Asked Questions

## General Questions

### What is git-autosquash?

git-autosquash is a tool that automatically organizes your uncommitted changes by squashing them back into the historical commits where those code sections were last modified. Instead of creating messy "fix typo" or "address review feedback" commits, it integrates improvements directly into the commits they logically belong to.

### How is this different from `git rebase --autosquash`?

`git rebase --autosquash` requires you to manually create fixup/squash commits first, then run the rebase. git-autosquash analyzes your working directory changes and automatically determines which historical commits they should be squashed into using git blame analysis.

### Is git-autosquash safe to use?

Yes, git-autosquash is designed with safety in mind:
- It never automatically executes changes without user approval
- The TUI shows exactly what will happen before execution
- You can abort at any time during the process
- All operations are standard git operations that can be undone
- It only operates on your local branch, never affecting remote repositories

### What if I make a mistake?

You can always undo git-autosquash operations:

```bash
# Find the previous state in reflog
git reflog

# Reset to previous state  
git reset --hard HEAD@{N}  # Replace N with appropriate entry

# Or create backup branch before running
git branch backup-before-autosquash
git-autosquash
# If needed: git reset --hard backup-before-autosquash
```

## Installation and Setup

### How do I install git-autosquash?

The recommended installation method is using pipx:

```bash
pipx install git-autosquash
```

For other installation methods, see the [Getting Started Guide](../user-guide/getting-started.md).

### Can I use git-autosquash without pipx?

Yes, you can install with regular pip:

```bash
pip install git-autosquash
```

However, pipx is recommended because it isolates git-autosquash in its own environment, preventing conflicts with other Python packages.

### How do I update git-autosquash?

```bash
# With pipx (recommended)
pipx upgrade git-autosquash

# With pip
pip install --upgrade git-autosquash
```

### Does git-autosquash work on Windows?

Yes, git-autosquash works on Windows, macOS, and Linux. However, Windows users may need:
- A terminal that supports ANSI color codes (Windows Terminal, PowerShell 7+)
- Git for Windows or similar git installation
- Python 3.9 or later

## Usage Questions

### When should I use git-autosquash?

git-autosquash is most useful when:
- You fix bugs while working on new features
- You address code review feedback affecting multiple commits
- You make improvements to existing code during development
- You want to maintain clean, logical commit history
- You're refactoring and want improvements integrated with original implementations

### When should I NOT use git-autosquash?

Avoid git-autosquash when:
- Working on main/master branch directly (use feature branches)
- Changes are truly independent and deserve their own commits
- You're not familiar with git rebase and conflict resolution
- Working on shared branches without team coordination
- Repository is in unusual state (detached HEAD, corrupt history)

### What's the difference between standard and line-by-line mode?

**Standard mode** (`git-autosquash`):
- Uses git's default hunk boundaries
- Faster analysis
- Good for most scenarios
- Groups related changes together

**Line-by-line mode** (`git-autosquash --line-by-line`):
- Analyzes each changed line individually
- More precise targeting
- Slower but more granular control
- Better for complex refactoring or mixed changes

### How does git-autosquash decide where changes should go?

git-autosquash uses git blame to analyze who last modified each line of code. It then:

1. **Counts frequency**: How many lines in each hunk were last modified by each commit
2. **Selects target**: Chooses the commit that modified the most lines (frequency-first)
3. **Breaks ties**: If multiple commits have same frequency, chooses the more recent one
4. **Filters scope**: Only considers commits on the current branch back to the merge-base with main

### What does the confidence level mean?

Confidence indicates how certain git-autosquash is about the target:

- **High (Green)**: All or most lines blame to the same commit - very likely correct
- **Medium (Yellow)**: Majority of lines blame to target commit - probably correct
- **Low (Red)**: Mixed blame results - might be incorrect, review carefully

Low confidence often means changes affect code from multiple commits and might be better as a new commit.

## Technical Questions

### Can git-autosquash handle merge conflicts?

Yes, but conflicts require manual resolution. When conflicts occur:

1. git-autosquash pauses and shows conflicted files
2. You resolve conflicts manually in your editor
3. Stage resolved files with `git add`
4. Continue with `git rebase --continue`
5. git-autosquash completes the remaining operations

For complex conflicts, you can abort with `git rebase --abort` and try a different approach.

### Does git-autosquash work with large repositories?

Yes, git-autosquash is designed to work efficiently with large repositories:

- Blame analysis is cached during each session
- Files are processed incrementally to manage memory
- Performance optimizations for repositories with extensive history
- Reasonable performance even with thousands of commits

For very large repositories, the first run may be slower as caches are built.

### Can I use git-autosquash on shared branches?

Use caution with shared branches:

1. **Coordinate with team**: Let others know you'll be rebasing
2. **Force push required**: After git-autosquash, you need `git push --force-with-lease`
3. **Team must update**: Others need to rebase their local copies

It's safer to use git-autosquash on personal feature branches before sharing.

### What Git version is required?

git-autosquash requires Git 2.25 or later for:
- Modern `git diff` output format
- Reliable `git blame` behavior  
- Interactive rebase features
- Proper conflict handling

### Does git-autosquash modify my git configuration?

No, git-autosquash never modifies your permanent git configuration. It may temporarily set environment variables during rebase operations, but these don't persist after the session ends.

## Workflow Questions

### How do I integrate git-autosquash into my development workflow?

Common integration patterns:

**Before committing**:
```bash
# Make changes throughout the day
git-autosquash  # Organize changes
git commit -m "Add user authentication feature"
```

**Before creating pull request**:
```bash
# Clean up branch history
git-autosquash
git push --force-with-lease origin feature-branch
```

**After addressing code review**:
```bash
# Make review changes
git-autosquash  # Distribute fixes to appropriate commits
git push --force-with-lease
```

### Can I use git-autosquash with pre-commit hooks?

Yes, you can integrate with pre-commit hooks, but be careful about automation:

```bash
#!/bin/bash
# .git/hooks/pre-commit
if ! git diff --quiet; then
    echo "Uncommitted changes detected."
    echo "Consider running 'git-autosquash' first."
    read -p "Continue with commit? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
```

Avoid automatically running git-autosquash in hooks - the interactive nature requires user decision-making.

### How do I handle file renames?

git-autosquash handles file renames automatically when git detects them. Ensure renames are properly staged:

```bash
# Git automatically detects renames when files are >50% similar
git add old_file.py new_file.py
git status  # Should show "renamed: old_file.py -> new_file.py"
git-autosquash
```

If git doesn't detect the rename, you may need to handle it manually before running git-autosquash.

## Error and Troubleshooting

### Why do I get "No target commits found"?

This happens when:
- All changes are in new files (expected - no history to squash into)
- Changes are outside the branch scope (before merge-base with main)
- Git blame can't find clear ownership (e.g., heavily refactored code)

This is often normal behavior. New functionality should remain as new commits.

### The TUI doesn't work on my system

Try these solutions:

```bash
# Check terminal capabilities
echo $TERM
tput colors

# Try different terminal setting
TERM=xterm-256color git-autosquash

# Force basic mode
TERM=dumb git-autosquash

# Disable colors
NO_COLOR=1 git-autosquash
```

The TUI requires a terminal with basic cursor movement support. It automatically falls back to text-based prompts if the TUI fails.

### git-autosquash is slow on my repository

Performance optimization steps:

```bash
# Clean up repository
git gc --aggressive
git prune

# Check repository size
du -sh .git/

# Try line-by-line for better precision (may be faster for complex changes)
git-autosquash --line-by-line

# Process changes in smaller batches
git stash push -m "batch2" -- large_module/
git-autosquash  # Process remaining
git stash pop
git-autosquash  # Process batch2
```

### Can I customize the TUI colors or shortcuts?

Currently, git-autosquash uses standard colors and shortcuts that aren't customizable. However:

- Colors respect the `NO_COLOR` environment variable
- Terminal capabilities are automatically detected
- Shortcuts follow vim-like conventions (j/k for navigation)

Future versions may add more customization options.

## Comparison Questions

### How does git-autosquash compare to other Git tools?

**vs `git rebase -i`**:
- git-autosquash automatically determines what should be squashed
- No manual editing of rebase todo lists
- Uses blame analysis instead of manual decision-making

**vs `git commit --fixup`**:
- No need to identify target commits manually
- Works on working directory changes, not just commits  
- Handles multiple targets automatically

**vs `git absorb`**:
- Similar concept but different implementation
- git-autosquash provides interactive TUI for approval
- Different algorithms for target selection

### Should I use git-autosquash or traditional git rebase?

Use git-autosquash when:
- You want intelligent automation for common squash scenarios
- You frequently fix bugs in existing commits during development
- You want to maintain clean history without manual analysis

Use traditional rebase when:
- You need complete control over commit organization
- You're doing complex history manipulation
- You're comfortable with manual interactive rebase

They're complementary tools - you can use both in your workflow as appropriate.

For more specific questions, check the [Troubleshooting Guide](../user-guide/troubleshooting.md) or report issues at https://github.com/andrewleech/git-autosquash/issues.