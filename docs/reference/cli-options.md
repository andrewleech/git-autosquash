# CLI Options

git-autosquash provides a simple command-line interface with focus on ease of use. This reference covers all available options and their usage.

## Basic Usage

```bash
git-autosquash [OPTIONS]
```

## Command-Line Options

### `--line-by-line`

**Usage**: `git-autosquash --line-by-line`

**Description**: Use line-by-line hunk splitting instead of default git hunks.

**Default**: Git's default hunk boundaries (typically more efficient)

**When to use**:
- When you need very fine-grained control over which changes go where
- When default hunks group unrelated changes together  
- When you want maximum precision in blame analysis

**Example**:
```bash
# Standard mode - uses git's hunk boundaries
git-autosquash

# Line-by-line mode - splits changes into individual lines
git-autosquash --line-by-line
```

**Performance impact**: Line-by-line mode is slower but more precise.

### `--auto-accept`

**Usage**: `git-autosquash --auto-accept`

**Description**: Automatically accept all hunks with blame-identified targets, bypassing the interactive TUI.

**Default**: Interactive mode with TUI for user review

**When to use**:
- When you trust the blame analysis and want to automate the process
- In CI/CD pipelines or automated workflows
- When all changes are simple and low-risk
- For batch processing of multiple repositories

**Example**:
```bash
# Interactive mode (default) - shows TUI for review
git-autosquash

# Auto-accept mode - processes automatically without TUI
git-autosquash --auto-accept
```

**Safety considerations**: Only hunks with high-confidence blame matches are processed. Hunks requiring manual target selection (new files, ambiguous blame) are automatically ignored.

### `--dry-run`

**Usage**: `git-autosquash --auto-accept --dry-run`

**Description**: Show what would be done without making any changes. Must be used with `--auto-accept`.

**When to use**:
- To preview what auto-accept mode would do
- To verify targeting before making actual changes
- For debugging blame analysis results
- To generate reports of potential changes

**Example**:
```bash
# Preview what would be done
git-autosquash --auto-accept --dry-run

# Error: dry-run requires auto-accept
git-autosquash --dry-run  # This fails
```

**Output format**: Shows detailed information about each hunk including target commits, confidence levels, and reasons for ignoring certain hunks.

### `--version`

**Usage**: `git-autosquash --version`

**Description**: Display version information and exit.

**Example**:
```bash
$ git-autosquash --version
git-autosquash 1.0.0
```

### `--help` / `-h`

**Usage**: `git-autosquash --help`

**Description**: Show help message with available options and exit.

**Example**:
```bash
$ git-autosquash --help
usage: git-autosquash [-h] [--line-by-line] [--auto-accept] [--dry-run] [--version]

Automatically squash changes back into historical commits

options:
  -h, --help            show this help message and exit
  --line-by-line        Use line-by-line hunk splitting instead of default git hunks
  --auto-accept         Automatically accept all hunks with blame-identified targets, bypass TUI
  --dry-run             Show what would be done without making changes (requires --auto-accept)
  --version             show program's version number and exit
```

## Option Details

### Hunk Splitting: Default vs Line-by-Line

The `--line-by-line` option changes how git-autosquash analyzes your changes:

#### Default Mode (Recommended)

```bash
git-autosquash
```

**How it works**:
- Uses Git's natural hunk boundaries from `git diff`
- Groups related changes together (e.g., function modifications)
- More efficient for most scenarios
- Better performance with large changes

**Example diff handling**:
```diff
@@ -10,6 +10,8 @@ def authenticate_user(username, password):
     if not username:
-        return None
+        return {"error": "Username required"}
     
     if not password:
-        return None  
+        return {"error": "Password required"}
+        
+    # Validate credentials
     return validate_credentials(username, password)
```

**Result**: This entire change is treated as one hunk, going to whichever commit most frequently modified this function.

#### Line-by-Line Mode

```bash
git-autosquash --line-by-line
```

**How it works**:
- Splits changes into individual line modifications
- Each line change analyzed separately for blame
- Maximum precision in targeting
- Slower but more granular control

**Example diff handling**:
Using the same diff above, line-by-line mode creates separate hunks for:
1. Line 12: `return None` → `return {"error": "Username required"}`
2. Line 15: `return None` → `return {"error": "Password required"}`  
3. Line 17: Addition of `# Validate credentials`

