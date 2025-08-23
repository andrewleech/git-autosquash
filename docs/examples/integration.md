# Integration Examples

This guide demonstrates how to integrate git-autosquash into existing development workflows, tools, and team processes.

## IDE Integration

### Visual Studio Code

#### Tasks Configuration

Create `.vscode/tasks.json`:

```json
{
    "version": "2.0.0",
    "tasks": [
        {
            "label": "git-autosquash",
            "type": "shell",
            "command": "git-autosquash",
            "group": {
                "kind": "build",
                "isDefault": false
            },
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": true,
                "panel": "new",
                "showReuseMessage": true,
                "clear": true
            },
            "problemMatcher": [],
            "runOptions": {
                "runOn": "default"
            }
        },
        {
            "label": "git-autosquash (line-by-line)",
            "type": "shell", 
            "command": "git-autosquash",
            "args": ["--line-by-line"],
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": true,
                "panel": "new"
            },
            "problemMatcher": []
        },
        {
            "label": "check-autosquash-needed",
            "type": "shell",
            "command": "bash",
            "args": [
                "-c",
                "if ! git diff --quiet; then echo 'Changes detected - consider git-autosquash'; git diff --stat; else echo 'No changes to organize'; fi"
            ],
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "silent",
                "panel": "shared"
            }
        }
    ]
}
```

#### Keybindings

Add to `.vscode/keybindings.json`:

```json
[
    {
        "key": "ctrl+shift+g a",
        "command": "workbench.action.tasks.runTask",
        "args": "git-autosquash"
    },
    {
        "key": "ctrl+shift+g ctrl+a", 
        "command": "workbench.action.tasks.runTask",
        "args": "git-autosquash (line-by-line)"
    },
    {
        "key": "ctrl+shift+g c",
        "command": "workbench.action.tasks.runTask", 
        "args": "check-autosquash-needed"
    }
]
```

#### Settings and Extensions

Add to `.vscode/settings.json`:

```json
{
    "git.autofetch": true,
    "git.confirmSync": false,
    "terminal.integrated.defaultProfile.linux": "bash",
    "terminal.integrated.profiles.linux": {
        "bash": {
            "path": "bash",
            "args": ["-l"],
            "env": {
                "TERM": "xterm-256color"
            }
        }
    }
}
```

### IntelliJ IDEA / PyCharm

#### External Tools Setup

1. **Settings** → **Tools** → **External Tools**
2. **Add New Tool**:

**git-autosquash (Standard)**:
```
Name: git-autosquash
Description: Organize changes into historical commits
Program: git-autosquash
Working directory: $ProjectFileDir$
```

**git-autosquash (Precise)**:
```
Name: git-autosquash (line-by-line)
Description: Organize changes with line-by-line precision  
Program: git-autosquash
Arguments: --line-by-line
Working directory: $ProjectFileDir$
```

#### Toolbar Integration

1. **Settings** → **Appearance & Behavior** → **Menus and Toolbars**
2. **Main Toolbar** → **Add Action** → **External Tools**
3. Add both git-autosquash tools

#### Keyboard Shortcuts

1. **Settings** → **Keymap**
2. **External Tools** → **git-autosquash**
3. **Add Keyboard Shortcut**: `Ctrl+Alt+G`

### Vim/Neovim

#### Basic Integration

Add to `.vimrc` or `init.vim`:

```vim
" git-autosquash integration
nnoremap <leader>ga :!git-autosquash<CR>
nnoremap <leader>gA :!git-autosquash --line-by-line<CR>

" Check if autosquash would be useful
function! CheckAutosquash()
    let l:status = system('git diff --quiet')
    if v:shell_error != 0
        echo "Changes detected - consider git-autosquash"
        echo system('git diff --stat')
    else
        echo "No changes to organize"
    endif
endfunction

command! CheckAutosquash call CheckAutosquash()
nnoremap <leader>gc :CheckAutosquash<CR>

" Pre-commit check
function! PreCommitCheck()
    if !empty(system('git diff --name-only'))
        let l:response = input("Uncommitted changes detected. Run git-autosquash first? (y/n): ")
        if l:response ==? 'y'
            !git-autosquash
        endif
    endif
endfunction

command! PreCommitCheck call PreCommitCheck()
```

#### Advanced Neovim Integration

For Neovim with Lua configuration:

