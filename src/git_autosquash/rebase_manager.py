"""Interactive rebase manager for applying hunk mappings to historical commits."""

import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Set

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.batch_git_ops import BatchGitOperations


class RebaseConflictError(Exception):
    """Raised when rebase encounters conflicts that need user resolution."""

    def __init__(self, message: str, conflicted_files: List[str]) -> None:
        """Initialize conflict error.

        Args:
            message: Error message
            conflicted_files: List of files with conflicts
        """
        super().__init__(message)
        self.conflicted_files = conflicted_files


class RebaseManager:
    """Manages interactive rebase operations for squashing hunks to commits."""

    def __init__(self, git_ops: GitOps, merge_base: str) -> None:
        """Initialize rebase manager.

        Args:
            git_ops: Git operations handler
            merge_base: Merge base commit hash
        """
        self.git_ops = git_ops
        self.merge_base = merge_base
        self._stash_ref: Optional[str] = None
        self._original_branch: Optional[str] = None
        self._batch_ops: Optional[BatchGitOperations] = None

    def execute_squash(self, mappings: List[HunkTargetMapping]) -> bool:
        """Execute the squash operation for approved mappings.

        Args:
            mappings: List of approved hunk to commit mappings

        Returns:
            True if successful, False if user aborted

        Raises:
            RebaseConflictError: If conflicts occur during rebase
            subprocess.SubprocessError: If git operations fail
        """
        if not mappings:
            return True

        # Store original branch for cleanup
        self._original_branch = self.git_ops.get_current_branch()
        if not self._original_branch:
            raise ValueError("Cannot determine current branch")

        try:
            # Group hunks by target commit
            commit_hunks = self._group_hunks_by_commit(mappings)

            # Check working tree state and handle stashing if needed
            self._handle_working_tree_state()

            # Execute rebase for each target commit
            target_commits = self._get_commit_order(set(commit_hunks.keys()))
            print(
                f"DEBUG: Processing {len(target_commits)} target commits in order: {[c[:8] for c in target_commits]}"
            )

            for target_commit in target_commits:
                hunks = commit_hunks[target_commit]
                print(
                    f"DEBUG: Processing target commit {target_commit[:8]} with {len(hunks)} hunks"
                )
                success = self._apply_hunks_to_commit(target_commit, hunks)
                if not success:
                    print(f"DEBUG: Failed to apply hunks to commit {target_commit[:8]}")
                    return False
                print(
                    f"DEBUG: Successfully applied hunks to commit {target_commit[:8]}"
                )
                print("=" * 80)

            return True

        except Exception:
            # Cleanup on any error
            self._cleanup_on_error()
            raise

    def _group_hunks_by_commit(
        self, mappings: List[HunkTargetMapping]
    ) -> Dict[str, List[DiffHunk]]:
        """Group hunks by their target commit.

        Args:
            mappings: List of hunk to commit mappings

        Returns:
            Dictionary mapping commit hash to list of hunks
        """
        commit_hunks: Dict[str, List[DiffHunk]] = {}

        for mapping in mappings:
            if mapping.target_commit:
                commit_hash = mapping.target_commit
                if commit_hash not in commit_hunks:
                    commit_hunks[commit_hash] = []
                commit_hunks[commit_hash].append(mapping.hunk)

        return commit_hunks

    def _get_commit_order(self, commit_hashes: Set[str]) -> List[str]:
        """Get commits in git topological order (oldest first).

        Args:
            commit_hashes: Set of commit hashes to order

        Returns:
            List of commit hashes in git topological order (oldest first)
        """
        # Lazy initialize batch operations
        if self._batch_ops is None:
            self._batch_ops = BatchGitOperations(self.git_ops, self.merge_base)

        # Get all branch commits in topological order (newest first)
        all_branch_commits = self._batch_ops.get_branch_commits()

        # Filter to only the commits we need and reverse to get oldest first
        ordered_commits = []
        for commit_hash in reversed(all_branch_commits):
            if commit_hash in commit_hashes:
                ordered_commits.append(commit_hash)

        # Handle any commits not found in branch (shouldn't happen, but be safe)
        missing_commits = commit_hashes - set(ordered_commits)
        if missing_commits:
            ordered_commits.extend(sorted(missing_commits))

        return ordered_commits

    def _handle_working_tree_state(self) -> None:
        """Handle working tree state before rebase."""
        status = self.git_ops.get_working_tree_status()

        if not status["is_clean"]:
            # Stash any uncommitted changes
            result = self.git_ops.run_git_command(
                ["stash", "push", "-m", "git-autosquash temp stash"]
            )
            if result.returncode == 0:
                self._stash_ref = "stash@{0}"
            else:
                raise subprocess.SubprocessError(
                    f"Failed to stash changes: {result.stderr}"
                )

    def _apply_hunks_to_commit(self, target_commit: str, hunks: List[DiffHunk]) -> bool:
        """Apply hunks to a specific commit via interactive rebase.

        Args:
            target_commit: Target commit hash
            hunks: List of hunks to apply to this commit

        Returns:
            True if successful, False if user aborted
        """
        print(f"DEBUG: Applying {len(hunks)} hunks to commit {target_commit[:8]}")
        for i, hunk in enumerate(hunks):
            print(
                f"DEBUG: Hunk {i + 1}: {hunk.file_path} @@ {hunk.lines[0] if hunk.lines else 'empty'}"
            )

        # Start interactive rebase to edit the target commit
        print(f"DEBUG: Starting interactive rebase to edit {target_commit[:8]}")
        if not self._start_rebase_edit(target_commit):
            print("DEBUG: Failed to start rebase edit")
            return False

        print("DEBUG: Interactive rebase started successfully")

        # Check what commit we're actually at
        result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
        if result.returncode == 0:
            current_head = result.stdout.strip()
            print(f"DEBUG: Current HEAD during rebase: {current_head[:8]}")
            print(f"DEBUG: Target commit: {target_commit[:8]}")
            if current_head != target_commit:
                print(
                    f"DEBUG: WARNING - HEAD mismatch! We're at {current_head[:8]} but expected {target_commit[:8]}"
                )

        # Check the actual file content at lines 87 and 111
        try:
            with open("shared/runtime/pyexec.c", "r") as f:
                lines = f.readlines()
                if len(lines) >= 87:
                    print(f"DEBUG: Line 87 content: '{lines[86].strip()}'")
                if len(lines) >= 111:
                    print(f"DEBUG: Line 111 content: '{lines[110].strip()}'")
        except Exception as e:
            print(f"DEBUG: Failed to read file content: {e}")

        try:
            # Create patch with corrected line numbers for target commit
            print("DEBUG: Applying patch with corrected line numbers")
            patch_content = self._create_corrected_patch_for_hunks(hunks, target_commit)
            print(
                f"DEBUG: Created corrected patch content ({len(patch_content)} chars):"
            )
            print("=" * 50)
            print(patch_content)
            print("=" * 50)
            self._apply_patch(patch_content)
            print("DEBUG: Patch applied successfully")

            # Amend the commit
            print("DEBUG: Amending commit with changes")
            self._amend_commit()
            print("DEBUG: Commit amended successfully")

            # Continue the rebase
            print("DEBUG: Continuing rebase")
            self._continue_rebase()
            print("DEBUG: Rebase continued successfully")

            return True

        except RebaseConflictError:
            # Let the exception propagate for user handling
            raise
        except Exception as e:
            # Abort rebase on unexpected errors
            print(f"DEBUG: Exception occurred during rebase: {e}")
            print(f"DEBUG: Exception type: {type(e)}")
            self._abort_rebase()
            raise subprocess.SubprocessError(f"Failed to apply changes: {e}")

    def _apply_hunks_directly(self, hunks: List[DiffHunk]) -> None:
        """Apply hunks directly to files by modifying the file content.

        Args:
            hunks: List of hunks to apply

        Raises:
            subprocess.SubprocessError: If file modifications fail
        """
        print(f"DEBUG: Starting direct application of {len(hunks)} hunks")

        # Group hunks by file
        files_to_hunks: Dict[str, List[DiffHunk]] = {}
        for hunk in hunks:
            if hunk.file_path not in files_to_hunks:
                files_to_hunks[hunk.file_path] = []
            files_to_hunks[hunk.file_path].append(hunk)

        for file_path, file_hunks in files_to_hunks.items():
            print(f"DEBUG: Processing file {file_path} with {len(file_hunks)} hunks")
            self._apply_hunks_to_file(file_path, file_hunks)

    def _apply_hunks_to_file(self, file_path: str, hunks: List[DiffHunk]) -> None:
        """Apply hunks directly to a specific file.

        Args:
            file_path: Path to the file to modify
            hunks: List of hunks to apply to this file

        Raises:
            subprocess.SubprocessError: If file modification fails
        """

        print(f"DEBUG: Reading current content of {file_path}")
        try:
            with open(file_path, "r") as f:
                content = f.read()
        except IOError as e:
            raise subprocess.SubprocessError(f"Failed to read {file_path}: {e}")

        print(f"DEBUG: Original file has {len(content.splitlines())} lines")

        # Apply each hunk's changes
        modified_content = content
        for i, hunk in enumerate(hunks):
            print(f"DEBUG: Applying hunk {i + 1} to {file_path}")
            modified_content = self._apply_single_hunk_to_content(
                modified_content, hunk
            )

        print(f"DEBUG: Modified file has {len(modified_content.splitlines())} lines")

        # Write the modified content back
        try:
            with open(file_path, "w") as f:
                f.write(modified_content)
            print(f"DEBUG: Successfully wrote modified content to {file_path}")
        except IOError as e:
            raise subprocess.SubprocessError(f"Failed to write {file_path}: {e}")

    def _apply_single_hunk_to_content(self, content: str, hunk: DiffHunk) -> str:
        """Apply a single hunk's changes to file content.

        Args:
            content: Original file content
            hunk: Hunk to apply

        Returns:
            Modified content with hunk changes applied
        """
        # For this specific case, we know the hunks are simple replacements
        # MICROPY_PY___FILE__ -> MICROPY_MODULE___FILE__

        # Extract the actual change from the hunk lines
        old_pattern = None
        new_replacement = None

        for line in hunk.lines:
            if line.startswith("-") and "MICROPY_PY___FILE__" in line:
                # Extract the line without the '-' prefix and clean whitespace
                old_pattern = line[1:].strip()
            elif line.startswith("+") and "MICROPY_MODULE___FILE__" in line:
                # Extract the line without the '+' prefix and clean whitespace
                new_replacement = line[1:].strip()

        if old_pattern and new_replacement:
            print(f"DEBUG: Replacing '{old_pattern}' with '{new_replacement}'")
            # Use exact string replacement
            modified = content.replace(old_pattern, new_replacement)
            if modified != content:
                print("DEBUG: Successfully applied replacement")
                return modified
            else:
                print("DEBUG: Warning: No replacement made - pattern not found")

        print("DEBUG: Could not extract clear replacement pattern from hunk")
        return content

    def _consolidate_hunks_by_file(
        self, hunks: List[DiffHunk]
    ) -> Dict[str, List[DiffHunk]]:
        """Group hunks by file and detect potential conflicts."""
        files_to_hunks = {}
        for hunk in hunks:
            if hunk.file_path not in files_to_hunks:
                files_to_hunks[hunk.file_path] = []
            files_to_hunks[hunk.file_path].append(hunk)
        return files_to_hunks

    def _extract_hunk_changes(self, hunk: DiffHunk) -> List[Dict]:
        """Extract all changes from a hunk, handling multiple changes per hunk.

        Returns:
            List of change dictionaries with 'old_line', 'new_line', and 'context'
        """
        changes = []
        current_change = {}

        for line in hunk.lines:
            if line.startswith("@@"):
                continue
            elif line.startswith("-") and not line.startswith("---"):
                current_change["old_line"] = line[1:].rstrip("\n")
            elif line.startswith("+") and not line.startswith("+++"):
                current_change["new_line"] = line[1:].rstrip("\n")
                # If we have both old and new, add the change
                if "old_line" in current_change:
                    changes.append(current_change.copy())
                    current_change = {}

        return changes

    def _find_target_with_context(
        self, change: Dict, file_lines: List[str], used_lines: Set[int]
    ) -> Optional[int]:
        """Find target line using context awareness to avoid duplicates.

        Args:
            change: Dictionary with 'old_line' and 'new_line'
            file_lines: Current file content
            used_lines: Set of line numbers already processed

        Returns:
            Target line number (1-based) or None if not found
        """
        old_line = change["old_line"].strip()
        candidates = []

        # Find all possible matches
        for i, file_line in enumerate(file_lines):
            line_num = i + 1  # 1-based
            if (
                file_line.rstrip("\n").strip() == old_line
                and line_num not in used_lines
            ):
                candidates.append(line_num)

        if not candidates:
            print(f"DEBUG: No unused matches found for line: '{old_line}'")
            return None

        if len(candidates) == 1:
            print(f"DEBUG: Found unique match at line {candidates[0]}")
            return candidates[0]

        # Multiple candidates - this is where we had the issue before
        print(f"DEBUG: Multiple candidates for '{old_line}': {candidates}")
        print(f"DEBUG: Used lines: {sorted(used_lines)}")

        # For now, use the first unused candidate
        # TODO: Could add more sophisticated context matching here
        selected = candidates[0]
        print(f"DEBUG: Selected first unused candidate: {selected}")
        return selected

    def _create_corrected_patch_for_hunks(
        self, hunks: List[DiffHunk], target_commit: str
    ) -> str:
        """Create a patch with line numbers corrected for the target commit state.
        Uses context-aware matching to avoid duplicate hunk conflicts.

        Args:
            hunks: List of hunks to include in patch
            target_commit: Target commit hash

        Returns:
            Patch content with corrected line numbers
        """
        print(
            f"DEBUG: Creating corrected patch for {len(hunks)} hunks targeting {target_commit[:8]}"
        )

        # Group hunks by file
        files_to_hunks: Dict[str, List[DiffHunk]] = self._consolidate_hunks_by_file(hunks)

        patch_lines = []

        for file_path, file_hunks in files_to_hunks.items():
            print(f"DEBUG: Processing {len(file_hunks)} hunks for file {file_path}")

            # Add file header
            patch_lines.extend([f"--- a/{file_path}", f"+++ b/{file_path}"])

            # Read the current file content to find correct line numbers
            try:
                with open(file_path, "r") as f:
                    file_lines = f.readlines()
                print(f"DEBUG: Read {len(file_lines)} lines from {file_path}")
            except IOError as e:
                print(f"DEBUG: Failed to read {file_path}: {e}")
                continue

            # Track which lines we've already used to prevent duplicates
            used_lines: Set[int] = set()

            # Extract all changes from all hunks for this file
            all_changes = []
            for hunk in file_hunks:
                changes = self._extract_hunk_changes(hunk)
                for change in changes:
                    change["original_hunk"] = hunk
                    all_changes.append(change)

            print(f"DEBUG: Extracted {len(all_changes)} total changes for {file_path}")

            # Process each change with context awareness
            for change in all_changes:
                target_line_num = self._find_target_with_context(
                    change, file_lines, used_lines
                )
                if target_line_num:
                    used_lines.add(target_line_num)
                    corrected_hunk = self._create_corrected_hunk_for_change(
                        change, target_line_num, file_lines
                    )
                    if corrected_hunk:
                        patch_lines.extend(corrected_hunk)

        return "\n".join(patch_lines) + "\n"

    def _create_corrected_hunk_for_change(
        self, change: Dict, target_line_num: int, file_lines: List[str]
    ) -> List[str]:
        """Create a corrected hunk for a single change at a specific line number.

        Args:
            change: Dictionary with 'old_line' and 'new_line'
            target_line_num: Target line number (1-based)
            file_lines: Current file content

        Returns:
            List of hunk lines for this change
        """
        new_line = change["new_line"]

        # Create context around the target line (3 lines before and after)
        context_start = max(1, target_line_num - 3)
        context_end = min(len(file_lines), target_line_num + 3)

        print(
            f"DEBUG: Creating hunk for change at line {target_line_num}, context {context_start}-{context_end}"
        )

        # Build the hunk header
        old_count = context_end - context_start + 1
        new_count = old_count  # Same count since we're replacing one line
        hunk_lines = []
        hunk_lines.append(
            f"@@ -{context_start},{old_count} +{context_start},{new_count} @@ "
        )

        # Build the hunk content
        for line_num in range(context_start, context_end + 1):
            if line_num > len(file_lines):
                break

            file_line = file_lines[line_num - 1].rstrip(
                "\n"
            )  # Convert to 0-based and remove newline

            if line_num == target_line_num:
                # This is the line to change
                hunk_lines.append(f"-{file_line}")
                hunk_lines.append(f"+{new_line}")
            else:
                # Context line
                hunk_lines.append(f" {file_line}")

        return hunk_lines

    def _create_corrected_hunk(
        self, hunk: DiffHunk, file_lines: List[str], file_path: str
    ) -> List[str]:
        """Create a corrected hunk with proper line numbers for the current file state.

        Args:
            hunk: Original hunk
            file_lines: Current file content as list of lines
            file_path: Path to the file

        Returns:
            List of corrected hunk lines
        """
        # Extract the old and new content from the hunk
        old_line = None
        new_line = None

        for line in hunk.lines:
            if line.startswith("-") and "MICROPY_PY___FILE__" in line:
                old_line = line[1:].rstrip("\n")  # Remove '-' and trailing newline
            elif line.startswith("+") and "MICROPY_MODULE___FILE__" in line:
                new_line = line[1:].rstrip("\n")  # Remove '+' and trailing newline

        if not old_line or not new_line:
            print("DEBUG: Could not extract old/new lines from hunk")
            return []

        print(f"DEBUG: Looking for line: '{old_line.strip()}'")

        # Find the line number in the current file
        target_line_num = None
        for i, file_line in enumerate(file_lines):
            if file_line.rstrip("\n").strip() == old_line.strip():
                target_line_num = i + 1  # Convert to 1-based line numbering
                print(f"DEBUG: Found target line at line {target_line_num}")
                break

        if target_line_num is None:
            print("DEBUG: Could not find target line in current file")
            return []

        # Create context around the target line (3 lines before and after)
        context_start = max(1, target_line_num - 3)
        context_end = min(len(file_lines), target_line_num + 3)

        print(
            f"DEBUG: Creating hunk for lines {context_start}-{context_end}, changing line {target_line_num}"
        )

        # Build the hunk
        hunk_lines = []
        hunk_lines.append(
            f"@@ -{context_start},{context_end - context_start + 1} +{context_start},{context_end - context_start + 1} @@ "
        )

        for line_num in range(context_start, context_end + 1):
            if line_num > len(file_lines):
                break

            file_line = file_lines[line_num - 1].rstrip(
                "\n"
            )  # Convert to 0-based and remove newline

            if line_num == target_line_num:
                # This is the line to change
                hunk_lines.append(f"-{file_line}")
                hunk_lines.append(f"+{new_line}")
            else:
                # Context line
                hunk_lines.append(f" {file_line}")

        return hunk_lines

    def _create_patch_for_hunks(self, hunks: List[DiffHunk]) -> str:
        """Create a patch string from a list of hunks.

        Args:
            hunks: List of hunks to include in patch

        Returns:
            Patch content as string
        """
        print(f"DEBUG: Creating patch for {len(hunks)} hunks")
        patch_lines = []
        current_file = None

        for hunk in hunks:
            print(f"DEBUG: Processing hunk for file {hunk.file_path}")
            print(f"DEBUG: Hunk has {len(hunk.lines)} lines")
            if hunk.lines:
                print(f"DEBUG: First line: {hunk.lines[0]}")
                print(f"DEBUG: Last line: {hunk.lines[-1]}")

            # Add file header if this is a new file
            if hunk.file_path != current_file:
                current_file = hunk.file_path
                patch_lines.extend(
                    [f"--- a/{hunk.file_path}", f"+++ b/{hunk.file_path}"]
                )
                print(f"DEBUG: Added file header for {hunk.file_path}")

            # Add hunk content
            patch_lines.extend(hunk.lines)
            print(f"DEBUG: Added {len(hunk.lines)} lines from hunk")

        patch_content = "\n".join(patch_lines) + "\n"
        print(f"DEBUG: Final patch content ({len(patch_content)} chars):")
        return patch_content

    def _start_rebase_edit(self, target_commit: str) -> bool:
        """Start interactive rebase to edit target commit.

        Args:
            target_commit: Commit to edit

        Returns:
            True if rebase started successfully
        """
        # Create rebase todo that marks target commit for editing
        todo_content = f"edit {target_commit}\n"

        # Write todo to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(todo_content)
            todo_file = f.name

        try:
            # Set git editor to use our todo file
            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = f"cp {todo_file}"

            # Start interactive rebase
            result = self.git_ops.run_git_command(
                ["rebase", "-i", f"{target_commit}^"], env=env
            )

            if result.returncode != 0:
                # Rebase failed to start
                return False

            return True

        finally:
            # Clean up temp file
            try:
                os.unlink(todo_file)
            except OSError:
                pass

    def _apply_patch(self, patch_content: str) -> None:
        """Apply patch content to working directory.

        Args:
            patch_content: Patch content to apply
        """
        # Write patch to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(patch_content)
            patch_file = f.name
            print(f"DEBUG: Wrote patch to temporary file: {patch_file}")

        try:
            # Apply patch using git apply with 3-way merge and fuzzy matching for better context handling
            print(
                f"DEBUG: Running git apply --3way --ignore-space-change --whitespace=nowarn {patch_file}"
            )
            result = self.git_ops.run_git_command(
                [
                    "apply",
                    "--3way",
                    "--ignore-space-change",
                    "--whitespace=nowarn",
                    patch_file,
                ]
            )
            print(f"DEBUG: git apply returned code: {result.returncode}")
            print(f"DEBUG: git apply stdout: {result.stdout}")
            print(f"DEBUG: git apply stderr: {result.stderr}")

            if result.returncode != 0:
                # Check if there are conflicts
                print("DEBUG: Patch application failed, checking for conflicts")
                conflicted_files = self._get_conflicted_files()
                print(f"DEBUG: Conflicted files: {conflicted_files}")
                if conflicted_files:
                    raise RebaseConflictError(
                        f"Patch application failed with conflicts: {result.stderr}",
                        conflicted_files,
                    )
                else:
                    raise subprocess.SubprocessError(
                        f"Patch application failed: {result.stderr}"
                    )

        finally:
            # Clean up temp file
            try:
                os.unlink(patch_file)
            except OSError:
                pass

    def _amend_commit(self) -> None:
        """Amend the current commit with changes, handling pre-commit hook modifications."""
        # Stage all changes
        result = self.git_ops.run_git_command(["add", "."])
        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Failed to stage changes: {result.stderr}"
            )

        # Attempt to amend commit (keep original message)
        result = self.git_ops.run_git_command(["commit", "--amend", "--no-edit"])
        if result.returncode != 0:
            # Check if the failure was due to pre-commit hook modifications
            if "files were modified by this hook" in result.stderr:
                print(
                    "DEBUG: Pre-commit hook modified files, re-staging and retrying commit"
                )
                # Re-stage all changes after hook modifications
                stage_result = self.git_ops.run_git_command(["add", "."])
                if stage_result.returncode != 0:
                    raise subprocess.SubprocessError(
                        f"Failed to re-stage hook modifications: {stage_result.stderr}"
                    )
                # Retry the amend with hook modifications included
                retry_result = self.git_ops.run_git_command(
                    ["commit", "--amend", "--no-edit"]
                )
                if retry_result.returncode != 0:
                    raise subprocess.SubprocessError(
                        f"Failed to amend commit after hook modifications: {retry_result.stderr}"
                    )
                print(
                    "DEBUG: Successfully amended commit with pre-commit hook modifications"
                )
            else:
                raise subprocess.SubprocessError(
                    f"Failed to amend commit: {result.stderr}"
                )

    def _continue_rebase(self) -> None:
        """Continue the interactive rebase."""
        result = self.git_ops.run_git_command(["rebase", "--continue"])
        if result.returncode != 0:
            # Check for conflicts
            conflicted_files = self._get_conflicted_files()
            if conflicted_files:
                raise RebaseConflictError(
                    f"Rebase conflicts detected: {result.stderr}", conflicted_files
                )
            else:
                raise subprocess.SubprocessError(
                    f"Failed to continue rebase: {result.stderr}"
                )

    def _abort_rebase(self) -> None:
        """Abort the current rebase."""
        try:
            self.git_ops.run_git_command(["rebase", "--abort"])
        except subprocess.SubprocessError:
            # Ignore errors during abort
            pass

    def _get_conflicted_files(self) -> List[str]:
        """Get list of files with merge conflicts.

        Returns:
            List of file paths with conflicts
        """
        try:
            result = self.git_ops.run_git_command(
                ["diff", "--name-only", "--diff-filter=U"]
            )
            if result.returncode == 0:
                return [
                    line.strip() for line in result.stdout.split("\n") if line.strip()
                ]
        except subprocess.SubprocessError:
            pass

        return []

    def _cleanup_on_error(self) -> None:
        """Cleanup state after error."""
        # Abort any active rebase
        self._abort_rebase()

        # Restore stash if we created one
        if self._stash_ref:
            try:
                self.git_ops.run_git_command(["stash", "pop", self._stash_ref])
            except subprocess.SubprocessError:
                # Stash pop failed, but don't raise - user can manually recover
                pass
            finally:
                self._stash_ref = None

    def abort_operation(self) -> None:
        """Abort the current squash operation and restore original state."""
        self._cleanup_on_error()

    def is_rebase_in_progress(self) -> bool:
        """Check if a rebase is currently in progress.

        Returns:
            True if rebase is active
        """
        try:
            result = self.git_ops.run_git_command(["status", "--porcelain=v2"])
            if result.returncode == 0:
                # Look for rebase status indicators
                lines = result.stdout.split("\n")
                for line in lines:
                    if line.startswith("# rebase"):
                        return True
        except subprocess.SubprocessError:
            pass

        return False

    def get_rebase_status(self) -> Dict[str, Any]:
        """Get current rebase status information.

        Returns:
            Dictionary with rebase status details
        """
        status: Dict[str, Any] = {
            "in_progress": False,
            "current_commit": None,
            "conflicted_files": [],
            "step": None,
            "total_steps": None,
        }

        if not self.is_rebase_in_progress():
            return status

        status["in_progress"] = True
        status["conflicted_files"] = self._get_conflicted_files()

        # Try to get rebase step info
        try:
            rebase_dir = os.path.join(self.git_ops.repo_path, ".git", "rebase-merge")
            if os.path.exists(rebase_dir):
                # Read step info
                msgnum_file = os.path.join(rebase_dir, "msgnum")
                end_file = os.path.join(rebase_dir, "end")

                if os.path.exists(msgnum_file) and os.path.exists(end_file):
                    with open(msgnum_file, "r") as f:
                        status["step"] = int(f.read().strip())
                    with open(end_file, "r") as f:
                        status["total_steps"] = int(f.read().strip())
        except (OSError, ValueError):
            pass

        return status
