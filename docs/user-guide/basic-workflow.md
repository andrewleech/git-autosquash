# Basic Workflow

Common git-autosquash usage patterns for day-to-day development.

## Standard Development Workflow

### 1. Feature Development with Bug Fixes

Working on a feature branch while discovering bugs in existing code that should be fixed in their original commits.

**Scenario**: Adding user authentication and noticing a validation bug in existing login code.

```bash
# You're on a feature branch
git checkout -b feature/oauth-integration

# Make changes to multiple files
vim src/auth/oauth.py      # New OAuth implementation
vim src/auth/login.py      # Fix validation bug in existing code
vim src/ui/login_form.py   # Update form for OAuth

# Check what you've changed
git status
# modified:   src/auth/oauth.py
# modified:   src/auth/login.py
# modified:   src/ui/login_form.py

# Run git-autosquash
git-autosquash
```

**Expected Results**:
- OAuth implementation changes → Stay in current working directory (no target found)
- Login validation fix → Goes back to commit that introduced the login functionality
- Form updates → Mixed (some to original form commit, some stay as new feature)

### 2. Code Cleanup and Refactoring

After refactoring code, distribute improvements back to their logical commits.

```bash
# After refactoring session
git status
# modified:   src/database/models.py     # Performance improvements
# modified:   src/api/handlers.py        # Error handling improvements
# modified:   src/utils/validation.py    # Code style cleanup

git-autosquash
```

The TUI shows which improvements can go back to the commits that originally introduced each piece of functionality.

### 3. Mixed Staged and Unstaged Changes

git-autosquash handles different working tree states:

```bash
# Some changes staged, others not
git add src/auth/login.py
git status
# Changes to be committed:
#   modified:   src/auth/login.py
# Changes not staged for commit:
#   modified:   src/ui/dashboard.py
#   modified:   src/utils/helpers.py

git-autosquash
# Mixed staged and unstaged changes detected.
# Choose an option:
#   a) Process all changes (staged + unstaged)
#   s) Stash unstaged changes and process only staged
#   q) Quit
```

Recommended approach:
- **Option a**: Most common choice, processes all changes together
- **Option s**: Use when you want to be careful about what gets rebased
- **Option q**: Use to manually stage exactly what you want first

## TUI Navigation Patterns

### Efficient Review Workflow

1. **Quick scan**: Use ↑/↓ to quickly review all mappings first
2. **Detailed review**: For each mapping:
   - Check the target commit message and date
   - Review the diff in the right panel
   - Consider the confidence level
3. **Batch approval**: Use `a` to toggle all if most look good, then manually adjust
4. **Execute**: Press Enter when satisfied

### Confidence Level Strategy

**High Confidence** (Green):
- Usually safe to approve automatically
- All lines blame to the target commit
- Clear logical connection

**Medium Confidence** (Yellow):
- Review the diff carefully
- Most lines match but some uncertainty
- Consider the logical relationship

**Low Confidence** (Red):
- Be cautious
- Mixed blame results or newer commits involved
- Often better to leave as new changes

### Keyboard Shortcuts Reference

| Action | Key | Description |
|--------|-----|-------------|
| Navigate | ↑↓ or jk | Move between hunk mappings |
| Cycle states | Space | Cycle current hunk: skip → squash → ignore → skip |
| Toggle squash all | a | Toggle all hunks between squash and skip |
| Toggle ignore all | i | Toggle all hunks between ignore and skip |
| Execute | Enter | Start rebase with approved changes |
| Cancel | Escape or q | Abort operation |

## Working Tree State Handling

git-autosquash intelligently handles different working tree states to ensure you can run it at any time during your development workflow.

### Scenario 1: Clean Working Tree
When your working tree is clean (no staged or unstaged changes):

```bash
git status
# On branch feature/auth
# Your branch is ahead of 'origin/main' by 3 commits.
# nothing to commit, working tree clean

git-autosquash
```

