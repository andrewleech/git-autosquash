"""
Edge case tests for patch generation fix.

These tests cover production edge cases including binary files, large files,
permission changes, encoding issues, and other file system complexities.
"""

import subprocess
import tempfile
import stat
from pathlib import Path
from typing import Optional
import pytest

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from git_autosquash.rebase_manager import RebaseManager


class EdgeCaseRepository:
    """Builder for edge case testing scenarios."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_ops = GitOps(repo_path)
        self._init_repo()

    def _init_repo(self):
        """Initialize repository with edge case configurations."""
        subprocess.run(
            ["git", "init"], cwd=self.repo_path, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Edge Test User"],
            cwd=self.repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "edge@example.com"],
            cwd=self.repo_path,
            check=True,
        )

        # Configure for binary file handling
        gitattributes_content = """
# Binary file patterns for testing
*.bin binary
*.exe binary
*.so binary
*.dylib binary
*.dll binary

# Text files with special handling
*.txt text
*.c text
*.h text

# Files that should be treated as text despite extension
test-binary-as-text.bin text
"""
        gitattributes_file = self.repo_path / ".gitattributes"
        gitattributes_file.write_text(gitattributes_content.strip())

        subprocess.run(["git", "add", ".gitattributes"], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add gitattributes"], cwd=self.repo_path, check=True
        )

        # Get base commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        self.base_commit = result.stdout.strip()

    def create_binary_file_scenario(self) -> dict:
        """Create scenario with binary files in commits."""
        # Create a simple binary file (fake executable)
        binary_content = (
            b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 100 + b"FAKE_BINARY_DATA" * 10
        )
        binary_file = self.repo_path / "test_program.bin"
        binary_file.write_bytes(binary_content)

        # Create accompanying text file that references the binary
        text_content = """// Configuration for binary program
#if OLD_BINARY_CONFIG
extern void init_binary_program(void);
#endif

void setup() {
    #if OLD_BINARY_CONFIG
    init_binary_program();
    #endif
}
"""
        text_file = self.repo_path / "binary_config.c"
        text_file.write_text(text_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add binary and config"],
            cwd=self.repo_path,
            check=True,
        )

        commit_with_binary = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Create changes to text file (not binary)
        updated_text = text_content.replace("OLD_BINARY_CONFIG", "NEW_BINARY_CONFIG")
        text_file.write_text(updated_text)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update binary config"],
            cwd=self.repo_path,
            check=True,
        )

        text_update_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "base_commit": self.base_commit,
            "commit_with_binary": commit_with_binary,
            "text_update_commit": text_update_commit,
        }

    def create_large_file_scenario(self, file_size_mb: float = 5.0) -> dict:
        """Create scenario with large files."""
        # Create large text file with patterns
        lines_per_mb = 15000  # Approximate
        total_lines = int(file_size_mb * lines_per_mb)

        large_content_lines = []
        pattern_lines = []

        for i in range(total_lines):
            if i % 1000 == 500:  # Every 1000 lines, add a pattern
                large_content_lines.append(f"#if OLD_LARGE_PATTERN  // Line {i}")
                pattern_lines.append(i)
            else:
                large_content_lines.append(f"// Large file content line {i:06d}")

        large_file = self.repo_path / "large_file.c"
        large_file.write_text("\n".join(large_content_lines))

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add large file"], cwd=self.repo_path, check=True
        )

        large_file_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Update some patterns in the large file
        updated_content = large_file.read_text()
        updated_content = updated_content.replace(
            "OLD_LARGE_PATTERN", "NEW_LARGE_PATTERN", 5
        )  # Only first 5
        large_file.write_text(updated_content)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update large file patterns"],
            cwd=self.repo_path,
            check=True,
        )

        pattern_update_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "base_commit": self.base_commit,
            "large_file_commit": large_file_commit,
            "pattern_update_commit": pattern_update_commit,
            "pattern_lines": pattern_lines,
            "file_size_mb": file_size_mb,
        }

    def create_permission_change_scenario(self) -> dict:
        """Create scenario with file permission changes."""
        # Create executable script file
        script_content = """#!/bin/bash
# Test script file

#if OLD_SCRIPT_CONFIG
echo "Old configuration"
#endif

