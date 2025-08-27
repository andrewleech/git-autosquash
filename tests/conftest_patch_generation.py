"""
Shared fixtures and utilities for patch generation tests.

This module provides common test infrastructure for testing the context-aware
patch generation fix, including repository builders, test data factories, and
shared configuration.
"""

import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
import pytest

from git_autosquash.git_ops import GitOps


class PatchGenerationTestRepo:
    """Base class for creating test repositories with specific scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)
        self._initialize_git()

    def _initialize_git(self):
        """Initialize a git repository with test configuration."""
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=self.repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
        )

    def _commit_changes(self, message: str) -> str:
        """Stage all changes and create a commit, returning the commit hash."""
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=self.repo_path, check=True)
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()


class MicroPythonTestData:
    """Factory for creating MicroPython-like test file content."""

    @staticmethod
    def create_initial_content() -> str:
        """Create initial pyexec.c content without __file__ support."""
        return """/*
 * This file is part of the MicroPython project, http://micropython.org/
 */

#include <stdio.h>
#include <string.h>

static int parse_compile_execute(const void *source, mp_parse_input_kind_t input_kind) {
    if (MP_STATE_VM(mp_pending_exception) != NULL) {
        return 0;
    }

    // Handle different source types
    if (source == NULL) {
        return -1;
    }
    
    // Other code here...
    return 0;
}
"""

    @staticmethod
    def create_target_content() -> str:
        """Create pyexec.c content with single __file__ support (target state)."""
        return """/*
 * This file is part of the MicroPython project, http://micropython.org/
 */

#include <stdio.h>
#include <string.h>

static int parse_compile_execute(const void *source, mp_parse_input_kind_t input_kind) {
    if (MP_STATE_VM(mp_pending_exception) != NULL) {
        return 0;
    }

    // Handle different source types
    if (source == NULL) {
        return -1;
    }
    
    // Handle frozen modules
    if (MP_OBJ_IS_TYPE(source, &mp_type_bytes)) {
        const frozen_module_t *frozen = frozen_find(source);
        if (frozen != NULL) {
            ctx->constants = frozen->constants;
            module_fun = mp_make_function_from_proto_fun(frozen->proto_fun, ctx, NULL);

            #if MICROPY_PY___FILE__
            // Set __file__ for frozen MPY modules
            if (input_kind == MP_PARSE_FILE_INPUT && frozen_module_name != NULL) {
                qstr source_name = qstr_from_str(frozen_module_name);
                mp_store_global(MP_QSTR___file__, MP_OBJ_NEW_QSTR(source_name));
            }
            #endif
        } else {
            // Handle other source types
            lex = source;
        }
        // source is a lexer, parse and compile the script
        qstr source_name = lex->source_name;
        if (input_kind == MP_PARSE_FILE_INPUT) {
            // More code processing...
        }
    }
    
    // Other code here...
    return 0;
}
"""

    @staticmethod
    def create_source_content() -> str:
        """Create pyexec.c content with dual __file__ support (source state with changes to squash)."""
        return """/*
 * This file is part of the MicroPython project, http://micropython.org/
 */

#include <stdio.h>
#include <string.h>

