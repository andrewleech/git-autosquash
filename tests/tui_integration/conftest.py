"""Base fixtures for TUI integration tests."""

import pytest
from typing import List, Optional
from unittest.mock import MagicMock, patch

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.hunk_target_resolver import HunkTargetMapping, TargetingMethod
from git_autosquash.commit_history_analyzer import CommitHistoryAnalyzer, CommitInfo
from git_autosquash.batch_git_ops import BatchCommitInfo


@pytest.fixture
def mock_git_ops():
    """Create a mock GitOps instance with realistic behavior."""
    git_ops = MagicMock(spec=GitOps)
    git_ops.repo_path = "/test/repo"
    git_ops._run_git_command.return_value = (True, "test output")
    return git_ops


@pytest.fixture
def sample_commits() -> List[CommitInfo]:
    """Create sample commit data for testing."""
    return [
        CommitInfo(
            commit_hash="d59d269184f1f320a1e4d31bddde6440cceae7e1",
            short_hash="d59d2691",
            subject="Fix context handling in pyexec module",
            author="John Doe",
            timestamp=1756174372,
            is_merge=False,
            files_touched=["shared/runtime/pyexec.c"]
        ),
        CommitInfo(
            commit_hash="384653e92f39114982d7afb1429956b954ab1234",
            short_hash="384653e9",
            subject="shared/runtime/pyexec: Fix UBSan error in pyexec_stdin()",
            author="Jane Smith",
            timestamp=1756100000,
            is_merge=False,
            files_touched=["shared/runtime/pyexec.c"]
        ),
        CommitInfo(
            commit_hash="a9024949e3c8f2d4b6e1a7f8c9d0e2f3b4a5c6d7",
            short_hash="a9024949",
            subject="Add new feature to runtime system",
            author="Bob Wilson",
            timestamp=1756050000,
            is_merge=False,
            files_touched=["shared/runtime/system.c"]
        ),
        CommitInfo(
            commit_hash="1234567890abcdef1234567890abcdef12345678",
            short_hash="12345678",
            subject="Merge pull request #123 from feature/branch",
            author="GitHub",
            timestamp=1756000000,
            is_merge=True,
            files_touched=None
        )
    ]


@pytest.fixture
def sample_diff_hunks() -> List[DiffHunk]:
    """Create sample diff hunks for testing."""
    return [
        DiffHunk(
            file_path="shared/runtime/pyexec.c",
            old_start=87,
            old_count=7,
            new_start=87,
            new_count=7,
            lines=[
                "@@ -87,7 +87,7 @@ static int parse_compile_exec",
                " #endif",
                " ",
                " #if MICROPY_ENABLE_COMPILER",
                "-            #if MICROPY_PY___FILE__",
                "+            #if MICROPY_MODULE___FILE__",
                "             qstr source_name = lex->source_name;",
                "             if (input_kind == MP_INPUT_FILE) {",
                "                 source_name = mp_obj_str_get_qstr(mp_obj_str_get_qstr(source_file));"
            ],
            context_before=[
                "    ctx->constants = frozen_constants;",
                "    module_fun = mp_make_function_from_raw_code(rc, ctx, NULL);"
            ],
            context_after=[
                "            // Set __file__ for imported modules",
                "            if (input_kind == MP_INPUT_FILE) {"
            ]
        ),
        DiffHunk(
            file_path="shared/runtime/pyexec.c", 
            old_start=142,
            old_count=3,
            new_start=142,
            new_count=3,
            lines=[
                "@@ -142,3 +142,3 @@ static void handle_input",
                " if (source_name != MP_QSTR_) {",
                "-    #if MICROPY_PY___FILE__",
                "+    #if MICROPY_MODULE___FILE__",
                "     mp_store_global(MP_QSTR___file__, MP_OBJ_NEW_QSTR(source_name));"
            ],
            context_before=[
                "    // Handle module initialization",
                "    mp_obj_t module_obj = mp_obj_new_module(source_name);"
            ],
            context_after=[
                "    #endif",
                "    // Continue with execution"
            ]
        ),
        DiffHunk(
            file_path="new_feature.py",
            old_start=0,
            old_count=0,
            new_start=1,
            new_count=10,
            lines=[
                "@@ -0,0 +1,10 @@",
                "+#!/usr/bin/env python3",
                "+\"\"\"New feature implementation.\"\"\"",
                "+",
                "+def new_function():",
                "+    \"\"\"A new function.\"\"\"",
                "+    return 'Hello, world!'",
                "+",
                "+if __name__ == '__main__':",
                "+    print(new_function())"
            ],
            context_before=[],
            context_after=[]
        )
    ]