#if OLD_SCRIPT_CONFIG
run_old_behavior
#endif
"""
        script_file = self.repo_path / "test_script.sh"
        script_file.write_text(script_content)

        # Make it executable
        script_file.chmod(script_file.stat().st_mode | stat.S_IEXEC)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add executable script"],
            cwd=self.repo_path,
            check=True,
        )

        script_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Change content and permissions
        updated_script = script_content.replace(
            "OLD_SCRIPT_CONFIG", "NEW_SCRIPT_CONFIG"
        )
        script_file.write_text(updated_script)

        # Remove execute permission
        script_file.chmod(script_file.stat().st_mode & ~stat.S_IEXEC)

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update script content and permissions"],
            cwd=self.repo_path,
            check=True,
        )

        permission_change_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "base_commit": self.base_commit,
            "script_commit": script_commit,
            "permission_change_commit": permission_change_commit,
        }

    def create_encoding_scenario(self) -> dict:
        """Create scenario with different text encodings."""
        # Create UTF-8 file with special characters
        utf8_content = """// UTF-8 encoded file with special characters
#if OLD_UNICODE_PATTERN
void process_unicode() {
    // Special chars: café, naïve, résumé
    printf("Processing unicode: ñoño, piñata\\n");
}
#endif

// Emoji test: 🚀 🎉 ✨
#if OLD_UNICODE_PATTERN  
void emoji_function() {
    // More emoji: 🔧 🐍 🎯
}
#endif
"""

        utf8_file = self.repo_path / "unicode_test.c"
        utf8_file.write_text(utf8_content, encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add UTF-8 file"], cwd=self.repo_path, check=True
        )

        utf8_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Update patterns
        updated_utf8 = utf8_content.replace(
            "OLD_UNICODE_PATTERN", "NEW_UNICODE_PATTERN"
        )
        utf8_file.write_text(updated_utf8, encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update unicode patterns"],
            cwd=self.repo_path,
            check=True,
        )

        unicode_update_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "base_commit": self.base_commit,
            "utf8_commit": utf8_commit,
            "unicode_update_commit": unicode_update_commit,
        }

    def create_symlink_scenario(self) -> Optional[dict]:
        """Create scenario with symbolic links (if supported by OS)."""
        try:
            # Create target file
            target_content = """// Target file for symlink
#if OLD_SYMLINK_PATTERN
void symlink_target() {
    // Implementation
}
#endif
"""
            target_file = self.repo_path / "symlink_target.c"
            target_file.write_text(target_content)

            # Create symbolic link
            symlink_file = self.repo_path / "symlink.c"
            symlink_file.symlink_to("symlink_target.c")

            subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Add symlink scenario"],
                cwd=self.repo_path,
                check=True,
            )

            symlink_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            # Update target file content
            updated_content = target_content.replace(
                "OLD_SYMLINK_PATTERN", "NEW_SYMLINK_PATTERN"
            )
            target_file.write_text(updated_content)

            subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Update symlink target"],
                cwd=self.repo_path,
                check=True,
            )

            symlink_update_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            return {
                "base_commit": self.base_commit,
                "symlink_commit": symlink_commit,
                "symlink_update_commit": symlink_update_commit,
            }

        except (OSError, subprocess.CalledProcessError):
            # Symlinks not supported on this platform
            return None


@pytest.fixture
def edge_case_repo():
    """Create repository for edge case testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir) / "edge_case_repo"
        repo_path.mkdir()
        builder = EdgeCaseRepository(repo_path)
        yield builder


