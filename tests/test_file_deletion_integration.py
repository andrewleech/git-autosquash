"""Integration tests for file deletion support."""

import time


from git_autosquash.blame_analyzer import BlameAnalyzer
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import HunkParser
from tests.conftest import temporary_test_repository


class TestFileDeletionIntegration:
    """End-to-end integration tests for file deletion features."""

    def test_empty_file_deletion_end_to_end(self):
        """Test complete flow: parse -> analyze -> apply for empty file deletion."""
        with temporary_test_repository("deletion_test") as repo:
            git_ops = GitOps(str(repo.repo_path))

            # Create an initial commit to serve as merge base
            initial_file = repo.repo_path / "README.md"
            initial_file.write_text("# Test Project\n")
            git_ops.run_git_command(["add", "README.md"])
            git_ops.run_git_command(["commit", "-m", "Initial commit"])
            initial_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            # Setup: create file, commit, delete, commit
            empty_file = repo.repo_path / "empty.txt"
            empty_file.touch()

            git_ops.run_git_command(["add", "empty.txt"])
            git_ops.run_git_command(["commit", "-m", "Add empty file"])

            addition_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            git_ops.run_git_command(["rm", "empty.txt"])
            git_ops.run_git_command(["commit", "-m", "Delete empty file"])

            deletion_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            # Parse deletion
            parser = HunkParser(git_ops)
            hunks = parser.get_diff_hunks(from_commit=deletion_sha)

            assert len(hunks) == 1
            assert hunks[0].is_file_deletion is True
            assert hunks[0].file_path == "empty.txt"

            # Analyze for target - use initial commit as merge base
            analyzer = BlameAnalyzer(git_ops, initial_sha, f"{deletion_sha}~1")
            mappings = analyzer.analyze_hunks(hunks)

            assert len(mappings) == 1
            assert mappings[0].target_commit == addition_sha
            assert mappings[0].targeting_method.value == "file_deletion"

    def test_nonempty_file_deletion_end_to_end(self):
        """Test complete flow for non-empty file deletion."""
        with temporary_test_repository("deletion_test") as repo:
            # Setup
            test_file = repo.repo_path / "test.txt"
            test_file.write_text("line 1\nline 2\nline 3\n")

            git_ops = GitOps(str(repo.repo_path))
            git_ops.run_git_command(["add", "test.txt"])
            git_ops.run_git_command(["commit", "-m", "Add test file"])

            git_ops.run_git_command(["rm", "test.txt"])
            git_ops.run_git_command(["commit", "-m", "Delete test file"])

            deletion_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            # Parse and verify content is captured
            parser = HunkParser(git_ops)
            hunks = parser.get_diff_hunks(from_commit=deletion_sha)

            assert len(hunks) == 1
            assert hunks[0].is_file_deletion is True
            assert hunks[0].has_deletions is True
            assert "line 1" in "\n".join(hunks[0].lines)

    def test_binary_file_deletion(self):
        """Test deletion of binary files."""
        with temporary_test_repository("deletion_test") as repo:
            # Create binary file
            binary_file = repo.repo_path / "binary.bin"
            binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe")

            git_ops = GitOps(str(repo.repo_path))
            git_ops.run_git_command(["add", "binary.bin"])
            git_ops.run_git_command(["commit", "-m", "Add binary"])

            git_ops.run_git_command(["rm", "binary.bin"])
            git_ops.run_git_command(["commit", "-m", "Delete binary"])

            deletion_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            # Parse - should handle binary gracefully
            parser = HunkParser(git_ops)
            hunks = parser.get_diff_hunks(from_commit=deletion_sha)

            assert len(hunks) >= 1
            deletion_hunk = [h for h in hunks if h.file_path == "binary.bin"][0]
            assert deletion_hunk.is_file_deletion is True

    def test_performance_many_file_deletions(self):
        """Test performance with many file deletions in single commit."""
        with temporary_test_repository("deletion_test") as repo:
            git_ops = GitOps(str(repo.repo_path))

            # Create 50 files
            for i in range(50):
                (repo.repo_path / f"file{i}.txt").write_text(f"content {i}")

            git_ops.run_git_command(["add", "."])
            git_ops.run_git_command(["commit", "-m", "Add 50 files"])

            # Delete all
            for i in range(50):
                git_ops.run_git_command(["rm", f"file{i}.txt"])

            git_ops.run_git_command(["commit", "-m", "Delete all files"])
            deletion_sha = git_ops.run_git_command(["rev-parse", "HEAD"]).stdout.strip()

            # Parse - should complete in reasonable time
            start = time.time()

            parser = HunkParser(git_ops)
            hunks = parser.get_diff_hunks(from_commit=deletion_sha)

            elapsed = time.time() - start

            assert len(hunks) == 50
            assert all(h.is_file_deletion for h in hunks)
            assert elapsed < 5.0  # Should complete in under 5 seconds