@pytest.fixture
def blame_matched_mappings(sample_diff_hunks, sample_commits) -> List[HunkTargetMapping]:
    """Create mappings with successful blame matches."""
    return [
        HunkTargetMapping(
            hunk=sample_diff_hunks[0],
            target_commit="d59d269184f1f320a1e4d31bddde6440cceae7e1",
            confidence="high",
            blame_info=[],
            targeting_method=TargetingMethod.BLAME_MATCH,
            needs_user_selection=False
        ),
        HunkTargetMapping(
            hunk=sample_diff_hunks[1],
            target_commit="d59d269184f1f320a1e4d31bddde6440cceae7e1", 
            confidence="medium",
            blame_info=[],
            targeting_method=TargetingMethod.FALLBACK_CONSISTENCY,
            needs_user_selection=False
        )
    ]


@pytest.fixture
def fallback_mappings(sample_diff_hunks, sample_commits) -> List[HunkTargetMapping]:
    """Create mappings requiring fallback selection."""
    return [
        HunkTargetMapping(
            hunk=sample_diff_hunks[2],  # new_feature.py
            target_commit=None,
            confidence="low",
            blame_info=[],
            targeting_method=TargetingMethod.FALLBACK_NEW_FILE,
            fallback_candidates=["384653e92f39114982d7afb1429956b954ab1234", "a9024949e3c8f2d4b6e1a7f8c9d0e2f3b4a5c6d7"],
            needs_user_selection=True
        )
    ]


@pytest.fixture  
def mixed_mappings(blame_matched_mappings, fallback_mappings) -> List[HunkTargetMapping]:
    """Create a mix of blame matched and fallback mappings."""
    return blame_matched_mappings + fallback_mappings


@pytest.fixture
def mock_commit_history_analyzer(mock_git_ops, sample_commits):
    """Create a mock CommitHistoryAnalyzer with realistic behavior."""
    analyzer = MagicMock(spec=CommitHistoryAnalyzer)
    analyzer.git_ops = mock_git_ops
    analyzer.merge_base = "b0fd0079f48bde7f12578823ef88c91f52757cff"
    
    # Mock batch operations
    mock_batch_ops = MagicMock()
    mock_batch_ops.batch_load_commit_info.return_value = {
        commit.commit_hash: BatchCommitInfo(
            commit_hash=commit.commit_hash,
            short_hash=commit.short_hash,
            subject=commit.subject,
            author=commit.author,
            timestamp=commit.timestamp,
            is_merge=commit.is_merge,
            parent_count=2 if commit.is_merge else 1
        ) for commit in sample_commits
    }
    analyzer.git_ops.batch_ops = mock_batch_ops
    
    # Mock commit suggestions
    def get_suggestions(strategy, file_path=None):
        return sample_commits[:3]  # Return first 3 commits as suggestions
    
    analyzer.get_commit_suggestions.side_effect = get_suggestions
    return analyzer


@pytest.fixture(params=[(80, 24), (120, 40), (100, 30)])
def terminal_sizes(request):
    """Provide various terminal size configurations for testing."""
    return request.param


@pytest.fixture
def large_mappings_dataset(sample_commits) -> List[HunkTargetMapping]:
    """Create a large dataset for performance testing."""
    mappings = []
    
    for i in range(50):
        hunk = DiffHunk(
            file_path=f"test_file_{i % 10}.py",
            old_start=i + 1,
            old_count=3,
            new_start=i + 1,
            new_count=3,
            lines=[
                f"@@ -{i+1},3 +{i+1},3 @@",
                f" def function_{i}():",
                f"-    old_code_{i}",
                f"+    new_code_{i}",
                "     return result"
            ],
            context_before=[f"# Context before {i}"],
            context_after=[f"# Context after {i}"]
        )
        
        # Mix of blame matches and fallbacks
        if i % 3 == 0:  # Fallback scenario
            mapping = HunkTargetMapping(
                hunk=hunk,
                target_commit=None,
                confidence="low",
                blame_info=[],
                targeting_method=TargetingMethod.FALLBACK_EXISTING_FILE,
                fallback_candidates=[sample_commits[0].commit_hash, sample_commits[1].commit_hash],
                needs_user_selection=True
            )
        else:  # Blame match
            mapping = HunkTargetMapping(
                hunk=hunk,
                target_commit=sample_commits[i % len(sample_commits)].commit_hash,
                confidence="high" if i % 2 == 0 else "medium",
                blame_info=[],
                targeting_method=TargetingMethod.BLAME_MATCH,
                needs_user_selection=False
            )
        
        mappings.append(mapping)
    
    return mappings


@pytest.fixture(autouse=True)
def disable_git_commands():
    """Automatically disable real git commands for all tests."""
    with patch('git_autosquash.git_ops.GitOps._run_git_command') as mock_git:
        mock_git.return_value = (True, "mocked git output")
        yield mock_git


@pytest.fixture
def mock_batch_git_ops():
    """Mock BatchGitOperations for performance testing."""
    with patch('git_autosquash.batch_git_ops.BatchGitOperations') as mock_ops:
        mock_instance = mock_ops.return_value
        mock_instance.get_branch_commits.return_value = [
            "d59d269184f1f320a1e4d31bddde6440cceae7e1",
            "384653e92f39114982d7afb1429956b954ab1234"
        ]
        yield mock_instance