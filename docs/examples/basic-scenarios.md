# Basic Scenarios

This guide walks through common real-world scenarios where git-autosquash provides immediate value.

## Scenario 1: Bug Fix During Feature Development

**Situation**: You're implementing user authentication and discover a validation bug in existing login code.

### Initial State

```bash
$ git log --oneline -5
abc1234 Add OAuth integration framework
def5678 Implement user dashboard 
789abcd Fix login validation logic
012cdef Add initial user model
345ef01 Initial project setup
```

### Your Changes

```bash
$ git status
On branch feature/oauth-integration
Changes not staged for commit:
  modified:   src/auth/oauth.py        # New OAuth implementation
  modified:   src/auth/login.py        # Fix validation bug discovered
  modified:   src/ui/login_form.py     # Update form for OAuth
```

### Running git-autosquash

```bash
$ git-autosquash
```

**TUI Output**:
```
┌─ Hunk Mappings ─────────────────────────────────────────────────┐
│ ● src/auth/oauth.py:15-30 → No target (new feature)            │
│ ● src/auth/login.py:45-47 → 789abcd Fix login validation logic  │ HIGH
│ ● src/ui/login_form.py:12 → def5678 Implement user dashboard    │ MED 
│ ● src/ui/login_form.py:20-25 → No target (new feature)         │
└─────────────────────────────────────────────────────────────────┘
```

### Result After Approval

- OAuth implementation → Stays as new changes
- Validation bug fix → Squashed into commit `789abcd`  
- Form OAuth changes → Stays as new changes
- Form improvement → Squashed into commit `def5678`

**Final commit history**:
```bash
$ git log --oneline -5  
abc1234 Add OAuth integration framework (updated)
def5678 Implement user dashboard (updated with form fix)
789abcd Fix login validation logic (updated with additional fix)
012cdef Add initial user model
345ef01 Initial project setup
```

## Scenario 2: Code Review Feedback

**Situation**: You receive code review feedback asking for changes across multiple historical commits.

### Review Comments

1. "Fix error handling in user registration" (affects commit `abc1234`)
2. "Update API documentation for login endpoint" (affects commit `def5678`)
3. "Add input validation to dashboard form" (affects commit `789abcd`)
4. "Fix typo in README" (affects commit `012cdef`)

### Your Fixes

```bash
$ git status
Changes not staged for commit:
  modified:   src/auth/registration.py  # Error handling improvement
  modified:   docs/api/login.md         # Documentation update
  modified:   src/ui/dashboard.py       # Input validation
  modified:   README.md                 # Typo fix
```

### git-autosquash Results

```bash
$ git-autosquash
```

Each fix goes back to its original commit:
- Registration fix → `abc1234` 
- API docs → `def5678`
- Dashboard validation → `789abcd`
- README typo → `012cdef`

**Benefit**: Clean, logical history where each commit remains focused and complete.

## Scenario 3: Refactoring Session

**Situation**: After a refactoring session, you have improvements scattered across many files.

### Changes Made

```bash
$ git diff --stat
src/auth/login.py          | 5 ++---     # Performance improvement
src/auth/registration.py   | 3 +--      # Code style cleanup  
src/ui/dashboard.py        | 8 ++++----   # Error handling improvement
src/utils/validation.py    | 12 ++++++------  # Algorithm optimization
src/database/models.py     | 6 +++---    # Type annotation fixes
tests/test_auth.py         | 4 ++--    # Test improvements
```

### git-autosquash Analysis

```bash
$ git-autosquash --line-by-line  # More precision for refactoring
```

**Results**:
- Login performance → Back to original login implementation commit
- Registration cleanup → Back to registration commit
- Dashboard error handling → Back to dashboard commit  
- Validation optimization → Back to validation utility commit
- Model annotations → Back to model definition commit
- Test improvements → Back to corresponding test commits

**Outcome**: Each original commit now includes its improvements, maintaining focused history.

## Scenario 4: Mixed Development Session

**Situation**: During one coding session, you both add new features and fix existing bugs.

### Session Work

1. **New feature**: Add password reset functionality
2. **Bug fix**: Fix email validation in existing signup
3. **New feature**: Add user profile editing
4. **Bug fix**: Fix error handling in existing login
5. **Improvement**: Optimize existing database queries

### Files Changed

```bash
$ git status --porcelain
M  src/auth/password_reset.py    # New feature
M  src/auth/signup.py            # Bug fix in existing code
M  src/ui/profile_editor.py      # New feature  
M  src/auth/login.py             # Bug fix in existing code
M  src/database/queries.py       # Optimization of existing code
```

### git-autosquash Organization