**Behavior**: Processes the HEAD commit, allowing you to split it up and distribute changes to earlier commits.

### Scenario 2: Staged Changes Only
When you have staged changes ready to commit:

```bash
git status
# On branch feature/auth
# Changes to be committed:
#   (use "git restore --staged <file>..." to unstage)
#         modified:   src/auth/login.py
#         modified:   src/ui/forms.py

git-autosquash
# No stashing warnings - processes staged changes directly
```

**Behavior**:
- No stashing needed
- Processes only the staged changes
- Staged changes remain in index after operation

### Scenario 3: Unstaged Changes Only
When you have unstaged changes in your working tree:

```bash
git status
# On branch feature/auth
# Changes not staged for commit:
#   (use "git add <file>..." to update what will be committed)
#         modified:   src/auth/login.py
#         modified:   src/ui/forms.py

git-autosquash
# No stashing warnings - processes unstaged changes directly
```

**Behavior**:
- No stashing needed
- Processes the unstaged changes
- Working tree changes remain after operation

### Scenario 4: Mixed Staged and Unstaged Changes
When you have both staged and unstaged changes:

```bash
git status
# On branch feature/auth
# Changes to be committed:
#   (use "git restore --staged <file>..." to unstage)
#         modified:   src/auth/login.py
# Changes not staged for commit:
#   (use "git add <file>..." to update what will be committed)
#         modified:   src/ui/forms.py

git-autosquash
# ⚠️  Working tree has both staged and unstaged changes.
# Unstaged changes will be temporarily stashed while processing staged changes.
# Choose an option:
#   c) Continue (unstaged changes will be temporarily stashed)
#   q) Quit
```

**Behavior**:
- Temporarily stashes **only the unstaged changes** (using `git stash --keep-index`)
- Processes **only the staged changes**
- Automatically restores unstaged changes after completion
- Staged changes remain staged if not squashed

### Why This Matters

This intelligent handling allows you to:

1. **Work naturally**: Stage changes you want to squash, keep unstaged changes for future work
2. **No data loss**: Never lose unstaged work, even during complex rebase operations
3. **Flexible workflow**: Run git-autosquash at any point without preparation
4. **Clear intentions**: The tool processes the most "ready" changes (staged > unstaged > HEAD)

### Examples of Mixed Change Workflows

**Example 1: Code review feedback + ongoing development**
```bash
# Stage fixes for code review feedback
git add src/auth/login.py src/docs/api.md

# Keep ongoing work unstaged
# (modified: src/new_feature.py, tests/test_new.py)

git-autosquash
# Processes only the staged fixes, unstaged work safely preserved
```

**Example 2: Bug fix + debug code**
```bash
# Stage the actual bug fix
git add src/auth/security.py

# Keep debug prints unstaged for continued development
# (modified: src/auth/debug_helpers.py with temporary logging)

git-autosquash
# Squashes bug fix to appropriate commit, keeps debug code for you
```

## Common Scenarios

### Bug Fix During Feature Work

**Best Practice**: Fix bugs as you encounter them, then use git-autosquash to organize the changes appropriately.

### Code Review Feedback

After receiving code review feedback requesting changes across multiple commits:

```bash
# After addressing review feedback
git status
# modified:   src/auth/login.py      # Requested security fix
# modified:   src/ui/dashboard.py    # Requested UI improvement
# modified:   docs/api.md           # Documentation update

git-autosquash
# Security fix → Goes to original login commit
# UI improvement → Goes to original dashboard commit
# Documentation → Stays as new change (no logical target)
```

### Merge Conflict Resolution

When conflicts occur during rebase:

```bash
git-autosquash
# ... TUI workflow ...
# ✓ Squash operation completed successfully!

# Later, if conflicts occurred:
# ⚠️ Rebase conflicts detected:
#   src/auth/login.py
#
# To resolve conflicts:
# 1. Edit the conflicted files to resolve conflicts
# 2. Stage the resolved files: git add <files>
# 3. Continue the rebase: git rebase --continue
# 4. Or abort the rebase: git rebase --abort
```

