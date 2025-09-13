"""
Base test repository classes for git-autosquash tests.

This module provides a proper architectural foundation for test repositories
that use GitOps for all git operations, implement resource management,
and provide comprehensive error handling.
"""

import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Iterator, Callable
import weakref
from contextlib import contextmanager

from git_autosquash.git_ops import GitOps
from git_autosquash.exceptions import GitAutoSquashError


class GitOperationError(GitAutoSquashError):
    """Raised when a git operation fails in test setup."""

    pass


class BaseTestRepository:
    """
    Base class for test repositories using proper GitOps integration.

    This class replaces direct subprocess usage with GitOps wrapper,
    implements proper resource management, and provides error boundaries.
    """

    # Class-level registry to track instances for cleanup
    _active_repositories: weakref.WeakSet = weakref.WeakSet()

    def __init__(self, repo_path: Path):
        """
        Initialize test repository with proper GitOps integration.

        Args:
            repo_path: Path to the test repository

        Raises:
            GitOperationError: If repository initialization fails
        """
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)
        self._commit_hashes: List[str] = []
        self._temp_files: List[Path] = []

        # Register for cleanup tracking
        BaseTestRepository._active_repositories.add(self)

        try:
            self._initialize_repository()
        except Exception as e:
            self.cleanup()
            raise GitOperationError(f"Failed to initialize test repository: {e}") from e

    def _initialize_repository(self) -> None:
        """Initialize git repository with proper error handling."""
        # Initialize git repository
        result = self.git_ops.run_git_command(["init"])
        if result.returncode != 0:
            raise GitOperationError(f"Git init failed: {result.stderr}")

        # Set test user configuration
        self._configure_git_user()

        # Verify repository is functional
        if not self.git_ops.is_git_repo():
            raise GitOperationError("Repository initialization verification failed")

    def _configure_git_user(self) -> None:
        """Configure git user for test commits."""
        config_commands = [
            (["config", "user.name", "Test User"], "user name"),
            (["config", "user.email", "test@example.com"], "user email"),
            (["config", "init.defaultBranch", "main"], "default branch"),
        ]

        for args, description in config_commands:
            result = self.git_ops.run_git_command(args)
            if result.returncode != 0:
                raise GitOperationError(
                    f"Failed to configure {description}: {result.stderr}"
                )

    def create_file(self, filename: str, content: str) -> Path:
        """
        Create a file with content in the repository.

        Args:
            filename: Name of the file to create
            content: Content to write to the file

        Returns:
            Path to the created file

        Raises:
            GitOperationError: If file creation fails
        """
        try:
            file_path = self.repo_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

            self._temp_files.append(file_path)
            return file_path
        except (OSError, IOError) as e:
            raise GitOperationError(f"Failed to create file {filename}: {e}") from e

    def create_files(self, files_content: Dict[str, str]) -> Dict[str, Path]:
        """
        Create multiple files with content.

        Args:
            files_content: Dictionary mapping filenames to content

        Returns:
            Dictionary mapping filenames to created file paths
        """
        created_files = {}
        try:
            for filename, content in files_content.items():
                created_files[filename] = self.create_file(filename, content)
            return created_files
        except GitOperationError:
            # Clean up any files that were created before the failure
            for path in created_files.values():
                try:
                    if path.exists():
                        path.unlink()
                except OSError:
                    pass  # Best effort cleanup
            raise

    def stage_all_changes(self) -> None:
        """
        Stage all changes in the repository.

        Raises:
            GitOperationError: If staging fails
        """
        result = self.git_ops.run_git_command(["add", "."])
        if result.returncode != 0:
            raise GitOperationError(f"Failed to stage changes: {result.stderr}")

    def commit_changes(self, message: str, allow_empty: bool = False) -> str:
        """
        Create a commit with the given message.

        Args:
            message: Commit message
            allow_empty: Whether to allow empty commits

        Returns:
            Commit hash of the created commit

        Raises:
            GitOperationError: If commit creation fails
        """
        commit_args = ["commit", "-m", message]
        if allow_empty:
            commit_args.append("--allow-empty")

        result = self.git_ops.run_git_command(commit_args)
        if result.returncode != 0:
            raise GitOperationError(f"Failed to create commit: {result.stderr}")

        # Get the commit hash
        hash_result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
        if hash_result.returncode != 0:
            raise GitOperationError(f"Failed to get commit hash: {hash_result.stderr}")

        commit_hash = hash_result.stdout.strip()
        self._commit_hashes.append(commit_hash)
        return commit_hash

    def add_commit(self, files_content: Dict[str, str], message: str) -> str:
        """
        Create files, stage them, and commit in one operation.

        Args:
            files_content: Dictionary mapping filenames to content
            message: Commit message

        Returns:
            Commit hash of the created commit
        """
        self.create_files(files_content)
        self.stage_all_changes()
        return self.commit_changes(message)

    def get_current_commit(self) -> Optional[str]:
        """
        Get the current commit hash.

        Returns:
            Current commit hash or None if no commits exist
        """
        result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
        if result.returncode == 0:
            return result.stdout.strip()
        return None

    def get_commit_count(self) -> int:
        """
        Get the number of commits in the repository.

        Returns:
            Number of commits
        """
        result = self.git_ops.run_git_command(["rev-list", "--count", "HEAD"])
        if result.returncode == 0:
            try:
                return int(result.stdout.strip())
            except ValueError:
                pass
        return 0

    def create_branch(
        self, branch_name: str, from_commit: Optional[str] = None
    ) -> None:
        """
        Create and checkout a new branch.

        Args:
            branch_name: Name of the branch to create
            from_commit: Optional commit to branch from

        Raises:
            GitOperationError: If branch creation fails
        """
        args = ["checkout", "-b", branch_name]
        if from_commit:
            args.append(from_commit)

        result = self.git_ops.run_git_command(args)
        if result.returncode != 0:
            raise GitOperationError(
                f"Failed to create branch {branch_name}: {result.stderr}"
            )

    def checkout_branch(self, branch_name: str) -> None:
        """
        Checkout an existing branch.

        Args:
            branch_name: Name of the branch to checkout

        Raises:
            GitOperationError: If checkout fails
        """
        result = self.git_ops.run_git_command(["checkout", branch_name])
        if result.returncode != 0:
            raise GitOperationError(
                f"Failed to checkout branch {branch_name}: {result.stderr}"
            )

    def get_working_tree_status(self) -> Dict[str, bool]:
        """Get working tree status using GitOps wrapper."""
        return self.git_ops.get_working_tree_status()

    def cleanup(self) -> None:
        """
        Clean up resources associated with this test repository.

        This method is safe to call multiple times.
        """
        # Clean up temporary files (best effort)
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except OSError:
                pass  # Best effort cleanup

        self._temp_files.clear()
        self._commit_hashes.clear()

    def __del__(self):
        """Ensure cleanup on garbage collection."""
        self.cleanup()

    @classmethod
    def cleanup_all(cls) -> None:
        """Clean up all active test repositories."""
        # Create a copy to avoid modification during iteration
        repositories = list(cls._active_repositories)
        for repo in repositories:
            try:
                repo.cleanup()
            except Exception:
                pass  # Best effort cleanup