```bash
$ git-autosquash
```

**Intelligent separation**:
- Password reset → Stays as new feature commit
- Email validation fix → Goes to original signup commit
- Profile editor → Stays as new feature commit
- Login error handling → Goes to original login commit
- Database optimization → Goes to original database commit

### Final Result

```bash
# New commits for features
git commit -m "Add password reset functionality" 
git commit -m "Add user profile editing interface"

# Historical commits updated with fixes/improvements
# - Signup commit now includes email validation fix
# - Login commit now includes better error handling  
# - Database commit now includes query optimizations
```

## Scenario 5: Large Feature Branch Cleanup

**Situation**: Before merging a large feature branch, clean up the commit history.

### Branch State

```bash
$ git log --oneline origin/main..HEAD
a1b2c3d Add user preferences UI
4e5f6g7 Fix bug in preferences saving  
8h9i0j1 Add user avatar upload
2k3l4m5 Fix avatar validation
6n7o8p9 Update user profile display
0q1r2s3 Fix profile loading performance
```

**Problem**: Bug fixes are separate commits, making history noisy.

### Cleanup with git-autosquash

```bash
# Make additional tweaks and improvements
vim src/ui/preferences.py    # Minor improvement
vim src/ui/avatar.py         # Style cleanup
vim src/ui/profile.py        # Performance tweak

$ git-autosquash
```

**Result**: Bug fixes and improvements get squashed back into their logical commits:
- Preferences fix → Into `a1b2c3d`
- Avatar validation → Into `8h9i0j1` 
- Profile performance → Into `6n7o8p9`
- Plus your new improvements distributed appropriately

### Clean Final History

```bash
$ git log --oneline origin/main..HEAD
a1b2c3d Add user preferences UI (with fixes and improvements)
8h9i0j1 Add user avatar upload (with validation fixes) 
6n7o8p9 Update user profile display (with performance improvements)
```

## Scenario 6: Hotfix Distribution

**Situation**: You need to apply the same fix to multiple points in history.

### Problem Discovery

Security vulnerability found in authentication code that appears in multiple commits.

### Your Fix

```bash
# Apply comprehensive fix
vim src/auth/security.py
vim src/auth/validation.py  
vim src/utils/crypto.py

$ git status
Changes not staged for commit:
  modified:   src/auth/security.py
  modified:   src/auth/validation.py  
  modified:   src/utils/crypto.py
```

### git-autosquash Distribution

```bash
$ git-autosquash --line-by-line  # Precision for security fixes
```

**Result**: Security improvements distributed to multiple historical commits where each component was introduced:
- Security module fixes → Original security implementation
- Validation fixes → Original validation implementation  
- Crypto fixes → Original crypto implementation

**Benefit**: Security fix is applied comprehensively across all related commits in branch history.

## Scenario 7: Documentation and Code Sync

**Situation**: Update documentation to match recent code changes across multiple commits.

### Changes Needed

```bash
$ git diff --name-only
docs/api/auth.md           # Update for auth changes
docs/api/user.md           # Update for user model changes
docs/deployment.md         # Update for deployment changes
src/auth/models.py         # Minor code improvement  
src/deployment/config.py   # Configuration update
```

### git-autosquash Organization

```bash
$ git-autosquash
```

**Result**:
- API docs → Back to commits that introduced those APIs
- Deployment docs → Back to deployment implementation commit
- Code improvements → Back to original implementation commits

**Outcome**: Each commit now has both its implementation AND corresponding documentation, maintaining completeness.

## Key Patterns

### When git-autosquash Helps Most

1. **Bug fixes during feature work** - Keeps bug fixes with original implementation
2. **Code review responses** - Distributes feedback fixes to logical commits
3. **Refactoring improvements** - Puts optimizations with original implementations  
4. **Documentation updates** - Keeps docs synchronized with code changes
5. **Branch cleanup** - Organizes messy development history before merging

### When to Use Standard Mode vs Line-by-Line

**Standard Mode** (`git-autosquash`):
- Feature development with occasional bug fixes
- General code organization
- Performance (faster analysis)

**Line-by-Line Mode** (`git-autosquash --line-by-line`):
- Refactoring sessions with mixed changes
- Security fixes requiring precision
- Code review responses to specific lines
- Complex scenarios with unrelated changes

### Success Indicators

After git-autosquash, you should see:
- ✅ Bug fixes integrated into original implementations
- ✅ Feature additions remain as new commits  
- ✅ Related changes grouped logically
- ✅ Cleaner, more maintainable git history
- ✅ Each commit tells a complete story

For more complex scenarios, see [Complex Workflows](complex-workflows.md).