class TestPatchGenerationEdgeCases:
    """Test patch generation edge cases for production scenarios."""

    def test_binary_file_handling(self, edge_case_repo):
        """Test patch generation with binary files in repository."""
        repo = edge_case_repo
        scenario = repo.create_binary_file_scenario()

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get diff from text update commit (should exclude binary changes)
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["text_update_commit"]]
        )

        assert diff_result.returncode == 0, "Should get diff successfully"

        # Verify diff contains text changes but not binary changes
        assert "binary_config.c" in diff_result.stdout, "Should show text file changes"
        assert (
            "Binary files" in diff_result.stdout
            or "test_program.bin" not in diff_result.stdout
        ), "Should handle binary files appropriately"

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)
        text_hunks = [h for h in hunks if h.file_path == "binary_config.c"]
        binary_hunks = [h for h in hunks if h.file_path == "test_program.bin"]

        # Should find text hunks but not binary hunks
        assert len(text_hunks) > 0, "Should find text file hunks"
        assert len(binary_hunks) == 0, "Should not parse binary file hunks"

        # Test patch generation for text changes
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            text_hunks, scenario["commit_with_binary"]
        )

        assert patch_content is not None, "Should generate patch for text changes"
        assert "binary_config.c" in patch_content, "Patch should reference text file"
        assert "test_program.bin" not in patch_content, (
            "Patch should not reference binary file"
        )

    def test_large_file_patch_generation(self, edge_case_repo):
        """Test patch generation with large files."""
        repo = edge_case_repo
        scenario = repo.create_large_file_scenario(
            file_size_mb=2.0
        )  # Use smaller size for testing

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get diff from large file update
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["pattern_update_commit"]]
        )

        assert diff_result.returncode == 0, "Should handle large file diff"

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)
        large_file_hunks = [h for h in hunks if h.file_path == "large_file.c"]

        assert len(large_file_hunks) > 0, "Should find hunks in large file"

        # Test patch generation doesn't crash with large files
        import time

        start_time = time.perf_counter()

        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            large_file_hunks, scenario["large_file_commit"]
        )

        end_time = time.perf_counter()
        processing_time = end_time - start_time

        # Should handle large files in reasonable time
        assert processing_time < 10.0, (
            f"Large file processing took {processing_time:.2f}s (too slow)"
        )
        assert patch_content is not None, "Should generate patch for large file"

        # Verify patch structure
        hunk_count = patch_content.count("@@")
        assert hunk_count > 0, "Should have hunks in large file patch"

    def test_file_permission_changes(self, edge_case_repo):
        """Test patch generation with file permission changes."""
        repo = edge_case_repo
        scenario = repo.create_permission_change_scenario()

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get diff showing both content and permission changes
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["permission_change_commit"]]
        )

        assert diff_result.returncode == 0, "Should get diff with permission changes"

        # Check if permission changes are detected
        if "old mode" in diff_result.stdout and "new mode" in diff_result.stdout:
            print("Permission changes detected in diff")

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)
        script_hunks = [h for h in hunks if h.file_path == "test_script.sh"]

        # Should still find content hunks despite permission changes
        assert len(script_hunks) > 0, (
            "Should find content hunks despite permission changes"
        )

        # Test patch generation with permission changes
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            script_hunks, scenario["script_commit"]
        )

        assert patch_content is not None, (
            "Should generate patch with permission changes"
        )
        assert "test_script.sh" in patch_content, "Patch should reference script file"

        # Verify content changes are captured
        assert (
            "OLD_SCRIPT_CONFIG" in patch_content or "NEW_SCRIPT_CONFIG" in patch_content
        ), "Should capture content changes"

    def test_unicode_and_encoding_handling(self, edge_case_repo):
        """Test patch generation with Unicode and special encoding scenarios."""
        repo = edge_case_repo
        scenario = repo.create_encoding_scenario()

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get diff with Unicode content
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["unicode_update_commit"]]
        )

        assert diff_result.returncode == 0, "Should handle Unicode diff"

        # Verify Unicode characters are preserved
        diff_content = diff_result.stdout
        assert "café" in diff_content or "unicode" in diff_content, (
            "Should preserve Unicode content"
        )

        hunks = hunk_parser._parse_diff_output(diff_content)
        unicode_hunks = [h for h in hunks if h.file_path == "unicode_test.c"]

        assert len(unicode_hunks) > 0, "Should find hunks in Unicode file"

        # Test patch generation with Unicode
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            unicode_hunks, scenario["utf8_commit"]
        )

        assert patch_content is not None, "Should generate patch with Unicode content"

        # Verify Unicode handling in patch
        # The patch should contain the pattern changes regardless of Unicode chars
        assert (
            "OLD_UNICODE_PATTERN" in patch_content
            or "NEW_UNICODE_PATTERN" in patch_content
        ), "Should handle Unicode pattern changes"

    def test_symlink_handling(self, edge_case_repo):
        """Test patch generation with symbolic links."""
        repo = edge_case_repo
        scenario = repo.create_symlink_scenario()

        if scenario is None:
            pytest.skip("Symbolic links not supported on this platform")

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, scenario["base_commit"])

        # Get diff showing symlink target changes
        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", scenario["symlink_update_commit"]]
        )

        assert diff_result.returncode == 0, "Should handle symlink target changes"

        hunks = hunk_parser._parse_diff_output(diff_result.stdout)
        target_hunks = [h for h in hunks if h.file_path == "symlink_target.c"]

        # Should find changes to the target file, not the symlink itself
        assert len(target_hunks) > 0, "Should find hunks in symlink target"

        # Test patch generation with symlinks
        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            target_hunks, scenario["symlink_commit"]
        )

        assert patch_content is not None, "Should generate patch for symlink scenario"
        assert "symlink_target.c" in patch_content, "Patch should reference target file"

    def test_corrupted_diff_handling(self, edge_case_repo):
        """Test handling of corrupted or malformed diff content."""
        repo = edge_case_repo

        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        RebaseManager(git_ops, repo.base_commit)

        # Test various corrupted diff formats
        corrupted_diffs = [
            # Missing hunk header
            """diff --git a/test.c b/test.c
index 1234567..abcdefg 100644
--- a/test.c
+++ b/test.c
-old line
+new line
""",
            # Malformed hunk header
            """diff --git a/test.c b/test.c
index 1234567..abcdefg 100644
--- a/test.c
+++ b/test.c
@@ invalid hunk header @@
-old line
+new line
""",
            # Truncated diff
            """diff --git a/test.c b/test.c
index 1234567..abcdefg 100644
--- a/test.c
+++ b/test.c
@@ -1,1 +1,1 @@
-old line
""",
            # Mixed line endings and control characters
            """diff --git a/test.c b/test.c\r\n
index 1234567..abcdefg 100644\r\n
--- a/test.c\r\n
+++ b/test.c\r\n
@@ -1,1 +1,1 @@\r\n
-old line\x00\r\n
+new line\r\n
""",
        ]

        for i, corrupted_diff in enumerate(corrupted_diffs):
            print(f"Testing corrupted diff scenario {i + 1}")

            # Test that parser handles corrupted input gracefully
            try:
                hunks = hunk_parser._parse_diff_output(corrupted_diff)
                # Should either parse correctly or return empty list, but not crash
                assert isinstance(hunks, list), (
                    f"Should return list for corrupted diff {i + 1}"
                )

            except Exception as e:
                # Should not raise unhandled exceptions for corrupted input
                assert False, (
                    f"Parser should handle corrupted diff {i + 1} gracefully: {e}"
                )

    def test_memory_pressure_scenarios(self, edge_case_repo):
        """Test patch generation under memory pressure conditions."""
        repo = edge_case_repo

        # Create scenario with many files and hunks
        files_content = {}
        for file_idx in range(20):  # Many files
            content_lines = []
            for line_idx in range(500):  # Medium-sized files
                if line_idx % 25 == 12:  # Regular pattern
                    content_lines.append(f"#if OLD_PATTERN_{file_idx}")
                else:
                    content_lines.append(f"// File {file_idx} Line {line_idx}")

            files_content[f"memory_test_{file_idx}.c"] = "\n".join(content_lines)

        # Add all files
        for filename, content in files_content.items():
            file_path = repo.repo_path / filename
            file_path.write_text(content)

        subprocess.run(["git", "add", "."], cwd=repo.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add many files for memory test"],
            cwd=repo.repo_path,
            check=True,
        )

        memory_base_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Update patterns in all files
        for filename in files_content.keys():
            file_path = repo.repo_path / filename
            content = file_path.read_text()
            updated_content = content.replace("OLD_PATTERN_", "NEW_PATTERN_")
            file_path.write_text(updated_content)

        subprocess.run(["git", "add", "."], cwd=repo.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Update all patterns"],
            cwd=repo.repo_path,
            check=True,
        )

        pattern_update_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo.repo_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Test patch generation with many files
        git_ops = GitOps(str(repo.repo_path))
        hunk_parser = HunkParser(git_ops)
        rebase_manager = RebaseManager(git_ops, repo.base_commit)

        diff_result = git_ops.run_git_command(
            ["show", "--no-merges", pattern_update_commit]
        )
        hunks = hunk_parser._parse_diff_output(diff_result.stdout)

        # Should find hunks for many files
        assert len(hunks) > 10, f"Should find many hunks, got {len(hunks)}"

        # Test memory usage during patch generation
        import psutil
        import gc

        gc.collect()
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        patch_content = rebase_manager._create_corrected_patch_for_hunks(
            hunks, memory_base_commit
        )

        gc.collect()
        memory_after = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = memory_after - memory_before

        # Should complete successfully without excessive memory usage
        assert patch_content is not None, "Should generate patch under memory pressure"
        assert memory_increase < 200, (
            f"Memory usage increase too high: {memory_increase:.1f}MB"
        )

        # Verify patch structure
        file_count = len(
            [line for line in patch_content.split("\n") if line.startswith("--- a/")]
        )
        assert file_count >= 10, f"Should have patches for many files, got {file_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
