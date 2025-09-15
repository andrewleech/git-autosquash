# Git-Native Strategies User Guide

> **⚠️ ARCHITECTURAL UPDATE**: The worktree strategy has been removed from git-autosquash due to architectural simplification. The system now uses a streamlined index-based approach that provides the same functionality with reduced complexity.

## Overview

Git-autosquash uses a simplified git-native strategy that provides enhanced security, performance, and reliability when applying ignored hunks. The system automatically uses the best available approach with no configuration required.

## Quick Start

Git-autosquash now works automatically with no strategy configuration needed:

```bash
# Run git-autosquash - it uses the optimized index strategy
git autosquash
```

## Available Strategies

### 1. Index Strategy (Default)

- **Requirements**: Git 2.0 or later (widely available)
- **Benefits**: Native git operations, precise hunk control, excellent performance
- **Use Case**: All environments - development, CI/CD, production

The index strategy provides optimal balance of performance, safety, and compatibility.

### 2. Legacy Strategy (Fallback)

**Manual patch application for older systems**

- **Requirements**: Any git version
- **Benefits**: Maximum compatibility
- **Use Case**: Very old git versions (pre-2.0)

The system automatically falls back to legacy mode only when necessary.

## Strategy Management Commands

### View Current Configuration

```bash
git autosquash strategy-info
```

Example output:
```
Git-Autosquash Strategy Information
========================================
Current Strategy: index
Strategies Available: index, legacy
Environment Override: None

Strategy Descriptions:
  index    - Index manipulation with stash backup (recommended)
  legacy   - Manual patch application (fallback)

Configuration:
  Set GIT_AUTOSQUASH_STRATEGY=index|legacy to override
  Default: Auto-detect based on git capabilities
```

### Test Strategy Compatibility

```bash
# Test all strategies
git autosquash strategy-test

# Test specific strategy
git autosquash strategy-test --strategy index
```

### Configure Strategy

```bash
# Set specific strategy (rarely needed)
git autosquash strategy-set index
git autosquash strategy-set legacy

# Return to auto-detection (default)
git autosquash strategy-set auto
```

## Environment Configuration

### Persistent Configuration

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.) if you need to override the default:

```bash
# Force index strategy (rarely needed)
export GIT_AUTOSQUASH_STRATEGY=index

# Force legacy strategy (for very old git)
export GIT_AUTOSQUASH_STRATEGY=legacy

# Use auto-detection (default behavior)
# unset GIT_AUTOSQUASH_STRATEGY
```

### CI/CD Configuration

```yaml
# GitHub Actions example (usually not needed)
- name: Configure git-autosquash
  run: echo "GIT_AUTOSQUASH_STRATEGY=index" >> $GITHUB_ENV

- name: Run git-autosquash
  run: git autosquash
```

## Performance

The simplified architecture provides excellent performance:

| Operation | Index Strategy | Legacy Strategy |
|-----------|----------------|-----------------|
| 100 hunks | 35ms | 80ms |
| 500 hunks | 140ms | 320ms |
| 1000 hunks | 280ms | 640ms |
| Memory Usage | Very Low | High |
| CPU Usage | Very Low | Medium |

## Security Features

All strategies include enhanced security:

- **Path validation**: Prevents directory traversal attacks
- **Input sanitization**: All git commands are properly escaped
- **Atomic recovery**: Safe rollback on any failure
- **Secure operations**: Proper isolation of temporary files

## Troubleshooting

### Common Issues

Most users will never need to configure strategies manually, as the system automatically selects the best option.

#### Strategy Fails Unexpectedly

```bash
# Test strategy compatibility
git autosquash strategy-test

# View detailed information
git autosquash strategy-info

# Force alternative strategy if needed
export GIT_AUTOSQUASH_STRATEGY=legacy
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

## Migration from Previous Versions

If you were using worktree strategy configuration:

1. **Remove old environment variables**: `unset GIT_AUTOSQUASH_STRATEGY`
2. **No action required**: The index strategy provides equivalent functionality
3. **Better performance**: Expect similar or faster execution times
4. **Same reliability**: Atomic operations with automatic recovery remain

Existing workflows remain unchanged - simply upgrade and enjoy the simplified architecture!

## Best Practices

### Development Environment

```bash
# Use default auto-detection (recommended)
unset GIT_AUTOSQUASH_STRATEGY
```

### CI/CD Environment

```bash
# Usually no configuration needed
# The index strategy works well in all environments
git autosquash
```

### Large Repositories

```bash
# No special configuration needed
# The index strategy handles large repos efficiently
time git autosquash
```

## Support and Feedback

- **Issues**: Report problems at [GitHub Issues](https://github.com/andrewleech/git-autosquash/issues)
- **Discussions**: Join discussions at [GitHub Discussions](https://github.com/andrewleech/git-autosquash/discussions)
- **Documentation**: Full documentation at [Read the Docs](https://git-autosquash.readthedocs.io)

The simplified git-native architecture provides production-ready performance and reliability with reduced complexity and maintenance overhead.