#!/usr/bin/env python3
"""Create realistic terminal screenshots for git-autosquash documentation.

This script generates high-quality terminal screenshots showing actual usage
of git-autosquash with realistic content and proper terminal rendering.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from tests.pyte_screenshot_capture import TerminalScreenshotCapture
except ImportError:
    print("ERROR: Could not import TerminalScreenshotCapture")
    print(
        "Make sure the tests/pyte_screenshot_capture.py file exists and pyte is installed"
    )
    sys.exit(1)


def create_hero_screenshot():
    """Create the main hero screenshot showing git-autosquash in action."""

    capture = TerminalScreenshotCapture(width=120, height=30)

    # Simulate a typical git-autosquash session
    commands = [
        "$ git status",
        "On branch feature/new-api",
        "Changes not staged for commit:",
        '  (use "git add <file>..." to update what will be committed)',
        '  (use "git restore <file>..." to discard changes in working directory)',
        "\tmodified:   src/api.py",
        "\tmodified:   src/models.py",
        "\tmodified:   tests/test_api.py",
        "",
        'no changes added to commit (use "git add ." or "git add <file>...")',
        "",
        "$ git add .",
        "",
        "$ git autosquash",
        "🔍 Analyzing 3 staged hunks...",
        "📊 Found target commits for 3/3 hunks (100% success rate)",
        "",
        "Git patch → target commit Review",
        "Progress Summary: 3 hunks - 3 automatic targets, 0 manual selection",
        "──────────────────────────────────────────────────────────────────",
        "",
        "✓ Automatic Targets (Blame Analysis)",
        "",
        "📄 src/api.py:15-23 → 📝 Add user authentication endpoints",
        "   Lines: @@ -15,8 +15,12 @@ def authenticate_user(username, password):",
        "   Confidence: HIGH (95%)",
        "",
        "📄 src/models.py:42-45 → 📝 Update User model with email field",
        "   Lines: @@ -42,3 +42,6 @@ class User:",
        "   Confidence: HIGH (92%)",
        "",
        "📄 tests/test_api.py:78-85 → 📝 Add tests for authentication flow",
        "   Lines: @@ -78,0 +78,7 @@ class TestAPI:",
        "   Confidence: MEDIUM (87%)",
        "",
        "[A]pprove All & Continue  [C]ontinue with Selected  [Q]Cancel",
    ]

    for cmd in commands:
        capture.type_command(cmd, delay=0.02)

    return capture.capture_screenshot("screenshots/readme/hero_screenshot.png")


def create_workflow_screenshots():
    """Create step-by-step workflow screenshots."""

    workflows = [
        {
            "filename": "workflow_step_01.png",
            "title": "Step 1: Make Changes",
            "commands": [
                "$ git status",
                "On branch feature/user-profile",
                "Changes not staged for commit:",
                '  (use "git add <file>..." to update what will be committed)',
                "",
                "\tmodified:   src/user.py",
                "\tmodified:   src/profile.py",
                "\tmodified:   tests/test_user.py",
                "",
                'no changes added to commit (use "git add ." or "git add <file>...")',
                "",
                "$ # Multiple files modified, ready to stage and autosquash",
            ],
        },
        {
            "filename": "workflow_step_02.png",
            "title": "Step 2: Stage Changes",
            "commands": [
                "$ git add .",
                "",
                "$ git status",
                "On branch feature/user-profile",
                "Changes to be committed:",
                '  (use "git restore --staged <file>..." to unstage)',
                "",
                "\tmodified:   src/user.py",
                "\tmodified:   src/profile.py",
                "\tmodified:   tests/test_user.py",
                "",
                "$ # Changes staged, ready for intelligent squashing",
            ],
        },
        {
            "filename": "workflow_step_03.png",
            "title": "Step 3: Run git-autosquash",
            "commands": [
                "$ git autosquash",
                "🔍 Analyzing 5 staged hunks...",
                "🎯 Running blame analysis on 5 hunks...",
                "📊 Found target commits for 4/5 hunks (80% success rate)",
                "⚠️  1 hunk requires manual target selection",
                "",
                "Launching enhanced interactive approval interface...",
            ],
        },
        {
            "filename": "workflow_step_04.png",
            "title": "Step 4: Interactive Review",
            "commands": [
                "Git patch → target commit Review",
                "Progress Summary: 5 hunks - 4 automatic targets, 1 manual selection",
                "──────────────────────────────────────────────────────────────────",
                "",
                "✓ Automatic Targets (Blame Analysis)",
                "",
                "📄 src/user.py:25-30 → 📝 Add user validation logic",
                "   Confidence: HIGH (94%)",
                "📄 src/user.py:45-52 → 📝 Update user save method",
                "   Confidence: HIGH (91%)",
                "📄 src/profile.py:15-20 → 📝 Add profile creation endpoint",
                "   Confidence: MEDIUM (87%)",
                "📄 tests/test_user.py:78-90 → 📝 Add comprehensive user tests",
                "   Confidence: HIGH (95%)",
                "",
                "⚠ Manual Selection Required (Press 'b' for batch operations)",
                "",
                "📄 src/profile.py:35-40 → ❓ Multiple potential targets found",
                "   [Select target commit or ignore]",
                "",
                "[A]pprove All & Continue  [C]ontinue with Selected  [Q]Cancel",
            ],
        },
        {
            "filename": "workflow_step_05.png",
            "title": "Step 5: Execution",
            "commands": [
                "User selected 5 hunks for squashing",
                "",
                "Executing interactive rebase for approved hunks...",
                "📦 Distributing 5 hunks to their target commits:",
                "  • 2 hunks → Add user validation logic (a4f2b8d)",
                "  • 1 hunk  → Update user save method (f7e9c3a)",
                "  • 1 hunk  → Add profile creation endpoint (b2d5e1f)",
                "  • 1 hunk  → Add comprehensive user tests (c8a6f4b)",
                "",
                "🔄 Starting interactive rebase from 3f8d92a...",
                "✅ Successfully applied 5 hunks to 4 target commits",
                "🎉 Rebase completed successfully!",
                "",
                "Summary:",
                "  Processed: 5 hunks",
                "  Squashed: 5 hunks into 4 commits",
                "  Ignored: 0 hunks",
                "",
                "$ # All changes intelligently squashed into appropriate commits!",
            ],
        },
        {
            "filename": "workflow_step_06.png",
            "title": "Step 6: Clean History",
            "commands": [
                "$ git log --oneline -8",
                "c8a6f4b Add comprehensive user tests",
                "b2d5e1f Add profile creation endpoint",
                "f7e9c3a Update user save method",
                "a4f2b8d Add user validation logic",
                "3f8d92a Initial user profile feature",
                "2e7d41c Update README with API documentation",
                "1c5f82e Add database migration for users table",
                "9b4e63d Fix authentication middleware bug",
                "",
                "$ git status",
                "On branch feature/user-profile",
                "nothing to commit, working tree clean",
                "",
                "$ # Perfect! Clean commit history with logical organization",
            ],
        },
    ]

    for workflow in workflows:
        print(f"Creating {workflow['filename']}...")
        capture = TerminalScreenshotCapture(width=120, height=30)

        for cmd in workflow["commands"]:
            capture.type_command(cmd, delay=0.01)

        capture.capture_screenshot(f"screenshots/readme/{workflow['filename']}")


def create_feature_screenshots():
    """Create feature demonstration screenshots."""

    features = [
        {
            "filename": "feature_smart_targeting.png",
            "title": "Smart Targeting with Blame Analysis",
            "commands": [
                "$ git autosquash --verbose",
                "🔍 Analyzing 3 staged hunks...",
                "🎯 Running blame analysis on 3 hunks...",
                "",
                "Hunk 1: src/api.py:45-52",
                "├─ Blame analysis: Last modified by commit a2f1d8c",
                "├─ Author: john@example.com (2 days ago)",
                "├─ Commit: 'Add API rate limiting'",
                "└─ Confidence: HIGH (94%) ✅",
                "",
                "Hunk 2: src/models.py:23-28",
                "├─ Blame analysis: Last modified by commit f3e7b1a",
                "├─ Author: jane@example.com (1 day ago)",
                "├─ Commit: 'Update User model schema'",
                "└─ Confidence: HIGH (91%) ✅",
                "",
                "Hunk 3: tests/test_api.py:156-163",
                "├─ Blame analysis: Last modified by commit d4c2e9f",
                "├─ Author: bob@example.com (3 hours ago)",
                "├─ Commit: 'Add rate limiting tests'",
                "└─ Confidence: MEDIUM (87%) ✅",
                "",
                "📊 Found target commits for 3/3 hunks (100% success rate)",
                "🎯 All hunks have high-confidence targets!",
            ],
        },
        {
            "filename": "feature_safety_first.png",
            "title": "Safety-First Approach",
            "commands": [
                "$ git autosquash",
                "🔍 Analyzing 2 staged hunks...",
                "🎯 Running blame analysis on 2 hunks...",
                "📊 Found target commits for 2/2 hunks (100% success rate)",
                "",
                "🛡️  Safety Check: Repository Analysis",
                "├─ Working tree: Clean ✅",
                "├─ Staged changes: 2 hunks ready ✅",
                "├─ Uncommitted changes: None ✅",
                "├─ Merge conflicts: None ✅",
                "├─ Rebase in progress: None ✅",
                "└─ Remote sync: Up to date ✅",
                "",
                "🔒 Backup Strategy:",
                "├─ Reflog enabled: Will track all changes ✅",
                "├─ Original HEAD: Saved as ORIG_HEAD ✅",
                "└─ Rollback available: 'git reset --hard ORIG_HEAD' ✅",
                "",
                "⚡ Execution Strategy: Git Native Handler",
                "├─ Method: In-place rebase with git commands ✅",
                "├─ Isolation: Full working tree backup ✅",
                "└─ Recovery: Automatic rollback on failure ✅",
                "",
                "✅ All safety checks passed. Proceeding...",
            ],
        },
        {
            "filename": "feature_interactive_tui.png",
            "title": "Interactive Terminal Interface",
            "commands": [
                "Git patch → target commit Review",
                "Progress Summary: 4 hunks - 3 automatic targets, 1 manual selection",
                "──────────────────────────────────────────────────────────────────",
                "",
                "✓ Automatic Targets (Blame Analysis)",
                "",
                "[●] 📄 src/auth.py:12-19 → 📝 Implement OAuth2 authentication",
                "     Lines: +def oauth_login(provider, token):",
                "     Confidence: HIGH (96%)",
                "",
                "[ ] 📄 src/auth.py:35-42 → 📝 Add session management",
                "     Lines: +class SessionManager:",
                "     Confidence: HIGH (89%)",
                "",
                "[ ] 📄 tests/test_auth.py:45-58 → 📝 Add OAuth2 test suite",
                "     Lines: +def test_oauth_flow():",
                "     Confidence: MEDIUM (85%)",
                "",
                "⚠ Manual Selection Required (Press 'b' for batch operations)",
                "",
                "[?] 📄 src/config.py:8-12 → ❓ Multiple targets found",
                "     Choose target: [1] Initial config [2] Update settings [3] Ignore",
                "",
                "📋 Selection: 1 approved, 0 ignored, 2 pending, 1 manual",
                "",
                "[A]pprove All  [Space]Toggle  [Enter]Continue  [B]atch  [Q]uit",
            ],
        },
    ]

    for feature in features:
        print(f"Creating {feature['filename']}...")
        capture = TerminalScreenshotCapture(width=120, height=30)

        for cmd in feature["commands"]:
            capture.type_command(cmd, delay=0.01)

        capture.capture_screenshot(f"screenshots/readme/{feature['filename']}")


def create_fallback_screenshots():
    """Create fallback scenario screenshots."""

    fallbacks = [
        {
            "filename": "fallback_new_file_fallback.png",
            "title": "New File Fallback Handling",
            "commands": [
                "$ git autosquash",
                "🔍 Analyzing 2 staged hunks...",
                "🎯 Running blame analysis on 2 hunks...",
                "",
                "Hunk 1: src/new_feature.py:1-25 (NEW FILE)",
                "├─ Blame analysis: No existing history",
                "├─ Fallback strategy: Recent commit analysis",
                "├─ Found 3 recent commits touching similar files:",
                "│   [1] Add user authentication (2 days ago)",
                "│   [2] Implement API endpoints (1 day ago)",
                "│   [3] Add database models (6 hours ago)",
                "└─ Action: Manual selection required ⚠️",
                "",
                "Hunk 2: src/utils.py:45-52",
                "├─ Blame analysis: Last modified by commit f2a8d3c",
                "├─ Commit: 'Add utility functions'",
                "└─ Confidence: HIGH (93%) ✅",
                "",
                "📊 Found target commits for 1/2 hunks (50% success rate)",
                "⚠️  1 hunk requires manual selection (new file)",
                "",
                "Launching enhanced interactive approval interface...",
            ],
        },
        {
            "filename": "fallback_manual_override.png",
            "title": "Manual Target Selection",
            "commands": [
                "⚠ Manual Selection Required (Press 'b' for batch operations)",
                "",
                "[?] 📄 src/new_feature.py:1-25 → ❓ New file - choose target",
                "",
                "Available target commits (most recent first):",
                "─────────────────────────────────────────────────────────────",
                "[1] 🔹 Add user authentication (a4f2b8d)",
                "    Author: john@example.com • 2 days ago",
                "    Files: src/auth.py, src/models.py",
                "",
                "[2] 🔹 Implement API endpoints (f7e9c3a)",
                "    Author: jane@example.com • 1 day ago",
                "    Files: src/api.py, src/routes.py",
                "",
                "[3] 🔹 Add database models (b2d5e1f)",
                "    Author: bob@example.com • 6 hours ago",
                "    Files: src/models.py, src/schema.py",
                "",
                "[4] 🔹 Create new feature branch (c8a6f4b)",
                "    Author: alice@example.com • 3 hours ago",
                "    Files: README.md, docs/features.md",
                "",
                "[I] 🚫 Ignore this hunk (leave in working tree)",
                "",
                "Select target [1-4] or [I]gnore: _",
            ],
        },
        {
            "filename": "fallback_ambiguous_blame_fallback.png",
            "title": "Ambiguous Blame Resolution",
            "commands": [
                "$ git autosquash --verbose",
                "🔍 Analyzing 1 staged hunk...",
                "🎯 Running blame analysis on 1 hunk...",
                "",
                "Hunk 1: src/shared.py:78-85",
                "├─ Blame analysis: Multiple recent modifications detected",
                "├─ Last change: commit d4c2e9f (2 hours ago)",
                "├─ Previous change: commit a7b3f1e (4 hours ago)",
                "├─ Context overlap: 3 commits modified nearby lines",
                "└─ Confidence: LOW (45%) ⚠️",
                "",
                "🔍 Detailed Analysis:",
                "├─ Line 78: Last modified by d4c2e9f 'Fix validation bug'",
                "├─ Line 79-82: Last modified by a7b3f1e 'Update error handling'",
                "├─ Line 83-85: Last modified by f2e8d1c 'Add logging support'",
                "└─ Overlapping changes detected in 6-line context window",
                "",
                "📊 Found target commits for 0/1 hunks (0% success rate)",
                "⚠️  1 hunk requires manual selection (ambiguous blame)",
                "",
                "💡 Tip: Use 'git log -p src/shared.py' to review recent changes",
                "",
                "Launching enhanced interactive approval interface...",
            ],
        },
    ]

    for fallback in fallbacks:
        print(f"Creating {fallback['filename']}...")
        capture = TerminalScreenshotCapture(width=120, height=30)

        for cmd in fallback["commands"]:
            capture.type_command(cmd, delay=0.01)

        capture.capture_screenshot(f"screenshots/readme/{fallback['filename']}")


def create_comparison_screenshots():
    """Create before/after comparison screenshots."""

    comparisons = [
        {
            "filename": "comparison_before_traditional.png",
            "title": "Before: Traditional Git Workflow",
            "commands": [
                "$ git log --oneline -10",
                "a4f2b8d WIP: working on user feature",
                "f7e9c3a fix typo in user validation",
                "b2d5e1f add more user tests",
                "c8a6f4b update user model again",
                "d1e9f2a fix user model bug",
                "e3f4a7b add user validation logic",
                "f5g6h8c working on user profile stuff",
                "g7h8i9d more user changes",
                "h9i0j1e fix user profile display",
                "i1j2k3f initial user work",
                "",
                "$ # 😞 Messy history with unclear commit messages",
                "$ # 😞 Multiple 'fix' and 'WIP' commits",
                "$ # 😞 Hard to understand the development story",
                "$ # 😞 Code review is difficult with scattered changes",
                "",
                "$ git rebase -i HEAD~10",
                "$ # 😓 Manual work required to clean up history",
                "$ # 😓 Risk of merge conflicts during interactive rebase",
                "$ # 😓 Time-consuming and error-prone process",
            ],
        },
        {
            "filename": "comparison_after_autosquash.png",
            "title": "After: With git-autosquash",
            "commands": [
                "$ git log --oneline -6",
                "c8a6f4b Add comprehensive user tests",
                "b2d5e1f Add user profile display functionality",
                "f7e9c3a Update user model with validation",
                "a4f2b8d Add user authentication logic",
                "e3f4a7b Initial user feature implementation",
                "f5g6h8c Update README with API documentation",
                "",
                "$ # 🎉 Clean, logical commit history",
                "$ # 🎉 Each commit represents a complete feature/fix",
                "$ # 🎉 Easy to understand the development progression",
                "$ # 🎉 Code reviews are focused and meaningful",
                "",
                "$ git autosquash --help | head -5",
                "Intelligently squash git changes into appropriate target commits",
                "✨ Automatic target detection using git blame analysis",
                "🛡️ Safety-first approach with rollback support",
                "🎯 Smart hunk-to-commit mapping with confidence scoring",
                "🚀 Interactive TUI for manual fallback scenarios",
                "",
                "$ # ⚡ Automated, intelligent, and safe!",
            ],
        },
    ]

    for comparison in comparisons:
        print(f"Creating {comparison['filename']}...")
        capture = TerminalScreenshotCapture(width=120, height=30)

        for cmd in comparison["commands"]:
            capture.type_command(cmd, delay=0.01)

        capture.capture_screenshot(f"screenshots/readme/{comparison['filename']}")


def main():
    """Generate all realistic screenshots."""

    # Create screenshots directory if it doesn't exist
    os.makedirs("screenshots/readme", exist_ok=True)

    print("🎬 Creating realistic terminal screenshots for git-autosquash...")
    print()

    # Generate all screenshot categories
    print("📸 Creating hero screenshot...")
    create_hero_screenshot()

    print("📸 Creating workflow screenshots...")
    create_workflow_screenshots()

    print("📸 Creating feature screenshots...")
    create_feature_screenshots()

    print("📸 Creating fallback screenshots...")
    create_fallback_screenshots()

    print("📸 Creating comparison screenshots...")
    create_comparison_screenshots()

    print()
    print("✅ All realistic screenshots created successfully!")
    print()
    print("Generated files:")
    screenshot_dir = Path("screenshots/readme")
    for screenshot in sorted(screenshot_dir.glob("*.png")):
        print(f"  • {screenshot}")
    print()
    print("🎉 Screenshots ready for documentation!")


if __name__ == "__main__":
    main()