**Result**: Each line change can go to different commits based on individual blame analysis.

### When to Use Each Mode

| Scenario | Recommended Mode | Reason |
|----------|-----------------|--------|
| General development | Default | Faster, handles related changes together |
| Large refactoring | Default | More efficient for bulk changes |
| Precise bug fixes | `--line-by-line` | Individual lines may belong to different commits |
| Code review fixes | `--line-by-line` | Review comments often target specific lines |
| Mixed change types | `--line-by-line` | Better separation of unrelated modifications |

## Execution Modes

git-autosquash supports three execution modes that control user interaction:

### Interactive Mode (Default)

```bash
git-autosquash
```

**How it works**:
- Analyzes all changes and presents them in a rich TUI
- User can review, approve, or modify each target assignment
- Provides full context with diff previews and blame information
- Safest mode with complete user control

**Best for**:
- First-time users learning the tool
- Complex changes requiring careful review
- Cases where blame analysis might be ambiguous
- When you want to understand what the tool is doing

### Auto-Accept Mode

```bash
git-autosquash --auto-accept
```

**How it works**:
- Automatically processes hunks with high-confidence blame targets
- Skips TUI entirely for qualifying hunks
- Ignores hunks that require manual target selection
- Provides summary of actions taken

**Safety features**:
- Only processes hunks with clear, unambiguous blame results
- Automatically ignores new files (no blame history)
- Skips hunks with conflicting or low-confidence targeting
- Full git reflog tracking for rollback capability

**Best for**:
- Experienced users who trust the blame analysis
- Automated workflows and CI/CD pipelines
- Batch processing of multiple repositories
- Simple, low-risk changes

### Dry-Run Mode

```bash
git-autosquash --auto-accept --dry-run
```

**How it works**:
- Performs all analysis without making any changes
- Shows exactly what auto-accept mode would do
- Displays target commits, confidence levels, and reasons for ignoring hunks
- Provides actionable summary with next steps

**Output includes**:
- List of hunks that would be automatically processed
- Target commit hashes and summaries for each hunk
- List of hunks that would be ignored and why
- Summary statistics and recommended next action

**Best for**:
- Previewing auto-accept behavior before committing
- Debugging unexpected blame analysis results
- Generating reports of potential changes
- Validating tool behavior in new repositories

### Mode Comparison

| Feature | Interactive | Auto-Accept | Dry-Run |
|---------|-------------|-------------|---------|
| User review required | Yes | No | No |
| Makes changes | Yes | Yes | No |
| TUI interface | Yes | No | No |
| Processes all hunks | User choice | High-confidence only | Preview only |
| Time required | Most | Least | Minimal |
| Safety level | Highest | High | N/A |
| Automation friendly | No | Yes | Yes |

## Exit Codes

git-autosquash uses standard Unix exit codes:

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | Success | Operation completed successfully |
| 1 | General error | Git operation failed, invalid repository, etc. |
| 130 | Interrupted | User cancelled with Ctrl+C |

**Examples**:
```bash
# Success
$ git-autosquash
# ... TUI workflow ...
✓ Squash operation completed successfully!
$ echo $?
0

# User cancellation  
$ git-autosquash
# ... user presses Escape or Ctrl+C ...
Operation cancelled by user
$ echo $?
130

# Error (not in git repository)
$ cd /tmp && git-autosquash
Error: Not in a git repository
$ echo $?
1
```

## Environment Variables

git-autosquash respects these environment variables:

### `TERM`

**Purpose**: Controls terminal capabilities for TUI rendering

**Example**:
```bash
# Force basic terminal mode
TERM=dumb git-autosquash

# Ensure full color support
TERM=xterm-256color git-autosquash
```

### `NO_COLOR`

**Purpose**: Disable colored output when set to any value

**Example**:
```bash
# Disable colors
NO_COLOR=1 git-autosquash

# Enable colors (default)
unset NO_COLOR
git-autosquash
```

### `GIT_SEQUENCE_EDITOR`

**Purpose**: git-autosquash temporarily overrides this during rebase operations

!!! warning "Don't Set Manually"
    git-autosquash manages this automatically. Setting it manually may interfere with the rebase process.

### `EDITOR` / `VISUAL`