**Resolution Process**:
1. Open conflicted files in your editor
2. Resolve conflicts (remove `<<<<<<<`, `=======`, `>>>>>>>` markers)
3. Stage resolved files: `git add src/auth/login.py`
4. Continue: `git rebase --continue`

### Extracting Accidentally Committed Changes

You committed debug code or temporary changes that should be removed from history but kept in your working tree for further development.

```bash
# You have commits with mixed changes
git log --oneline -3
# abc1234 Add user dashboard feature
# def5678 Fix authentication bug
# ghi9012 Add admin panel

# Some commits contain debug prints or temporary code
# that you want to extract back to working directory

git-autosquash
```

**In the TUI**:
1. For each hunk containing debug/temporary code: Select **"Ignore (keep in working tree)"**
2. For legitimate changes: Select **"Skip"** (leave in commits) or **"Squash"** (organize better)
3. Execute the operation

**Result**:
- Debug code gets extracted to your working directory
- Clean commits remain in history
- You can now properly commit or discard the extracted code

This is a selective "uncommit" operation - more precise than `git reset`.

## Branch Management

### Safe Branch Practices

**Good practices**:
- Use git-autosquash on feature branches only
- Ensure your branch has a clear merge-base with main/master
- Keep feature branches focused and reasonably sized

**Avoid**:
- Running on main/master branch directly
- Using on branches without clear merge-base
- Running on very large branches with complex history

### Working with Shared Branches

If others are working on your branch:

1. **Coordinate first**: Let team members know you're rebasing
2. **Force push required**: After git-autosquash, you'll need `git push --force-with-lease`
3. **Team updates**: Others will need to `git pull --rebase` or reset their local branches

### Branch Cleanup After Success

```bash
# After successful git-autosquash
git log --oneline -10  # Verify the results look good

# If satisfied, you might want to:
git push --force-with-lease origin feature/oauth-integration

# Or continue with more development
git commit -m "Add OAuth provider configuration"
```

## Performance Tips

### Large Repositories

For large repositories with extensive history:

- git-autosquash caches blame and commit information
- First run may be slower as caches are built
- Subsequent runs on the same branch are faster
- Consider using `--line-by-line` for precise control

### Optimizing for Speed

```bash
# For large changesets, line-by-line can be more precise
git-autosquash --line-by-line

# Standard mode is faster for most cases
git-autosquash
```

## Integration with Git Workflows

### Pre-Push Hook

Integrate git-autosquash into your workflow with git hooks:

```bash
#!/bin/bash
# .git/hooks/pre-push

echo "Checking if working directory needs git-autosquash..."
if ! git diff --quiet; then
    echo "Uncommitted changes found. Consider running git-autosquash first."
    read -p "Continue with push? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
```

### IDE Integration

Configure IDEs to run git-autosquash:

- **VS Code**: Add as a task or terminal command
- **IntelliJ/PyCharm**: Configure as external tool
- **Vim/Neovim**: Create command mapping

## Troubleshooting Common Issues

### "No target commits found"

Occurs when:
- All changes are in new files
- Changes are outside the branch scope (before merge-base)
- Git blame doesn't find clear ownership

**Solution**: Review if the changes actually belong in historical commits, or if they should stay as new changes.

### "Command not found"

Check installation:
```bash
which git-autosquash
git-autosquash --version
```

Reinstall if needed:
```bash
pipx reinstall git-autosquash
```

### "Not in a git repository"

Ensure you're in a Git repository:
```bash
pwd
git status
```

### Performance issues

For very large diffs:
- Consider breaking changes into smaller chunks
- Use `--line-by-line` for more granular control
- Ensure adequate memory and disk space

## Next Steps

- [Advanced Usage](advanced-usage.md) - Power features and options
- [Complex Workflows](../examples/complex-workflows.md) - Challenging scenarios
- [Troubleshooting](troubleshooting.md) - Detailed problem-solving guides