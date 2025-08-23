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
usage: git-autosquash [-h] [--line-by-line] [--version]

Automatically squash changes back into historical commits

options:
  -h, --help       show this help message and exit
  --line-by-line   Use line-by-line hunk splitting instead of default git hunks
  --version        show program's version number and exit
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
    read -p "Run git-autosquash? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git-autosquash "$@"
    fi
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
	@echo "Running git-autosquash..."
	@git-autosquash

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