**Purpose**: Used by Git for conflict resolution when rebase conflicts occur

**Example**:
```bash
# Use specific editor for conflict resolution
EDITOR=vim git-autosquash

# Or set globally
export EDITOR=code
git-autosquash
```

## Git Configuration Integration

git-autosquash works with standard Git configuration:

### Relevant Git Settings

```bash
# These Git settings affect git-autosquash behavior:

# Default editor for conflict resolution
git config --global core.editor vim

# Merge tool for resolving conflicts
git config --global merge.tool vimdiff  

# Automatic stashing during rebase (overridden by git-autosquash)
git config --global rebase.autoStash true
```

### Git Aliases

You can create Git aliases for convenience:

```bash
# Set up alias
git config --global alias.autosquash '!git-autosquash'

# Now you can use:
git autosquash
git autosquash --line-by-line
```

## Shell Integration

### Tab Completion

If you have `argcomplete` installed, git-autosquash supports tab completion:

```bash
# Install argcomplete
pipx inject git-autosquash argcomplete

# Enable completion (add to your shell config)
eval "$(register-python-argcomplete git-autosquash)"

# Now you can tab-complete:
git-autosquash --<TAB>
# Shows: --line-by-line --version --help
```

### Shell Functions

Useful shell functions for git-autosquash:

```bash
# Quick function to check if autosquash would be useful
check-autosquash() {
    if git diff --quiet; then
        echo "No changes to analyze"
    else
        echo "Found changes - git-autosquash might be useful"
        git diff --stat
    fi
}

# Function to run autosquash with confirmation
safe-autosquash() {
    echo "Current changes:"
    git status --short
    echo
    echo "Available modes:"
    echo "  1) Interactive (default) - full TUI review"
    echo "  2) Auto-accept - automatic processing"
    echo "  3) Dry-run - preview only"
    read -p "Choose mode (1/2/3) or cancel (c): " -n 1 -r
    echo
    case $REPLY in
        1) git-autosquash "$@" ;;
        2) git-autosquash --auto-accept "$@" ;;
        3) git-autosquash --auto-accept --dry-run "$@" ;;
        c|C) echo "Cancelled" ;;
        *) echo "Invalid choice" ;;
    esac
}
```

## Debugging and Troubleshooting

### Verbose Output

While git-autosquash doesn't have a verbose flag, you can monitor Git operations:

```bash
# Set Git trace for debugging
GIT_TRACE=1 git-autosquash

# Monitor specific Git operations
GIT_TRACE_SETUP=1 git-autosquash
```

### Common Issues

#### "Command not found"

```bash
# Check if installed
which git-autosquash
echo $PATH

# Reinstall if needed
pipx reinstall git-autosquash
```

#### "Permission denied"

```bash
# Check file permissions
ls -la $(which git-autosquash)

# Fix if needed (pipx should handle this automatically)
chmod +x $(which git-autosquash)
```

#### "TUI not working"

```bash
# Check terminal capabilities
echo $TERM
tput colors

# Try with basic terminal
TERM=dumb git-autosquash
```

## Integration Examples

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Check if we have unstaged changes that might benefit from autosquash
if ! git diff --quiet; then
    echo "Consider running 'git-autosquash' before committing"
    echo "to distribute changes to their logical commits."
fi
```

### Makefile Integration

```makefile
.PHONY: autosquash
autosquash:
	@echo "Running git-autosquash interactively..."
	@git-autosquash

.PHONY: autosquash-auto
autosquash-auto:
	@echo "Running git-autosquash in auto-accept mode..."
	@git-autosquash --auto-accept

.PHONY: autosquash-dry-run
autosquash-dry-run:
	@echo "Previewing git-autosquash changes..."
	@git-autosquash --auto-accept --dry-run

.PHONY: autosquash-precise
autosquash-precise:
	@echo "Running git-autosquash with line-by-line precision..."
	@git-autosquash --line-by-line
```

### CI/CD Integration

```yaml
# .github/workflows/check-autosquash.yml
name: Check if autosquash needed
on: [pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check for unorganized changes
        run: |
          if ! git diff --quiet origin/main..HEAD; then
            echo "::notice::Consider using git-autosquash to organize changes"
          fi
```

For more advanced usage patterns, see [Advanced Usage](../user-guide/advanced-usage.md).