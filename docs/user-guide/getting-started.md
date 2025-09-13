# Getting Started

This guide covers your first git-autosquash session, from setup to successfully distributing changes back to historical commits.

## Prerequisites

- [Installed git-autosquash](../installation.md)
- Git repository with commit history
- Working directory changes or staged changes to distribute

## Your First Session

### Step 1: Set Up Test Scenario

Create a realistic scenario where you have changes to distribute:

![Git Status Check](../screenshots/readme/workflow_step_01.png)

### Step 2: Run git-autosquash

Execute the analysis:

```bash
git-autosquash
```

Initial analysis output:

![Analysis and Launch](../screenshots/readme/workflow_step_02.png)

Process:
- Analyzes your branch and finds merge base with main/master
- Parses changes into individual hunks (code sections)
- Runs git blame to find which commit last modified each line
- Launches interactive TUI with proposed mappings

### Step 3: Navigate TUI Interface

The TUI displays three sections:

![TUI Interface Overview](../screenshots/readme/feature_interactive_tui.png)

### Step 4: Review and Approve Changes

For each hunk mapping:

1. **Review target commit**: Verify mapping makes sense
2. **Examine diff**: Right panel shows exact changes
3. **Check confidence level**:
   - **High**: Strong evidence this change belongs in target commit
   - **Medium**: Likely correct, review carefully
   - **Low**: Uncertain mapping, consider carefully
4. **Approve or reject**: Check box to approve squashing

#### Keyboard Navigation

- **↑/↓ or j/k**: Navigate between hunk mappings
- **Space**: Toggle approval checkbox
- **Enter**: Approve all hunks and continue
- **a**: Toggle all hunks at once
- **Escape**: Cancel operation

### Step 5: Execute Squash

After approving changes, press **Enter**:

![Execution Progress](../screenshots/readme/workflow_step_05.png)

### Step 6: Verify Results

Check git history:

```bash
# View updated commits
git log --oneline -10

# Check specific commit changes
git show abc1234
git show def5678
```

Changes are incorporated into appropriate historical commits.

## Understanding the Process

### Analysis Phase
- Parses working directory changes into hunks
- Runs git blame on each changed line range
- Identifies commit that last modified those lines
- Filters commits to current branch only

### Approval Phase
- Shows proposed hunk → commit mappings
- Provides diff review and approve/reject controls
- Displays confidence levels based on blame analysis

### Execution Phase
- Groups approved hunks by target commit
- Executes interactive rebase to edit historical commits
- Applies patches to amend appropriate commits
- Handles conflicts with resolution guidance

### Confidence Levels

- **High**: All lines last modified by target commit
- **Medium**: Most lines match target commit, some uncertainty
- **Low**: Mixed blame results or newer commits involved

Start conservative: Only approve "high confidence" mappings initially.

## Safety and Recovery

### Mistake Prevention
- All changes start unapproved (explicit approval required)
- Cancel anytime with Escape
- Automatic rollback on errors
- Manual undo: `git rebase --abort`

### Conflict Resolution
When conflicts occur:
1. Rebase pauses at conflicted commit
2. Shows conflicted files
3. Provides resolution instructions:
   ```
   ⚠️ Rebase conflicts detected:
     src/auth/login.py

   To resolve:
   1. Edit conflicted files
   2. Stage resolved files: git add <files>
   3. Continue: git rebase --continue
   4. Or abort: git rebase --abort
   ```

### Undoing Changes
- **Before push**: Use `git reflog` to find pre-autosquash commit, then `git reset --hard <commit>`
- **After push**: Force push (careful on shared branches) or create revert commits

### Files to Avoid
Be cautious with:
- Files modified by multiple commits heavily
- Frequently changing configuration files
- Files where blame doesn't represent logical ownership
- Large refactoring spanning multiple commits

## Next Steps

- [Basic Workflow](basic-workflow.md) patterns
- [Advanced Usage](advanced-usage.md) options like `--line-by-line`
- [Example Scenarios](../examples/basic-scenarios.md) for common use cases
- [Troubleshooting](troubleshooting.md) for edge cases

## Keyboard Reference

| Action | Shortcut |
|--------|----------|
| Navigate up/down | ↑/↓ or k/j |
| Toggle approval | Space |
| Approve all and continue | Enter |
| Toggle all hunks | a |
| Cancel operation | Escape |
| Quit application | q or Ctrl+C |