static int parse_compile_execute(const void *source, mp_parse_input_kind_t input_kind) {
    if (MP_STATE_VM(mp_pending_exception) != NULL) {
        return 0;
    }

    // Handle different source types
    if (source == NULL) {
        return -1;
    }
    
    // Handle frozen modules
    if (MP_OBJ_IS_TYPE(source, &mp_type_bytes)) {
        const frozen_module_t *frozen = frozen_find(source);
        if (frozen != NULL) {
            ctx->constants = frozen->constants;
            module_fun = mp_make_function_from_proto_fun(frozen->proto_fun, ctx, NULL);

            #if MICROPY_MODULE___FILE__
            // Set __file__ for frozen MPY modules
            if (input_kind == MP_PARSE_FILE_INPUT && frozen_module_name != NULL) {
                qstr source_name = qstr_from_str(frozen_module_name);
                mp_store_global(MP_QSTR___file__, MP_OBJ_NEW_QSTR(source_name));
            }
            #endif
        } else {
            // Handle other source types
            lex = source;
        }
        // source is a lexer, parse and compile the script
        qstr source_name = lex->source_name;
        #if MICROPY_MODULE___FILE__
        if (input_kind == MP_PARSE_FILE_INPUT) {
            mp_store_global(MP_QSTR___file__, MP_OBJ_NEW_QSTR(source_name));
        }
        #endif
    }
    
    // Other code here...
    return 0;
}
// Additional change
"""

    @staticmethod
    def create_variations(base_content: str, variations: List[str]) -> List[str]:
        """Create multiple variations of content for testing different scenarios."""
        results = []
        for variation in variations:
            modified_content = base_content.replace("MICROPY_PY___FILE__", variation)
            results.append(modified_content)
        return results


class HunkPatternFactory:
    """Factory for creating common hunk patterns for testing."""

    @staticmethod
    def create_identical_changes_pattern() -> Dict[str, Any]:
        """Create pattern for testing identical changes in different locations."""
        return {
            "old_pattern": "#if MICROPY_PY___FILE__",
            "new_pattern": "#if MICROPY_MODULE___FILE__",
            "description": "Preprocessor directive change from PY to MODULE",
            "expected_locations": 2,  # Should find 2 different locations
        }

    @staticmethod
    def create_simple_text_change() -> Dict[str, Any]:
        """Create pattern for simple text changes."""
        return {
            "old_pattern": "This is a test",
            "new_pattern": "This is a test file",
            "description": "Simple text addition",
            "expected_locations": 1,
        }

    @staticmethod
    def create_variable_rename_pattern() -> Dict[str, Any]:
        """Create pattern for variable renaming."""
        return {
            "old_pattern": "old_variable_name",
            "new_pattern": "new_variable_name",
            "description": "Variable renaming",
            "expected_locations": "multiple",  # Can vary by test scenario
        }


class PerformanceTestConfig:
    """Configuration for performance-related tests."""

    # Maximum allowed time for operations (seconds)
    MAX_PATCH_GENERATION_TIME = 2.0
    MAX_HUNK_PARSING_TIME = 1.0
    MAX_LINE_MATCHING_TIME = 0.5

    # Memory limits
    MAX_MEMORY_INCREASE_MB = 50

    # Test data sizes
    LARGE_FILE_LINES = 10000
    MANY_HUNKS_COUNT = 100
    STRESS_TEST_FILES = 50

    @staticmethod
    def create_large_file_content(line_count: Optional[int] = None) -> str:
        """Create content for large file performance testing."""
        if line_count is None:
            line_count = PerformanceTestConfig.LARGE_FILE_LINES

        lines = []
        for i in range(line_count):
            lines.append(
                f"Line {i:04d}: This is test content for performance testing with some meaningful text\n"
            )

        return "".join(lines)

    @staticmethod
    def create_many_hunks_scenario(hunk_count: Optional[int] = None) -> Dict[str, str]:
        """Create content patterns that will generate many hunks."""
        if hunk_count is None:
            hunk_count = PerformanceTestConfig.MANY_HUNKS_COUNT

        base_content = "// Header comment\n"
        for i in range(hunk_count):
            base_content += f'#define CONSTANT_{i:03d} "value_{i:03d}"\n'

        modified_content = base_content.replace("value_", "new_value_")

        return {
            "original": base_content,
            "modified": modified_content,
            "expected_hunks": str(hunk_count),
        }


@pytest.fixture(scope="function")
def temp_repo_base():
    """Create a basic temporary git repository."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "test_repo"
        repo_path.mkdir()
        yield PatchGenerationTestRepo(repo_path)


