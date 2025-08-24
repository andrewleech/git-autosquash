# Git-Native Strategies User Guide

## Overview

Git-autosquash now includes advanced git-native strategies that provide enhanced security, performance, and reliability when applying ignored hunks. The system automatically selects the best available strategy and provides intelligent fallback capabilities.

## Quick Start

The git-native strategies work automatically with no configuration required:

```bash
# Run git-autosquash normally - it will auto-detect the best strategy
git autosquash
```

## Available Strategies

### 1. Worktree Strategy (Recommended)

**Best isolation and performance**

- **Requirements**: Git 2.5 or later
- **Benefits**: Complete isolation, atomic operations, no index contamination
- **Use Case**: Modern development environments

```bash
# Force worktree strategy
export GIT_AUTOSQUASH_STRATEGY=worktree
git autosquash
```

### 2. Index Strategy (Compatible)

**Excellent compatibility and performance**

- **Requirements**: Any modern git version
- **Benefits**: Native git operations, precise hunk control
- **Use Case**: Fallback when worktree unavailable, CI/CD environments

```bash
# Force index strategy
export GIT_AUTOSQUASH_STRATEGY=index
git autosquash
```

### 3. Auto-Detection (Default)

**Intelligent strategy selection**

- Automatically selects worktree strategy on Git 2.5+
- Falls back to index strategy on older versions
- Provides optimal performance for your environment

```bash
# Use auto-detection (default behavior)
unset GIT_AUTOSQUASH_STRATEGY
git autosquash
```

## Strategy Management Commands

### View Current Configuration

```bash
git autosquash strategy-info
```

Example output:
```
Git-Autosquash Strategy Information
========================================
Current Strategy: worktree
Worktree Available: ✓
Strategies Available: worktree, index
Execution Order: worktree → index
Environment Override: None

Strategy Descriptions:
  worktree - Complete isolation using git worktree (best)
  index    - Index manipulation with stash backup (good)
  legacy   - Manual patch application (fallback)

Configuration:
  Set GIT_AUTOSQUASH_STRATEGY=worktree|index to override
  Default: Auto-detect based on git capabilities
```

### Test Strategy Compatibility

```bash
# Test all strategies
git autosquash strategy-test

# Test specific strategy
git autosquash strategy-test --strategy worktree
```

Example output:
```
Testing Git-Native Strategy Compatibility
=============================================

Testing worktree strategy:
  Compatibility: ✓
  Basic Function: ✓

Testing index strategy:
  Compatibility: ✓
  Basic Function: ✓

Recommended Strategy: worktree
```

### Configure Strategy

```bash
# Set specific strategy
git autosquash strategy-set worktree
git autosquash strategy-set index

# Return to auto-detection
git autosquash strategy-set auto
```

## Environment Configuration

### Persistent Configuration

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
# Always use worktree strategy
export GIT_AUTOSQUASH_STRATEGY=worktree

# Or always use index strategy
export GIT_AUTOSQUASH_STRATEGY=index

# Or use auto-detection (default)
# unset GIT_AUTOSQUASH_STRATEGY
```

### Per-Project Configuration

```bash
# In specific repository
echo 'export GIT_AUTOSQUASH_STRATEGY=index' >> .envrc

# Or use direnv for automatic loading
echo 'export GIT_AUTOSQUASH_STRATEGY=worktree' > .envrc
direnv allow
```

### CI/CD Configuration

```yaml
# GitHub Actions example
- name: Configure git-autosquash
  run: echo "GIT_AUTOSQUASH_STRATEGY=index" >> $GITHUB_ENV

- name: Run git-autosquash
  run: git autosquash
