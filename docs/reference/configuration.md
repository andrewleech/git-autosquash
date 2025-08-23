# Configuration Reference

git-autosquash supports various configuration options through environment variables, Git configuration, and command-line arguments.

## Command-Line Options

### Core Options

#### `--line-by-line`
**Description**: Enable line-by-line hunk splitting mode  
**Usage**: `git-autosquash --line-by-line`  
**Default**: Disabled (uses git's default hunk boundaries)

**When to use**:
- Refactoring sessions with mixed changes
- Security fixes requiring precision
- Code review responses targeting specific lines
- Complex scenarios with unrelated modifications

**Performance impact**: Slower analysis but more precise targeting.

#### `--version`
**Description**: Display version information and exit  
**Usage**: `git-autosquash --version`  
**Output**: `git-autosquash X.Y.Z`

#### `--help` / `-h`
**Description**: Show help message and exit  
**Usage**: `git-autosquash --help`

## Environment Variables

### Terminal Control

#### `TERM`
**Purpose**: Controls terminal capabilities for TUI rendering  
**Default**: System default  
**Common values**:
- `xterm-256color` - Full color terminal
- `xterm` - Basic color support
- `dumb` - No color or advanced features

**Example**:
```bash
# Force full color support
TERM=xterm-256color git-autosquash

# Basic terminal mode for compatibility
TERM=dumb git-autosquash
```

#### `NO_COLOR`
**Purpose**: Disable colored output when set to any value  
**Default**: Unset (colors enabled)  
**Specification**: Follows [NO_COLOR standard](https://no-color.org/)

**Example**:
```bash
# Disable all colors
NO_COLOR=1 git-autosquash

# Enable colors (default behavior)
unset NO_COLOR
git-autosquash
```

### Git Integration

#### `GIT_SEQUENCE_EDITOR`
**Purpose**: git-autosquash temporarily overrides this during rebase operations  
**Default**: Managed automatically by git-autosquash  

!!! warning "Don't Set Manually"
    git-autosquash manages this variable automatically during rebase operations. Setting it manually may interfere with the rebase process.

#### `EDITOR` / `VISUAL`
**Purpose**: Editor used by Git for conflict resolution  
**Default**: Git's configured editor  

**Example**:
```bash
# Use specific editor for conflict resolution
EDITOR=vim git-autosquash

# Or set globally
export EDITOR=code
git-autosquash
```

### Debug and Tracing

#### `GIT_TRACE`
**Purpose**: Enable Git command tracing for debugging  
**Values**: `1` (basic), `2` (detailed)  
**Default**: Disabled

**Example**:
```bash
# Basic git command tracing
GIT_TRACE=1 git-autosquash

# Detailed tracing
GIT_TRACE=2 git-autosquash
```

#### `GIT_TRACE_SETUP`
**Purpose**: Trace Git setup and configuration discovery  
**Values**: `1` (enabled)  
**Default**: Disabled

**Example**:
```bash
# Debug git configuration issues
GIT_TRACE_SETUP=1 git-autosquash
```

## Git Configuration

### Relevant Git Settings

git-autosquash respects standard Git configuration settings:

#### Core Settings

```bash
# Default editor for conflict resolution
git config --global core.editor vim

# Automatic line ending conversion
git config --global core.autocrlf true

# Show original diff in conflict markers
git config --global merge.conflictstyle diff3
```

#### Merge and Rebase Settings

```bash
# Merge tool for resolving conflicts
git config --global merge.tool vimdiff

# Automatic stashing during rebase (overridden by git-autosquash)
git config --global rebase.autoStash true

# Preserve merge commits during rebase
git config --global rebase.preserveMerges true
```

#### User Settings

```bash
# Required for commits (used during rebase)
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# GPG signing (if enabled)
git config --global user.signingkey YOUR_KEY_ID
git config --global commit.gpgsign true
```

### Git Aliases

Create convenient aliases for git-autosquash:

```bash
# Basic alias
git config --global alias.autosquash '!git-autosquash'

# Alias with line-by-line mode
git config --global alias.autosquash-precise '!git-autosquash --line-by-line'

# Check if autosquash would be useful
git config --global alias.check-autosquash '!bash -c "if ! git diff --quiet; then echo \"Changes detected - consider git-autosquash\"; git diff --stat; else echo \"No changes to organize\"; fi"'

# Usage after setting aliases
git autosquash
git autosquash-precise
git check-autosquash
```

## TUI Configuration

### Keyboard Shortcuts

Default keyboard shortcuts in the TUI:

| Action | Key | Description |
|--------|-----|-------------|
| Navigate up | ↑ or k | Move to previous hunk mapping |
| Navigate down | ↓ or j | Move to next hunk mapping |
| Toggle approval | Space | Approve/reject current mapping |
| Toggle all | a | Approve or reject all mappings |
| Execute | Enter | Start rebase with approved changes |
| Cancel | Escape or q | Abort operation |

### Display Configuration

The TUI adapts to terminal capabilities:

**Minimum requirements**:
- Terminal size: 80x24 characters
- Basic cursor movement support

**Enhanced features** (when supported):
- 256-color support for syntax highlighting
- Unicode characters for improved display
- Mouse support for navigation

**Fallback behavior**:
- Automatically falls back to text-based approval if TUI fails
- Graceful degradation on limited terminals
- Clear error messages for unsupported environments

## Performance Configuration

### Caching

git-autosquash includes automatic caching for performance:

**Blame cache**:
- Commit metadata cached per session
- Branch scope filtering cached
- File blame results cached

**Cache location**: Memory only (not persisted)  
**Cache lifetime**: Single git-autosquash session

### Memory Management

**Default limits**:
- Maximum hunks processed: No limit
- Maximum file size analyzed: 10MB per file
- Maximum diff size: 100MB total

**Optimization strategies**:
- Hunks processed incrementally
- Large files analyzed in chunks
- Memory released after processing each file

## Shell Integration

### Tab Completion

Enable tab completion with `argcomplete`:

```bash
# Install argcomplete in git-autosquash environment
pipx inject git-autosquash argcomplete

# Enable completion in bash
echo 'eval "$(register-python-argcomplete git-autosquash)"' >> ~/.bashrc

# Enable completion in zsh  
echo 'eval "$(register-python-argcomplete git-autosquash)"' >> ~/.zshrc

# Reload shell configuration
source ~/.bashrc  # or ~/.zshrc
```

**Completion features**:
- Option completion: `git-autosquash --<TAB>`
- Shows available options: `--line-by-line`, `--version`, `--help`

### Shell Functions

Useful shell functions for integration:

```bash
# Add to ~/.bashrc or ~/.zshrc

# Check if autosquash would be useful
check-autosquash() {
    if git diff --quiet; then
        echo "No changes to analyze"
        return 0
    fi
    
    echo "Changes detected:"
    git diff --stat
    echo
    echo "Consider running 'git-autosquash' to organize changes"
}

# Safe autosquash with confirmation
safe-autosquash() {
    if git diff --quiet; then
        echo "No changes to organize"
        return 0
    fi
    
    echo "Current changes:"
    git status --short
    echo
    read -p "Run git-autosquash? (y/n): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git-autosquash "$@"
    else
        echo "Cancelled"
    fi
}

# Pre-commit helper
pre-commit-autosquash() {
    if ! git diff --quiet; then
        echo "Uncommitted changes detected"
        echo "Run git-autosquash to organize before committing"
        return 1
    fi
    echo "Ready for commit"
}
```

## Project-Specific Configuration

### `.gitconfig` Per Repository

Configure git-autosquash behavior per repository:

```bash
# In repository root
cd /path/to/your/project

# Set repository-specific editor
git config core.editor "code --wait"

# Set repository-specific merge tool
git config merge.tool vscode

# Disable GPG signing for this repository
git config commit.gpgsign false
```

### IDE Integration Settings

#### VS Code Settings (`.vscode/settings.json`)

```json
{
    "terminal.integrated.env.linux": {
        "TERM": "xterm-256color"
    },
    "terminal.integrated.env.osx": {
        "TERM": "xterm-256color"  
    },
    "terminal.integrated.env.windows": {
        "TERM": "xterm-256color"
    },
    "git.autofetch": true,
    "git.confirmSync": false
}
```

#### IntelliJ/PyCharm External Tools

Configure git-autosquash as external tool:

**Program**: `git-autosquash`  
**Arguments**: (none for standard mode, `--line-by-line` for precise mode)  
**Working directory**: `$ProjectFileDir$`  
**Environment variables**: `TERM=xterm-256color`

## Troubleshooting Configuration

### Common Configuration Issues

#### TUI Not Working

**Problem**: TUI displays incorrectly or doesn't start

**Solutions**:
```bash
# Check terminal capabilities
echo $TERM
tput colors

# Try with different terminal setting
TERM=xterm git-autosquash

# Force basic mode
TERM=dumb git-autosquash
```

#### Git Commands Failing

**Problem**: Git operations fail or behave unexpectedly

**Solutions**:
```bash
# Check git configuration
git config --list

# Verify git version
git --version  # Requires 2.25+

# Test basic git operations
git status
git log --oneline -5
```

#### Performance Issues  

**Problem**: git-autosquash runs slowly

**Solutions**:
```bash
# Check repository size
du -sh .git/
git count-objects -v

# Clean up repository
git gc --aggressive

# Monitor resource usage
time git-autosquash
```

#### Permission Issues

**Problem**: Permission denied when running git-autosquash

**Solutions**:
```bash
# Check installation
which git-autosquash
ls -la $(which git-autosquash)

# Fix permissions
chmod +x $(which git-autosquash)

# Reinstall if needed
pipx reinstall git-autosquash
```

### Environment Variable Debugging

Debug environment issues:

```bash
# Check all relevant environment variables
echo "TERM: $TERM"
echo "NO_COLOR: $NO_COLOR"
echo "EDITOR: $EDITOR"
echo "VISUAL: $VISUAL"
echo "GIT_SEQUENCE_EDITOR: $GIT_SEQUENCE_EDITOR"
echo "PATH: $PATH"

# Test git environment
git config --list
git --exec-path
```

For additional troubleshooting, see [Troubleshooting Guide](../user-guide/troubleshooting.md).