@pytest.fixture(scope="function")
def temp_repo():
    """Alias for temp_repo_base for backward compatibility."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "test_repo"
        repo_path.mkdir()
        from tests.test_patch_generation_fix import PatchGenerationTestRepository

        yield PatchGenerationTestRepository(repo_path)


@pytest.fixture(scope="function")
def micropython_test_data():
    """Provide MicroPython test data factory."""
    return MicroPythonTestData()


@pytest.fixture(scope="function")
def hunk_pattern_factory():
    """Provide hunk pattern factory for testing."""
    return HunkPatternFactory()


@pytest.fixture(scope="function")
def performance_config():
    """Provide performance test configuration."""
    return PerformanceTestConfig()


@pytest.fixture(scope="session")
def test_session_info():
    """Provide information about the test session."""
    return {
        "test_type": "patch_generation",
        "focus_area": "context_aware_matching",
        "reference_doc": "PATCH_GENERATION_FIX.md",
    }


class TestAssertions:
    """Common assertion helpers for patch generation tests."""

    @staticmethod
    def assert_patch_structure(patch_content: str, expected_hunks: int):
        """Assert that patch has expected structure."""
        assert patch_content is not None, "Patch should be generated"

        hunk_headers = [
            line for line in patch_content.split("\n") if line.startswith("@@")
        ]
        assert len(hunk_headers) == expected_hunks, (
            f"Expected {expected_hunks} hunk headers, found {len(hunk_headers)}"
        )

    @staticmethod
    def assert_patch_applies_cleanly(
        git_ops: GitOps, patch_content: str, repo_path: Path
    ):
        """Assert that a patch applies without errors."""
        patch_file = repo_path / "test.patch"
        patch_file.write_text(patch_content)

        # Check if patch would apply
        check_result = git_ops.run_git_command(["apply", "--check", str(patch_file)])
        assert check_result.returncode == 0, (
            f"Patch should apply cleanly: {check_result.stderr}"
        )

        # Actually apply the patch
        apply_result = git_ops.run_git_command(["apply", str(patch_file)])
        assert apply_result.returncode == 0, (
            f"Patch application failed: {apply_result.stderr}"
        )

    @staticmethod
    def assert_different_line_ranges(patch_content: str):
        """Assert that hunks target different line ranges."""
        hunk_headers = [
            line for line in patch_content.split("\n") if line.startswith("@@")
        ]

        line_ranges = []
        for header in hunk_headers:
            # Extract line range from @@ -old_start,old_count +new_start,new_count @@
            parts = header.split("@@")[1].strip().split(" ")
            line_ranges.append(parts[0])  # old range

        assert len(set(line_ranges)) == len(line_ranges), (
            f"Hunks should target different line ranges: {line_ranges}"
        )

    @staticmethod
    def assert_performance_within_limits(
        elapsed_time: float, max_time: float, operation_name: str
    ):
        """Assert that operation completed within time limits."""
        assert elapsed_time < max_time, (
            f"{operation_name} took too long: {elapsed_time:.3f}s (max: {max_time}s)"
        )

    @staticmethod
    def assert_hunk_content_patterns(
        hunks: List[Any], expected_patterns: Dict[str, Any]
    ):
        """Assert that hunks contain expected content patterns."""
        old_pattern = expected_patterns.get("old_pattern")
        new_pattern = expected_patterns.get("new_pattern")

        for hunk in hunks:
            if old_pattern:
                has_old = any(
                    old_pattern in line for line in hunk.lines if line.startswith("-")
                )
                assert has_old, f"Hunk should contain old pattern '{old_pattern}'"

            if new_pattern:
                has_new = any(
                    new_pattern in line for line in hunk.lines if line.startswith("+")
                )
                assert has_new, f"Hunk should contain new pattern '{new_pattern}'"


@pytest.fixture(scope="function")
def test_assertions():
    """Provide test assertion helpers."""
    return TestAssertions()