```lua
-- init.lua or plugin configuration
local function git_autosquash(line_by_line)
    local cmd = line_by_line and "git-autosquash --line-by-line" or "git-autosquash"
    vim.cmd("!" .. cmd)
end

local function check_autosquash()
    local handle = io.popen("git diff --quiet")
    local result = handle:close()
    
    if not result then
        print("Changes detected - consider git-autosquash")
        local stats = io.popen("git diff --stat"):read("*all")
        print(stats)
    else
        print("No changes to organize")
    end
end

-- Keymaps
vim.keymap.set('n', '<leader>ga', function() git_autosquash(false) end, { desc = "git-autosquash" })
vim.keymap.set('n', '<leader>gA', function() git_autosquash(true) end, { desc = "git-autosquash line-by-line" })
vim.keymap.set('n', '<leader>gc', check_autosquash, { desc = "Check autosquash needed" })

-- Commands
vim.api.nvim_create_user_command('GitAutosquash', function() git_autosquash(false) end, {})
vim.api.nvim_create_user_command('GitAutosquashPrecise', function() git_autosquash(true) end, {})
vim.api.nvim_create_user_command('CheckAutosquash', check_autosquash, {})
```

## Git Hooks Integration

### Pre-commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Pre-commit: Checking working directory...${NC}"

# Check if there are unstaged changes
if ! git diff --quiet; then
    echo -e "${YELLOW}Unstaged changes detected.${NC}"
    echo -e "Consider running ${GREEN}git-autosquash${NC} to organize changes before committing."
    echo
    echo "Changed files:"
    git diff --name-only | sed 's/^/  /'
    echo
    
    # Option to run git-autosquash automatically
    if [ -t 0 ]; then  # Only prompt if interactive
        read -p "Run git-autosquash now? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            git-autosquash
            exit $?  # Exit with git-autosquash result
        fi
    fi
    
    # Continue with commit if user declined
    echo -e "${YELLOW}Proceeding with commit of staged changes only...${NC}"
fi

# Run standard pre-commit checks (linting, tests, etc.)
echo -e "${GREEN}Pre-commit: All checks passed${NC}"
exit 0
```

### Pre-push Hook

```bash
#!/bin/bash
# .git/hooks/pre-push

# Arguments: $1 = remote name, $2 = remote URL
remote="$1"
url="$2"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m' 
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Pre-push: Checking branch organization...${NC}"

# Get current branch
branch=$(git rev-parse --abbrev-ref HEAD)

# Skip checks for main/master branches
if [[ "$branch" == "main" || "$branch" == "master" ]]; then
    echo -e "${GREEN}Pre-push: Main branch, skipping autosquash checks${NC}"
    exit 0
fi

# Check if there are uncommitted changes
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo -e "${RED}Uncommitted changes detected on branch: $branch${NC}"
    echo "Consider organizing changes with git-autosquash before pushing."
    echo
    
    # Show what's changed
    if ! git diff --quiet; then
        echo "Unstaged changes:"
        git diff --name-only | sed 's/^/  /'
    fi
    
    if ! git diff --cached --quiet; then
        echo "Staged changes:"
        git diff --cached --name-only | sed 's/^/  /'
    fi
    echo
    
    if [ -t 0 ]; then  # Interactive terminal
        read -p "Continue with push anyway? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${RED}Push cancelled. Organize changes and try again.${NC}"
            exit 1
        fi
    else
        echo -e "${RED}Push cancelled due to uncommitted changes.${NC}"
        exit 1
    fi
fi

# Check branch history quality (optional enhancement)
commit_count=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "0")
if [ "$commit_count" -gt 10 ]; then
    echo -e "${YELLOW}Branch has many commits ($commit_count). Consider using git-autosquash for cleaner history.${NC}"
fi

echo -e "${GREEN}Pre-push: Branch organization looks good${NC}"
exit 0
```

### Post-commit Hook

```bash
#!/bin/bash
# .git/hooks/post-commit

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if working directory has changes after commit
if ! git diff --quiet; then
    echo -e "${YELLOW}Working directory still has changes after commit.${NC}"
    echo -e "Consider running ${GREEN}git-autosquash${NC} to organize remaining changes."
    echo
    echo "Remaining changes:"
    git diff --name-only | sed 's/^/  /'
    echo
fi
```

## CI/CD Integration

### GitHub Actions

#### Autosquash Opportunity Detection

```yaml
# .github/workflows/autosquash-check.yml
name: Autosquash Opportunity Check
on: 
  pull_request:
    types: [opened, synchronize]