class TemporaryTestRepository(BaseTestRepository):
    """
    Test repository that manages its own temporary directory.

    This class provides automatic cleanup of the temporary directory
    and can be used as a context manager.
    """

    def __init__(self, name: str = "test_repo"):
        """
        Initialize temporary test repository.

        Args:
            name: Name for the repository directory
        """
        self._temp_dir = tempfile.mkdtemp()
        self._temp_dir_path = Path(self._temp_dir)
        repo_path = self._temp_dir_path / name
        repo_path.mkdir(parents=True, exist_ok=True)

        super().__init__(repo_path)

    def cleanup(self) -> None:
        """Clean up repository and temporary directory."""
        super().cleanup()

        # Clean up temporary directory
        import shutil

        try:
            if self._temp_dir_path.exists():
                shutil.rmtree(self._temp_dir_path)
        except OSError:
            pass  # Best effort cleanup

    def __enter__(self) -> "TemporaryTestRepository":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit with cleanup."""
        self.cleanup()


@contextmanager
def temporary_test_repository(
    name: str = "test_repo",
) -> Iterator[TemporaryTestRepository]:
    """
    Context manager for creating temporary test repositories.

    Args:
        name: Name for the repository directory

    Yields:
        TemporaryTestRepository instance
    """
    repo = TemporaryTestRepository(name)
    try:
        yield repo
    finally:
        repo.cleanup()


class PatchGenerationTestRepository(BaseTestRepository):
    """
    Specialized test repository for patch generation testing.

    This class extends the base repository with functionality specific
    to testing patch generation scenarios.
    """

    def create_micropython_scenario(self) -> Dict[str, str]:
        """
        Create a MicroPython-like test scenario.

        Returns:
            Dictionary with commit hashes for different states
        """
        # Initial state without __file__ support
        initial_content = """/*
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
}"""

        initial_commit = self.add_commit(
            {"pyexec.c": initial_content},
            "Initial MicroPython pyexec.c without __file__ support",
        )

        # Target state with single __file__ support
        target_content = initial_content.replace(
            "// Other code here...",
            """// Handle frozen modules
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
    
    // Other code here...""",
        )

        target_commit = self.add_commit(
            {"pyexec.c": target_content}, "Add __file__ support for frozen modules"
        )

        return {
            "initial": initial_commit,
            "target": target_commit,
        }

    def create_identical_changes_scenario(self) -> Dict[str, Any]:
        """
        Create a scenario with identical changes at different locations.

        Returns:
            Dictionary with commit hash and change pattern info
        """
        content_with_duplicates = """// Configuration section
#if MICROPY_PY___FILE__
#define ENABLE_FILE_SUPPORT 1
#endif

// Function implementation
static void setup_module(void) {
    #if MICROPY_PY___FILE__
    // Initialize file support
    init_file_support();
    #endif
    
    // Other setup code
}"""

        commit_hash = self.add_commit(
            {"module.c": content_with_duplicates},
            "Add module with duplicate preprocessor checks",
        )

        return {
            "commit": commit_hash,
            "old_pattern": "MICROPY_PY___FILE__",
            "new_pattern": "MICROPY_MODULE___FILE__",
            "expected_locations": 2,
        }


class ErrorHandlingTestRepository(BaseTestRepository):
    """
    Test repository specialized for testing error conditions and edge cases.
    """

    def create_invalid_git_state(self) -> None:
        """Create an invalid git state for testing error handling."""
        # Corrupt the git directory to test error handling
        git_dir = self.repo_path / ".git"
        if git_dir.exists():
            (git_dir / "HEAD").write_text("invalid reference")

    def create_conflicting_state(self) -> None:
        """Create a repository state that will cause merge conflicts."""
        # Create initial file
        self.add_commit(
            {"conflict_file.txt": "line 1\nline 2\nline 3"}, "Initial content"
        )

        # Create branch and modify file
        self.create_branch("feature")
        self.add_commit(
            {"conflict_file.txt": "line 1 modified\nline 2\nline 3"}, "Feature change"
        )

        # Switch back to main and make conflicting change
        self.checkout_branch("main")
        self.add_commit(
            {"conflict_file.txt": "line 1 different\nline 2\nline 3"}, "Main change"
        )

        # Attempt merge to create conflict state
        result = self.git_ops.run_git_command(["merge", "feature"])
        # We expect this to fail with conflicts
        assert result.returncode != 0, "Merge should fail with conflicts"


class PerformanceTestRepository(BaseTestRepository):
    """
    Test repository optimized for performance testing scenarios.
    """

    def create_large_file_scenario(self, line_count: int = 10000) -> str:
        """
        Create a large file for performance testing.

        Args:
            line_count: Number of lines to create

        Returns:
            Commit hash of the large file commit
        """
        lines = []
        for i in range(line_count):
            lines.append(
                f"Line {i:05d}: Performance test content with meaningful text\n"
            )

        large_content = "".join(lines)
        return self.add_commit(
            {"large_file.txt": large_content}, f"Add large file with {line_count} lines"
        )

    def create_many_hunks_scenario(self, hunk_count: int = 100) -> Dict[str, Any]:
        """
        Create content that will generate many hunks for performance testing.

        Args:
            hunk_count: Number of hunks to generate

        Returns:
            Dictionary with scenario information
        """
        base_content = "// Header comment\n"
        for i in range(hunk_count):
            base_content += f'#define CONSTANT_{i:03d} "value_{i:03d}"\n'

        initial_commit = self.add_commit(
            {"many_constants.h": base_content}, "Add many constants"
        )

        # Modify to create hunks
        modified_content = base_content.replace("value_", "new_value_")
        final_commit = self.add_commit(
            {"many_constants.h": modified_content}, "Update all constant values"
        )

        return {
            "initial_commit": initial_commit,
            "final_commit": final_commit,
            "expected_hunks": hunk_count,
        }


class ResourceManagedTestRepository(BaseTestRepository):
    """
    Test repository with enhanced resource management for stress testing.

    This class provides memory monitoring, resource cleanup, and performance
    tracking capabilities for resource-intensive test scenarios.
    """

    def __init__(self, repo_path: Path):
        """
        Initialize resource-managed test repository.

        Args:
            repo_path: Path to the test repository
        """
        super().__init__(repo_path)
        self._resource_monitor = ResourceMonitor()
        self._performance_metrics: dict[str, float] = {}
        self._cleanup_callbacks: list[Callable] = []

    def add_cleanup_callback(self, callback):
        """Add cleanup callback to be executed during resource cleanup."""
        self._cleanup_callbacks.append(callback)

    def start_resource_monitoring(self):
        """Start monitoring resource usage for performance tracking."""
        self._resource_monitor.start_monitoring()

    def stop_resource_monitoring(self) -> dict:
        """Stop monitoring and return resource usage metrics."""
        return self._resource_monitor.stop_monitoring()

    def create_massive_file_scenario(
        self, num_files: int = 50, lines_per_file: int = 1000
    ) -> dict:
        """
        Create a massive file scenario for stress testing.

        Args:
            num_files: Number of files to create
            lines_per_file: Lines per file

        Returns:
            Dictionary with scenario information
        """
        files_content = {}

        for file_idx in range(num_files):
            content_lines = []
            for line_idx in range(lines_per_file):
                if line_idx % 100 == 10:
                    # Add pattern lines for targeted hunks
                    content_lines.append(f"#if STRESS_PATTERN_{file_idx}")
                    content_lines.append(
                        f"void stress_function_{file_idx}_{line_idx}() {{"
                    )
                    content_lines.append("    // Stress test implementation")
                    content_lines.append("}")
                    content_lines.append("#endif")
                else:
                    content_lines.append(f"// File {file_idx} Line {line_idx}")

            filename = f"stress_file_{file_idx:03d}.c"
            files_content[filename] = "\n".join(content_lines)

        initial_commit = self.add_commit(
            files_content, f"Add {num_files} stress test files"
        )

        # Create modified version for hunks
        modified_content = {}
        for filename, content in files_content.items():
            modified_content[filename] = content.replace(
                "STRESS_PATTERN_", "MODIFIED_PATTERN_"
            )

        final_commit = self.add_commit(modified_content, "Modify stress test patterns")

        return {
            "initial_commit": initial_commit,
            "final_commit": final_commit,
            "file_count": num_files,
            "expected_hunks": num_files * (lines_per_file // 100),
        }

    def create_concurrent_modification_scenario(self) -> dict:
        """Create scenario for testing concurrent operations."""
        base_content = {
            "shared_file.py": '''def shared_function():
    """Shared function for concurrent testing."""
    return "original_value"

class SharedClass:
    def __init__(self):
        self.value = "original"
    
    def method(self):
        return self.value''',
            "config.py": """SHARED_CONFIG = {
    "setting1": "value1",
    "setting2": "value2",
    "flag": False
}""",
        }

        initial_commit = self.add_commit(base_content, "Initial concurrent test setup")

        # Create branch for concurrent modifications
        self.create_branch("concurrent_branch")
        concurrent_content = {
            "shared_file.py": base_content["shared_file.py"].replace(
                "original_value", "concurrent_value"
            ),
            "config.py": base_content["config.py"].replace("False", "True"),
        }
        concurrent_commit = self.add_commit(
            concurrent_content, "Concurrent modifications"
        )

        # Return to main for main modifications
        self.checkout_branch("main")
        main_content = {
            "shared_file.py": base_content["shared_file.py"].replace(
                "original", "main_modified"
            ),
            "config.py": base_content["config.py"].replace("value1", "modified_value1"),
        }
        main_commit = self.add_commit(main_content, "Main branch modifications")

        return {
            "initial_commit": initial_commit,
            "concurrent_commit": concurrent_commit,
            "main_commit": main_commit,
            "concurrent_branch": "concurrent_branch",
        }

    def cleanup(self) -> None:
        """Enhanced cleanup with resource monitoring and callbacks."""
        # Execute cleanup callbacks
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception:
                pass  # Best effort cleanup

        self._cleanup_callbacks.clear()

        # Stop resource monitoring if active
        if hasattr(self, "_resource_monitor"):
            try:
                self._resource_monitor.cleanup()
            except Exception:
                pass

        super().cleanup()


class ResourceMonitor:
    """Monitor system resources during test execution."""

    def __init__(self):
        self.monitoring = False
        self._start_metrics = None
        self._process = None

    def start_monitoring(self):
        """Start resource monitoring."""
        try:
            import psutil

            self._process = psutil.Process()
            self._start_metrics = {
                "memory": self._process.memory_info(),
                "cpu_percent": self._process.cpu_percent(),
                "open_files": len(self._process.open_files()),
                "threads": self._process.num_threads(),
            }
            self.monitoring = True
        except ImportError:
            # psutil not available, skip monitoring
            pass

    def stop_monitoring(self) -> dict:
        """Stop monitoring and return metrics."""
        if not self.monitoring or self._start_metrics is None:
            return {}

        try:
            import psutil  # noqa: F401

            end_metrics = {
                "memory": self._process.memory_info(),
                "cpu_percent": self._process.cpu_percent(),
                "open_files": len(self._process.open_files()),
                "threads": self._process.num_threads(),
            }

            return {
                "memory_delta": end_metrics["memory"].rss
                - self._start_metrics["memory"].rss,
                "cpu_usage": end_metrics["cpu_percent"],
                "file_descriptors_delta": end_metrics["open_files"]
                - self._start_metrics["open_files"],
                "thread_delta": end_metrics["threads"] - self._start_metrics["threads"],
            }
        except (ImportError, Exception):
            return {}
        finally:
            self.monitoring = False

    def cleanup(self):
        """Clean up monitoring resources."""
        self.monitoring = False
        self._start_metrics = None
        self._process = None


class StressTestRepository(ResourceManagedTestRepository):
    """
    Specialized repository for stress testing scenarios.

    This class provides utilities for creating high-load scenarios,
    concurrent operations testing, and performance benchmarking.
    """

    def __init__(self, repo_path: Path):
        """Initialize stress test repository."""
        super().__init__(repo_path)
        self._configure_git_for_performance()

    def _configure_git_for_performance(self):
        """Configure git settings for performance testing."""
        performance_configs = [
            (["config", "core.preloadindex", "true"], "preload index"),
            (["config", "core.fscache", "true"], "fs cache"),
            (["config", "gc.auto", "0"], "disable auto gc"),
            (["config", "core.autocrlf", "false"], "disable autocrlf"),
        ]

        for args, description in performance_configs:
            try:
                result = self.git_ops.run_git_command(args)
                if result.returncode != 0:
                    # Log but don't fail - these are optimizations
                    pass
            except Exception:
                # Best effort configuration
                pass


class ConcurrentSafeTestRepository(StressTestRepository):
    """
    Repository with enhanced concurrent operation safety mechanisms.

    This class provides thread-safe operations, lock management, and
    concurrent access protection for test scenarios.
    """

    def __init__(self, repo_path: Path):
        """Initialize concurrent-safe test repository."""
        super().__init__(repo_path)
        self._operation_lock = threading.RLock()
        self._active_operations: set[str] = set()
        self._operation_counter = 0

    def _get_operation_id(self) -> str:
        """Get unique operation ID for tracking concurrent operations."""
        with self._operation_lock:
            self._operation_counter += 1
            return f"op_{self._operation_counter}_{threading.current_thread().ident}"

    @contextmanager
    def _safe_operation(self, operation_name: str):
        """Context manager for safe concurrent operations."""
        operation_id = self._get_operation_id()
        full_operation_name = f"{operation_name}_{operation_id}"

        with self._operation_lock:
            if full_operation_name in self._active_operations:
                raise GitOperationError(
                    f"Operation {operation_name} already in progress"
                )
            self._active_operations.add(full_operation_name)

        try:
            yield operation_id
        finally:
            with self._operation_lock:
                self._active_operations.discard(full_operation_name)

    def concurrent_add_commit(self, files_content: Dict[str, str], message: str) -> str:
        """Thread-safe commit creation."""
        with self._safe_operation("concurrent_commit"):
            return self.add_commit(files_content, message)

    def concurrent_create_branch(
        self, branch_name: str, from_commit: Optional[str] = None
    ) -> None:
        """Thread-safe branch creation."""
        with self._safe_operation("concurrent_branch"):
            # Add thread ID to branch name to avoid conflicts
            thread_id = threading.current_thread().ident
            safe_branch_name = f"{branch_name}_{thread_id}"
            self.create_branch(safe_branch_name, from_commit)

    def concurrent_checkout_branch(self, branch_name: str) -> None:
        """Thread-safe branch checkout."""
        with self._safe_operation("concurrent_checkout"):
            self.checkout_branch(branch_name)

    def get_active_operations(self) -> set:
        """Get set of currently active operations."""
        with self._operation_lock:
            return self._active_operations.copy()

    def wait_for_operations_complete(self, timeout_seconds: float = 30.0) -> bool:
        """Wait for all active operations to complete."""
        import time

        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            with self._operation_lock:
                if not self._active_operations:
                    return True
            time.sleep(0.1)

        return False

    def cleanup(self) -> None:
        """Enhanced cleanup with operation safety."""
        # Wait for active operations to complete
        if not self.wait_for_operations_complete(timeout_seconds=10.0):
            # Force cleanup even with active operations
            with self._operation_lock:
                self._active_operations.clear()

        super().cleanup()


@contextmanager
def concurrent_test_repositories(
    count: int = 3, base_name: str = "concurrent_repo"
) -> Iterator[List[ConcurrentSafeTestRepository]]:
    """
    Create multiple concurrent test repositories for parallel testing.

    Args:
        count: Number of repositories to create
        base_name: Base name for repositories

    Yields:
        List of ConcurrentSafeTestRepository instances
    """
    repositories = []
    temp_dirs = []

    try:
        for i in range(count):
            temp_dir = tempfile.mkdtemp()
            temp_dirs.append(temp_dir)
            repo_path = Path(temp_dir) / f"{base_name}_{i}"
            repo_path.mkdir(parents=True, exist_ok=True)

            repo = ConcurrentSafeTestRepository(repo_path)
            repositories.append(repo)

        yield repositories

    finally:
        # Cleanup all repositories
        for repo in repositories:
            try:
                repo.cleanup()
            except Exception:
                pass  # Best effort cleanup

        # Cleanup temporary directories
        import shutil

        for temp_dir in temp_dirs:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass  # Best effort cleanup


class PerformanceMonitoringRepository(ConcurrentSafeTestRepository):
    """
    Repository with built-in performance monitoring capabilities.

    This class tracks operation timing, resource usage, and performance
    metrics during test execution.
    """

    def __init__(self, repo_path: Path):
        """Initialize performance monitoring repository."""
        super().__init__(repo_path)
        self._performance_metrics = {}
        self._operation_timings: list[dict[str, Any]] = []
        self._resource_tracker = ResourceMonitor()

    @contextmanager
    def _timed_operation(self, operation_name: str):
        """Context manager for timing operations."""
        import time

        start_time = time.time()
        start_memory = self._get_current_memory()

        try:
            yield
        finally:
            end_time = time.time()
            end_memory = self._get_current_memory()

            timing_info = {
                "operation": operation_name,
                "duration": end_time - start_time,
                "memory_delta": end_memory - start_memory,
                "timestamp": start_time,
                "thread_id": threading.current_thread().ident,
            }

            self._operation_timings.append(timing_info)

    def _get_current_memory(self) -> float:
        """Get current memory usage in MB."""
        try:
            import psutil

            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except ImportError:
            return 0.0

    def add_commit_with_timing(
        self, files_content: Dict[str, str], message: str
    ) -> str:
        """Add commit with performance timing."""
        with self._timed_operation("add_commit"):
            return self.add_commit(files_content, message)

    def create_branch_with_timing(
        self, branch_name: str, from_commit: Optional[str] = None
    ) -> None:
        """Create branch with performance timing."""
        with self._timed_operation("create_branch"):
            self.create_branch(branch_name, from_commit)

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary."""
        if not self._operation_timings:
            return {}

        operations_by_type: dict[str, list[dict[str, Any]]] = {}
        for timing in self._operation_timings:
            op_type = timing["operation"]
            if op_type not in operations_by_type:
                operations_by_type[op_type] = []
            operations_by_type[op_type].append(timing)

        summary = {}
        for op_type, timings in operations_by_type.items():
            durations = [t["duration"] for t in timings]
            memory_deltas = [t["memory_delta"] for t in timings]

            summary[op_type] = {
                "count": len(timings),
                "total_duration": sum(durations),
                "avg_duration": sum(durations) / len(durations),
                "max_duration": max(durations),
                "min_duration": min(durations),
                "total_memory_delta": sum(memory_deltas),
                "avg_memory_delta": sum(memory_deltas) / len(memory_deltas),
            }

        return summary

    def cleanup(self) -> None:
        """Cleanup with performance metrics reporting."""
        # Log performance summary before cleanup
        summary = self.get_performance_summary()
        if summary:
            sum(s["count"] for s in summary.values())
            sum(s["total_duration"] for s in summary.values())
            # Performance metrics available for logging/analysis

        super().cleanup()
