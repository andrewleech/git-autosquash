"""Interactive rebase manager for applying hunk mappings to historical commits."""

import logging
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Set

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.batch_git_ops import BatchGitOperations

logger = logging.getLogger(__name__)


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

            # Restore stash if we created one (success path)
            if self._stash_ref:
                try:
                    result = self.git_ops.run_git_command(
                        ["stash", "pop", self._stash_ref]
                    )
                    if result.returncode != 0:
                        print(f"DEBUG: Failed to restore stash: {result.stderr}")
                        print(
                            "DEBUG: You may need to manually restore with: git stash pop"
                        )
                except Exception as e:
                    print(f"DEBUG: Error restoring stash: {e}")
                    print("DEBUG: You may need to manually restore with: git stash pop")
                finally:
                    self._stash_ref = None

            return True

        except RebaseConflictError:
            # Don't cleanup on rebase conflicts - let user resolve manually
            raise
        except Exception:
            # Cleanup on any other error
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
        """Get commits in git topological order (newest first).

        Args:
            commit_hashes: Set of commit hashes to order

        Returns:
            List of commit hashes in git topological order (newest first)
        """
        # Lazy initialize batch operations
        if self._batch_ops is None:
            self._batch_ops = BatchGitOperations(self.git_ops, self.merge_base)

        # Get all branch commits in chronological order (oldest first)
        all_branch_commits = self._batch_ops.get_branch_commits()

        # Filter to only the commits we need, keeping chronological order
        ordered_commits = []
        for commit_hash in all_branch_commits:
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

        # Validate status data
        if not isinstance(status, dict):
            raise ValueError("Invalid working tree status format")

        operation_type = None
        message = None
        stash_sha = None

        if status.get("has_staged", False) and status.get("has_unstaged", False):
            # Mixed changes: stash only unstaged changes, keep staged changes in index
            operation_type = "mixed"
            message = "git-autosquash: temporary stash of unstaged changes"

            # Use --keep-index to stash only unstaged changes
            stash_sha = self._create_stash_with_options(message, ["--keep-index"])

        elif status.get("has_staged", False) and not status.get("has_unstaged", False):
            # Staged changes only: must stash before rebase
            operation_type = "staged_only"
            message = "git-autosquash: temporary stash of staged changes"

            # Use --staged to stash only staged changes
            stash_sha = self._create_stash_with_options(message, ["--staged"])

        elif not status.get("has_staged", False) and status.get("has_unstaged", False):
            # Unstaged changes only: must stash before rebase
            operation_type = "unstaged_only"
            message = "git-autosquash: temporary stash of unstaged changes"

            # Stash all working tree changes
            stash_sha = self._create_and_store_stash(message)

        else:
            # Clean working tree, nothing to stash
            logger.debug("Working tree is clean, no stashing needed")
            return

        if stash_sha:
            self._stash_ref = stash_sha
            logger.info(f"Working tree prepared. Stash SHA: {stash_sha[:8]}")
        else:
            raise subprocess.SubprocessError(
                f"Failed to stash {operation_type} changes"
            )

    def _create_and_store_stash(self, message: str) -> Optional[str]:
        """Create a stash and return its SHA reference.

        Uses git stash create + store to get a reliable SHA reference
        instead of assuming stash@{0}.

        Args:
            message: Description for the stash

        Returns:
            SHA of created stash, or None if failed or no changes
        """
        # Step 1: Create stash object without modifying stash list
        # This returns a SHA that uniquely identifies the stash
        create_result = self.git_ops.run_git_command(["stash", "create", message])

        if create_result.returncode != 0:
            logger.error(f"Failed to create stash: {create_result.stderr}")
            return None

        stash_sha = create_result.stdout.strip()
        if not stash_sha:
            # No changes to stash (working tree might be clean)
            logger.info("No changes to stash")
            return None

        # Step 2: Store the stash object in the stash list
        # This makes it visible in 'git stash list'
        store_result = self.git_ops.run_git_command(
            ["stash", "store", "-m", message, stash_sha]
        )

        if store_result.returncode != 0:
            logger.error(f"Failed to store stash {stash_sha}: {store_result.stderr}")
            # The stash object exists but isn't in the list
            # We can still use it by SHA
            logger.warning(f"Stash created but not stored in list. SHA: {stash_sha}")

        logger.info(f"Created stash with SHA: {stash_sha}")
        return stash_sha

    def _create_stash_with_options(
        self, message: str, options: List[str]
    ) -> Optional[str]:
        """Create stash with specific options and return SHA.

        Args:
            message: Stash message
            options: List of git stash options (e.g., ['--keep-index'])

        Returns:
            SHA of created stash, or None if failed
        """
        # Use git stash push with options, then get the SHA
        cmd = ["stash", "push"] + options + ["-m", message]
        result = self.git_ops.run_git_command(cmd)

        if result.returncode != 0:
            logger.error(
                f"Failed to create stash with options {options}: {result.stderr}"
            )
            return None

        # Get the SHA of the most recently created stash
        # Use git stash list to get the SHA of stash@{0}
        list_result = self.git_ops.run_git_command(
            ["stash", "list", "--format=%H", "-n", "1"]
        )
        if list_result.returncode == 0 and list_result.stdout.strip():
            stash_sha = list_result.stdout.strip()
            logger.info(f"Created stash with options {options}, SHA: {stash_sha}")
            return stash_sha

        logger.error("Failed to retrieve SHA of created stash")
        return None

    def _restore_stash_by_sha(self, stash_sha: str) -> bool:
        """Restore stash using its SHA reference.

        Args:
            stash_sha: SHA of the stash to restore

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Restoring stash by SHA: {stash_sha[:12]}")

        # Apply the stash
        result = self.git_ops.run_git_command(["stash", "apply", stash_sha])

        if result.returncode != 0:
            # Check if it's a conflict during stash application
            if "CONFLICT" in result.stderr or "conflict" in result.stderr.lower():
                logger.error(
                    f"Conflicts occurred while applying stash {stash_sha[:12]}"
                )
            else:
                logger.error(f"Failed to apply stash {stash_sha}: {result.stderr}")
            return False

        # Successfully applied, now drop the stash
        logger.info("Stash applied successfully, dropping from list")
        drop_result = self.git_ops.run_git_command(["stash", "drop", stash_sha])
        if drop_result.returncode != 0:
            logger.warning(f"Failed to drop stash (non-critical): {drop_result.stderr}")

        return True

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

    def _consolidate_hunks_by_file(
        self, hunks: List[DiffHunk]
    ) -> Dict[str, List[DiffHunk]]:
        """Group hunks by file and detect potential conflicts."""
        files_to_hunks: Dict[str, List[DiffHunk]] = {}
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
            file_line_stripped = file_line.rstrip("\n").strip()

            if file_line_stripped == old_line and line_num not in used_lines:
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
        files_to_hunks: Dict[str, List[DiffHunk]] = self._consolidate_hunks_by_file(
            hunks
        )

        patch_lines = []

        for file_path, file_hunks in files_to_hunks.items():
            print(f"DEBUG: Processing {len(file_hunks)} hunks for file {file_path}")

            # Add file header
            patch_lines.extend([f"--- a/{file_path}", f"+++ b/{file_path}"])

            # Read the file content from target commit to find correct line numbers
            try:
                # Get file content at target commit
                result = self.git_ops.run_git_command(
                    ["show", f"{target_commit}:{file_path}"]
                )
                if result.returncode != 0:
                    print(
                        f"DEBUG: Failed to get {file_path} from {target_commit}: {result.stderr}"
                    )
                    continue

                file_lines = result.stdout.splitlines(keepends=True)
                print(
                    f"DEBUG: Read {len(file_lines)} lines from {file_path} at {target_commit[:8]}"
                )
            except Exception as e:
                print(f"DEBUG: Failed to read {file_path} from {target_commit}: {e}")
                continue

            # Extract all changes from all hunks for this file
            all_changes = []
            for hunk in file_hunks:
                changes = self._extract_hunk_changes(hunk)
                for change in changes:
                    change["original_hunk"] = hunk
                    all_changes.append(change)

            print(f"DEBUG: Extracted {len(all_changes)} total changes for {file_path}")

            # Find target lines for all changes first
            changes_with_targets = []
            used_lines: Set[int] = set()

            for change in all_changes:
                target_line_num = self._find_target_with_context(
                    change, file_lines, used_lines
                )
                if target_line_num is not None:
                    used_lines.add(target_line_num)
                    changes_with_targets.append((change, target_line_num))
                    print(f"DEBUG: Mapped change to line {target_line_num}")
                else:
                    print(
                        f"DEBUG: Could not find target for change: {change['old_line'][:50]}..."
                    )

            # Sort changes by line number
            changes_with_targets.sort(key=lambda x: x[1])

            # Group overlapping changes to avoid hunk conflicts
            consolidated_hunks = self._consolidate_overlapping_changes(
                changes_with_targets, file_lines
            )

            # Add consolidated hunks to patch
            for hunk_lines in consolidated_hunks:
                patch_lines.extend(hunk_lines)

        return "\n".join(patch_lines) + "\n"

    def _consolidate_overlapping_changes(
        self, changes_with_targets: List[tuple], file_lines: List[str]
    ) -> List[List[str]]:
        """Consolidate overlapping changes into non-overlapping hunks.

        Args:
            changes_with_targets: List of (change_dict, target_line_num) tuples sorted by line number
            file_lines: Current file content

        Returns:
            List of hunk line lists ready for patch inclusion
        """
        if not changes_with_targets:
            return []

        consolidated_hunks = []
        current_group: List[tuple] = []

        # Group changes that would create overlapping context
        for i, (change, line_num) in enumerate(changes_with_targets):
            if not current_group:
                # Start new group
                current_group = [(change, line_num)]
            else:
                # Check if this change overlaps with the current group's context
                group_start = min(line for _, line in current_group) - 6
                group_end = max(line for _, line in current_group) + 6

                change_start = line_num - 6
                change_end = line_num + 6

                # If contexts overlap, add to current group
                if change_start <= group_end and change_end >= group_start:
                    current_group.append((change, line_num))
                    print(
                        f"DEBUG: Consolidating change at line {line_num} with existing group"
                    )
                else:
                    # No overlap, create hunk for current group and start new group
                    hunk_lines = self._create_consolidated_hunk(
                        current_group, file_lines
                    )
                    if hunk_lines:
                        consolidated_hunks.append(hunk_lines)
                    current_group = [(change, line_num)]

        # Process final group
        if current_group:
            hunk_lines = self._create_consolidated_hunk(current_group, file_lines)
            if hunk_lines:
                consolidated_hunks.append(hunk_lines)

        print(
            f"DEBUG: Created {len(consolidated_hunks)} consolidated hunks from {len(changes_with_targets)} changes"
        )
        return consolidated_hunks

    def _create_consolidated_hunk(
        self, changes_group: List[tuple], file_lines: List[str]
    ) -> List[str]:
        """Create a single hunk containing multiple changes.

        Args:
            changes_group: List of (change_dict, target_line_num) tuples to include in hunk
            file_lines: Current file content

        Returns:
            List of hunk lines, or empty list if creation failed
        """
        if not changes_group:
            return []

        # Determine the overall context range for all changes
        min_line = min(line_num for _, line_num in changes_group)
        max_line = max(line_num for _, line_num in changes_group)

        # Expand context to ensure good patch application (6 lines each side)
        context_start = max(1, min_line - 6)
        context_end = min(len(file_lines), max_line + 6)

        print(
            f"DEBUG: Creating consolidated hunk for lines {min_line}-{max_line}, context {context_start}-{context_end}"
        )

        # Create change mapping for quick lookup
        changes_by_line = {line_num: change for change, line_num in changes_group}

        # Build the hunk header
        old_count = context_end - context_start + 1
        new_count = (
            old_count  # Same count since we're replacing lines, not adding/removing
        )
        hunk_lines = []
        hunk_lines.append(
            f"@@ -{context_start},{old_count} +{context_start},{new_count} @@ "
        )

        # Build the hunk content
        for line_num in range(context_start, context_end + 1):
            if line_num > len(file_lines):
                break

            file_line = file_lines[line_num - 1].rstrip("\n")

            if line_num in changes_by_line:
                # This line should be changed
                change = changes_by_line[line_num]
                new_line = change["new_line"]
                hunk_lines.append(f"-{file_line}")
                hunk_lines.append(f"+{new_line}")
            else:
                # Context line
                hunk_lines.append(f" {file_line}")

        return hunk_lines

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

        # Create context around the target line (6 lines before and after for better resilience)
        context_start = max(1, target_line_num - 6)
        context_end = min(len(file_lines), target_line_num + 6)

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

    def _generate_rebase_todo(self, target_commit: str) -> str:
        """Generate rebase todo list with target commit marked for editing.

        Args:
            target_commit: Commit to mark for editing

        Returns:
            Rebase todo content
        """
        # Check if target commit is reachable from HEAD
        reachable_result = self.git_ops.run_git_command(
            ["merge-base", "--is-ancestor", target_commit, "HEAD"]
        )

        if reachable_result.returncode == 0:
            # Target commit is an ancestor of HEAD - use normal range
            result = self.git_ops.run_git_command(
                ["rev-list", "--reverse", f"{target_commit}^..HEAD"]
            )
        else:
            # Target commit is not in current branch history
            # Find common ancestor and create range from there
            merge_base_result = self.git_ops.run_git_command(
                ["merge-base", target_commit, "HEAD"]
            )

            if merge_base_result.returncode == 0:
                merge_base = merge_base_result.stdout.strip()
                # Get commits from merge base to HEAD that include our target
                result = self.git_ops.run_git_command(
                    ["rev-list", "--reverse", f"{merge_base}..HEAD", target_commit]
                )
            else:
                # No common ancestor found, fallback to simple edit
                return f"edit {target_commit}\n"

        if result.returncode != 0:
            # Fallback to simple edit if rev-list fails
            return f"edit {target_commit}\n"

        commit_list = [
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        ]

        # If no commits found, use simple edit
        if not commit_list:
            return f"edit {target_commit}\n"

        # For now, always use comprehensive approach to avoid losing commits
        # TODO: Implement proper conflict-avoiding strategy that preserves subsequent commits

        # Use comprehensive rebase approach
        print(
            f"DEBUG: Using comprehensive rebase approach for {target_commit[:8]} with {len(commit_list)} commits"
        )
        todo_lines = []
        for commit_hash in commit_list:
            if commit_hash == target_commit:
                todo_lines.append(f"edit {commit_hash}")
            else:
                todo_lines.append(f"pick {commit_hash}")

        return "\n".join(todo_lines) + "\n"

    def _commit_might_conflict_with_target(
        self, commit_hash: str, target_commit: str, target_files: Optional[set] = None
    ) -> bool:
        """Check if a commit might conflict with changes to the target commit.

        Args:
            commit_hash: Commit to check for conflicts
            target_commit: Target commit being modified
            target_files: Set of files being modified in target (optional, will be computed if not provided)

        Returns:
            True if commit might conflict with target modifications
        """
        # Get files modified by the potentially conflicting commit
        result = self.git_ops.run_git_command(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash]
        )

        if result.returncode != 0:
            # If we can't determine files, assume potential conflict for safety
            return True

        commit_files = set(
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        )

        # Get files modified in target commit if not provided
        if target_files is None:
            target_result = self.git_ops.run_git_command(
                ["diff-tree", "--no-commit-id", "--name-only", "-r", target_commit]
            )

            if target_result.returncode != 0:
                # If we can't determine target files, assume potential conflict
                return True

            target_files = set(
                line.strip()
                for line in target_result.stdout.strip().split("\n")
                if line.strip()
            )

        # Check for file overlap - if same files are modified, potential conflict
        file_overlap = commit_files.intersection(target_files)

        if file_overlap:
            print(
                f"DEBUG: Potential conflict detected: commit {commit_hash[:8]} and target {target_commit[:8]} both modify: {', '.join(file_overlap)}"
            )
            return True

        return False

    def _should_use_simple_rebase(self, target_commit: str) -> bool:
        """Determine if we should use simple rebase approach to avoid conflicts.

        Args:
            target_commit: Target commit being modified

        Returns:
            True if simple rebase approach should be used
        """
        # Check if there are subsequent commits that might conflict
        result = self.git_ops.run_git_command(
            ["rev-list", "--reverse", f"{target_commit}^..HEAD"]
        )

        if result.returncode != 0:
            return False

        commit_list = [
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        ]

        # Get target files once for efficiency
        target_result = self.git_ops.run_git_command(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", target_commit]
        )

        if target_result.returncode != 0:
            return False

        target_files = set(
            line.strip()
            for line in target_result.stdout.strip().split("\n")
            if line.strip()
        )

        # Check if any subsequent commits might conflict
        for commit_hash in commit_list:
            if commit_hash != target_commit:
                if self._commit_might_conflict_with_target(
                    commit_hash, target_commit, target_files
                ):
                    print(
                        "DEBUG: Using simple rebase due to potential conflicts with subsequent commits"
                    )
                    return True

        return False

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

        # Create context around the target line (6 lines before and after for better resilience)
        context_start = max(1, target_line_num - 6)
        context_end = min(len(file_lines), target_line_num + 6)

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
        # Clean up any existing rebase state first
        self._cleanup_rebase_state()

        # Create rebase todo that marks target commit for editing and picks all others
        todo_content = self._generate_rebase_todo(target_commit)
        print(f"DEBUG: Generated todo content for {target_commit[:8]}:")
        print(todo_content)

        # Write todo to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(todo_content)
            todo_file = f.name

        try:
            # Set git editor to use our todo file
            env = os.environ.copy()
            env["GIT_SEQUENCE_EDITOR"] = f"cp {todo_file}"

            # Start interactive rebase from target commit to include commits after it
            print(f"DEBUG: Starting rebase with: git rebase -i {target_commit}^")
            result = self.git_ops.run_git_command(
                ["rebase", "-i", f"{target_commit}^"], env=env
            )

            print(f"DEBUG: Rebase command returned: {result.returncode}")
            if result.stdout:
                print(f"DEBUG: Rebase stdout: {result.stdout}")
            if result.stderr:
                print(f"DEBUG: Rebase stderr: {result.stderr}")

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

    def _cleanup_rebase_state(self) -> None:
        """Clean up any existing rebase state that might interfere."""
        # Check if there's an ongoing rebase
        rebase_merge_dir = os.path.join(self.git_ops.repo_path, ".git", "rebase-merge")
        rebase_apply_dir = os.path.join(self.git_ops.repo_path, ".git", "rebase-apply")

        if os.path.exists(rebase_merge_dir) or os.path.exists(rebase_apply_dir):
            print("DEBUG: Found existing rebase state, cleaning up...")
            # Try to abort any existing rebase
            self.git_ops.run_git_command(["rebase", "--abort"])
            print("DEBUG: Cleaned up existing rebase state")

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
            # Apply patch using git apply with fuzzy matching for better context handling
            print(
                f"DEBUG: Running git apply --ignore-whitespace --whitespace=nowarn {patch_file}"
            )
            result = self.git_ops.run_git_command(
                [
                    "apply",
                    "--ignore-whitespace",
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
        """Continue the interactive rebase, handling empty commits."""
        max_retries = 10  # Prevent infinite loops
        retry_count = 0

        while retry_count < max_retries:
            result = self.git_ops.run_git_command(["rebase", "--continue"])
            print(f"DEBUG: git rebase --continue returned: {result.returncode}")
            print(f"DEBUG: git rebase --continue stdout: {result.stdout}")
            print(f"DEBUG: git rebase --continue stderr: {result.stderr}")

            if result.returncode == 0:
                # Rebase completed successfully
                return

            # Check if this is an empty commit that should be skipped
            if (
                "The previous cherry-pick is now empty" in result.stderr
                or "nothing to commit, working tree clean" in result.stderr
            ):
                print("DEBUG: Skipping empty commit during rebase")
                skip_result = self.git_ops.run_git_command(["rebase", "--skip"])
                if skip_result.returncode == 0:
                    # Check if rebase is complete
                    status_result = self.git_ops.run_git_command(
                        ["status", "--porcelain=v1"]
                    )
                    if (
                        status_result.returncode == 0
                        and not self.is_rebase_in_progress()
                    ):
                        return  # Rebase completed
                    retry_count += 1
                    continue
                else:
                    raise subprocess.SubprocessError(
                        f"Failed to skip empty commit: {skip_result.stderr}"
                    )
            else:
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

        raise subprocess.SubprocessError(
            f"Rebase failed after {max_retries} attempts to handle empty commits"
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
        # Check for rebase directories that indicate an active rebase
        rebase_merge_dir = os.path.join(self.git_ops.repo_path, ".git", "rebase-merge")
        rebase_apply_dir = os.path.join(self.git_ops.repo_path, ".git", "rebase-apply")

        if os.path.exists(rebase_merge_dir) or os.path.exists(rebase_apply_dir):
            return True

        # Also check git status output for rebase indicators
        try:
            result = self.git_ops.run_git_command(["status"])
            if result.returncode == 0 and "rebase in progress" in result.stdout:
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