jobs:
  check-organization:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history for analysis
          
      - name: Install git-autosquash
        run: pipx install git-autosquash
        
      - name: Analyze branch organization
        run: |
          echo "## Branch Analysis" >> $GITHUB_STEP_SUMMARY
          
          # Count commits in PR
          COMMIT_COUNT=$(git rev-list --count origin/main..HEAD)
          echo "Commits in branch: $COMMIT_COUNT" >> $GITHUB_STEP_SUMMARY
          
          # Count changed files
          FILE_COUNT=$(git diff --name-only origin/main..HEAD | wc -l)
          echo "Files changed: $FILE_COUNT" >> $GITHUB_STEP_SUMMARY
          
          # Check for potential organization opportunities
          if [ $COMMIT_COUNT -gt 5 ] && [ $FILE_COUNT -gt 10 ]; then
            echo "::notice::Branch might benefit from git-autosquash organization"
            echo "::notice::Consider running git-autosquash to organize $COMMIT_COUNT commits across $FILE_COUNT files"
            
            echo "## Recommendation" >> $GITHUB_STEP_SUMMARY
            echo "This branch has many commits and file changes. Consider:" >> $GITHUB_STEP_SUMMARY
            echo "1. Run \`git-autosquash\` to organize commits" >> $GITHUB_STEP_SUMMARY
            echo "2. Review the organized history" >> $GITHUB_STEP_SUMMARY
            echo "3. Force-push the cleaned branch" >> $GITHUB_STEP_SUMMARY
          else
            echo "::notice::Branch organization looks good"
            echo "## Status" >> $GITHUB_STEP_SUMMARY
            echo "Branch organization appears well-structured." >> $GITHUB_STEP_SUMMARY
          fi
          
          # Show commit history
          echo "## Commit History" >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
          git log --oneline origin/main..HEAD >> $GITHUB_STEP_SUMMARY
          echo '```' >> $GITHUB_STEP_SUMMARY
```

#### Documentation for PR Authors

```yaml
# .github/workflows/pr-guidance.yml
name: PR Development Guidance
on:
  pull_request:
    types: [opened]

jobs:
  provide-guidance:
    runs-on: ubuntu-latest
    steps:
      - name: Comment on PR with git-autosquash guidance
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## Development Workflow Guidance
              
              Thank you for your contribution! Here are some tips for maintaining clean commit history:
              
              ### Using git-autosquash
              
              If you need to make additional changes to this PR:
              
              1. **Make your changes** as normal in your working directory
              2. **Run git-autosquash** to organize changes:
                 \`\`\`bash
                 git-autosquash
                 \`\`\`
              3. **Review the proposed organization** in the TUI
              4. **Force-push** the cleaned history:
                 \`\`\`bash
                 git push --force-with-lease
                 \`\`\`
              
              ### When to use git-autosquash
              
              - ✅ Bug fixes for existing features
              - ✅ Code review feedback  
              - ✅ Refactoring improvements
              - ✅ Documentation updates
              
              ### Benefits
              
              - Maintains logical commit organization
              - Each commit tells a complete story
              - Easier code review and maintenance
              - Cleaner project history
              
              Questions? See our [git-autosquash documentation](https://docs.example.com/git-autosquash).`
            })
```

### GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - analyze
  - build
  - test

autosquash-analysis:
  stage: analyze
  image: python:3.12-slim
  before_script:
    - apt-get update && apt-get install -y git
    - pip install pipx
    - pipx install git-autosquash
  script:
    - |
      if [ "$CI_PIPELINE_SOURCE" == "merge_request_event" ]; then
        echo "Analyzing merge request branch organization..."
        
        # Fetch target branch for comparison
        git fetch origin $CI_MERGE_REQUEST_TARGET_BRANCH_NAME
        
        # Count commits and files
        COMMIT_COUNT=$(git rev-list --count origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME..HEAD)
        FILE_COUNT=$(git diff --name-only origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME..HEAD | wc -l)
        
        echo "Commits in MR: $COMMIT_COUNT"
        echo "Files changed: $FILE_COUNT"
        
        # Provide recommendations
        if [ $COMMIT_COUNT -gt 5 ] && [ $FILE_COUNT -gt 10 ]; then
          echo "::warning::Consider using git-autosquash to organize this branch"
          echo "Run: git-autosquash && git push --force-with-lease"
        else
          echo "::info::Branch organization looks good"
        fi
      fi
  only:
    - merge_requests
```

## Build Tool Integration

### Makefile

```makefile
.PHONY: autosquash autosquash-check autosquash-precise clean-history pre-commit

# Standard git-autosquash
autosquash:
	@echo "Running git-autosquash..."
	@if ! git diff --quiet; then \
		git-autosquash; \
	else \
		echo "No changes to organize"; \
	fi

# Line-by-line precision mode  
autosquash-precise:
	@echo "Running git-autosquash with line-by-line precision..."
	@if ! git diff --quiet; then \
		git-autosquash --line-by-line; \
	else \
		echo "No changes to organize"; \
	fi

# Check if autosquash would be useful
autosquash-check:
	@if ! git diff --quiet; then \
		echo "Changes detected:"; \
		git diff --stat; \
		echo ""; \
		echo "Consider running 'make autosquash' to organize changes"; \
	else \
		echo "No changes to analyze"; \
	fi

# Clean up branch history before merge
clean-history: autosquash
	@echo "Branch history cleaned"
	@git log --oneline -10

# Pre-commit workflow
pre-commit: autosquash-check
	@echo "Pre-commit checks completed"

# Development workflow shortcuts
dev-commit: autosquash
	@echo "Ready for commit after organization"

dev-push: autosquash  
	@echo "Organized changes, ready to push"
	@git push --force-with-lease

# Integration with existing workflows
test: autosquash-check
	pytest tests/

lint: autosquash-check
	ruff check src/
	ruff format src/

build: autosquash-check lint test
	python -m build

# Help target
help:
	@echo "git-autosquash integration targets:"
	@echo "  autosquash        - Organize changes into logical commits"  
	@echo "  autosquash-precise - Use line-by-line precision"
	@echo "  autosquash-check  - Check if organization would be useful"
	@echo "  clean-history     - Clean up branch before merge"
	@echo "  pre-commit        - Pre-commit workflow with checks"
	@echo "  dev-commit        - Organize then prompt for commit"
	@echo "  dev-push          - Organize and force-push"
```