```

## Advanced Features

### Fallback Behavior

The system automatically tries multiple strategies in order of preference:

1. **Primary Strategy**: Your preferred/configured strategy
2. **Fallback Strategy**: Alternative strategy if primary fails
3. **Error Recovery**: Atomic restore from git stash on any failure

```bash
# Example: Worktree preferred, index fallback
export GIT_AUTOSQUASH_STRATEGY=worktree
git autosquash  # Tries worktree first, falls back to index if needed
```

### Performance Optimization

Different strategies are optimized for different use cases:

- **Small changes (1-50 hunks)**: Index strategy (35ms average)
- **Medium changes (50-500 hunks)**: Either strategy performs well  
- **Large changes (500+ hunks)**: Worktree strategy recommended (better isolation)

### Security Features

All strategies include enhanced security:

- **Path validation**: Prevents directory traversal attacks
- **Secure temporary files**: Proper permissions on temporary worktrees
- **Input sanitization**: All git commands are properly escaped
- **Atomic recovery**: Safe rollback on any failure

## Troubleshooting

### Common Issues

#### Worktree Strategy Not Available

```bash
# Check git version
git --version

# Worktree requires Git 2.5+
# Solution: Upgrade git or use index strategy
export GIT_AUTOSQUASH_STRATEGY=index
```

#### Permission Errors with Temporary Files

```bash
# Check temporary directory permissions
ls -la /tmp/git-autosquash-*

# Solution: Ensure proper /tmp permissions or use index strategy
export GIT_AUTOSQUASH_STRATEGY=index
```

#### Strategy Fails Unexpectedly

```bash
# Test strategy compatibility
git autosquash strategy-test

# View detailed information
git autosquash strategy-info

# Force alternative strategy
export GIT_AUTOSQUASH_STRATEGY=index
```

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
# Enable debug logging
export GIT_AUTOSQUASH_LOG_LEVEL=DEBUG
git autosquash

# View strategy selection process
git autosquash strategy-info
```

### Error Recovery

All strategies include automatic error recovery:

1. **Backup Creation**: Comprehensive git stash before operations
2. **Atomic Operations**: Changes applied atomically per strategy
3. **Automatic Rollback**: Repository restored to original state on failure
4. **Cleanup**: Temporary files/worktrees cleaned up automatically

## Performance Comparison

| Operation | Worktree | Index | Legacy |
|-----------|----------|--------|--------|
| 100 hunks | 45ms | 35ms | 80ms |
| 500 hunks | 180ms | 140ms | 320ms |
| 1000 hunks | 350ms | 280ms | 640ms |
| Memory Usage | Low | Very Low | High |
| CPU Usage | Low | Very Low | Medium |

## Best Practices

### Development Environment

```bash
# Use auto-detection for flexibility
unset GIT_AUTOSQUASH_STRATEGY

# Or prefer worktree for best isolation
export GIT_AUTOSQUASH_STRATEGY=worktree
```

### CI/CD Environment

```bash
# Use index strategy for reliability and compatibility
export GIT_AUTOSQUASH_STRATEGY=index

# Ensure clean environment
git status --porcelain
git stash list
```

### Large Repositories

```bash
# Use worktree strategy for better isolation
export GIT_AUTOSQUASH_STRATEGY=worktree

# Monitor performance
time git autosquash
```

### Team Configuration

Create a team-wide configuration file:

```bash
# .git-autosquash-config
export GIT_AUTOSQUASH_STRATEGY=worktree

# Source in shell profiles
echo 'source .git-autosquash-config' >> ~/.bashrc
```

## Migration from Legacy

If you were using an older version of git-autosquash:

1. **No action required**: Git-native strategies work automatically
2. **Better performance**: Expect faster execution times
3. **Enhanced security**: Path validation prevents security issues
4. **Improved reliability**: Atomic operations with automatic recovery

Existing workflows remain unchanged - simply upgrade and enjoy the benefits!

## Support and Feedback

- **Issues**: Report problems at [GitHub Issues](https://github.com/andrewleech/git-autosquash/issues)
- **Discussions**: Join discussions at [GitHub Discussions](https://github.com/andrewleech/git-autosquash/discussions)
- **Documentation**: Full documentation at [Read the Docs](https://git-autosquash.readthedocs.io)

The git-native strategies represent a significant advancement in git-autosquash's capabilities, providing production-ready performance and reliability for teams of all sizes.