### NPM Scripts

For Node.js projects, add to `package.json`:

```json
{
  "scripts": {
    "autosquash": "git-autosquash",
    "autosquash:precise": "git-autosquash --line-by-line",  
    "autosquash:check": "bash -c 'if ! git diff --quiet; then echo \"Changes detected:\"; git diff --stat; echo \"\"; echo \"Run: npm run autosquash\"; else echo \"No changes to organize\"; fi'",
    "pre-commit": "npm run autosquash:check && npm run lint && npm run test",
    "pre-push": "npm run autosquash:check",
    "clean-history": "npm run autosquash && git log --oneline -10",
    "dev:organize": "npm run autosquash && echo 'Ready for commit'",
    "dev:push": "npm run autosquash && git push --force-with-lease"
  },
  "husky": {
    "hooks": {
      "pre-commit": "npm run pre-commit",
      "pre-push": "npm run pre-push"
    }
  }
}
```

### Gradle

For Java projects, add to `build.gradle`:

```gradle
task autosquash(type: Exec) {
    group = 'git'
    description = 'Organize changes into logical commits'
    commandLine 'git-autosquash'
}

task autosquashPrecise(type: Exec) {
    group = 'git'
    description = 'Organize changes with line-by-line precision'
    commandLine 'git-autosquash', '--line-by-line'
}

task autosquashCheck(type: Exec) {
    group = 'git'
    description = 'Check if git-autosquash would be useful'
    commandLine 'bash', '-c', '''
        if ! git diff --quiet; then
            echo "Changes detected:"
            git diff --stat
            echo ""
            echo "Consider running: ./gradlew autosquash"
        else
            echo "No changes to organize"
        fi
    '''
}

task preCommit {
    group = 'git'
    description = 'Pre-commit workflow with organization check'
    dependsOn autosquashCheck, test, checkstyleMain
}

// Integration with existing tasks
test.finalizedBy autosquashCheck
build.dependsOn preCommit
```

## Team Workflow Integration

### Code Review Process

```markdown
# Team Code Review Checklist

## Before Requesting Review

- [ ] Run `git-autosquash` to organize commits
- [ ] Ensure each commit has a clear, focused purpose  
- [ ] Verify commit messages follow team conventions
- [ ] Force-push organized branch: `git push --force-with-lease`

## During Code Review

### Reviewer Checklist
- [ ] Commit organization makes logical sense
- [ ] Each commit can be understood independently
- [ ] Bug fixes are integrated into original implementations
- [ ] Feature additions are clearly separated

### Feedback Integration
When addressing review feedback:

1. Make requested changes in working directory
2. Run `git-autosquash` to distribute fixes appropriately
3. Review proposed organization in TUI
4. Force-push updated branch
5. Respond to review with summary of changes
```

### Branch Naming Conventions

```bash
# Team conventions that work well with git-autosquash

# Feature branches - new functionality
feature/user-authentication
feature/dashboard-ui
feature/api-endpoints

# Bugfix branches - primarily fixes
bugfix/login-validation
bugfix/memory-leaks
bugfix/security-issues

# Refactor branches - improvements to existing code  
refactor/auth-service
refactor/database-layer
refactor/error-handling

# Mixed branches - both new features and fixes
mixed/user-management
mixed/notification-system
```

### Documentation Standards

Team documentation template for PRs:

```markdown
## Changes Made

### New Features
- List new functionality that will remain as new commits

### Bug Fixes  
- List fixes that git-autosquash distributed to historical commits

### Improvements
- List refactoring/optimization that was integrated into existing commits

## git-autosquash Usage

- [x] Ran git-autosquash to organize commits
- [x] Reviewed proposed organization in TUI  
- [x] Verified each commit maintains focused scope
- [ ] N/A - No changes needed organization

## Testing

- [ ] All tests pass
- [ ] Added tests for new functionality
- [ ] Verified fixes resolve reported issues
```

This integration approach ensures git-autosquash becomes a natural part of development workflow rather than an additional burden.