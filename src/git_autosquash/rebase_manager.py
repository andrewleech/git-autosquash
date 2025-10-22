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
from git_autosquash.squash_context import SquashContext

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
        self._context: Optional[SquashContext] = None

    def execute_squash(
        self,
        mappings: List[HunkTargetMapping],
        ignored_mappings: List[HunkTargetMapping],
        context: SquashContext,
    ) -> bool:
        """Execute the squash operation for approved mappings.

        Args:
            mappings: List of approved hunk to commit mappings
            ignored_mappings: List of ignored hunk to commit mappings
            context: SquashContext for --source commits and blame configuration

        Returns:
            True if successful, False if user aborted

        Raises:
            RebaseConflictError: If conflicts occur during rebase
            subprocess.SubprocessError: If git operations fail
        """
        if not mappings and not ignored_mappings:
            return True

        self._context = context
        self._ignored_mappings = ignored_mappings

        # Store original branch for cleanup
        self._original_branch = self.git_ops.get_current_branch()
        if not self._original_branch:
            raise ValueError("Cannot determine current branch")

        try:
            # Group hunks by target commit
            commit_hunks = self._group_hunks_by_commit(mappings)

            # Build mapping from hunk to source_commit_sha for cherry-pick
            hunk_to_source_commit = {}
            for mapping in mappings:
                if mapping.source_commit_sha:
                    # Use hunk as key (need to find it in commit_hunks)
                    hunk_to_source_commit[id(mapping.hunk)] = mapping.source_commit_sha

            # Check working tree state and handle stashing if needed
            self._handle_working_tree_state()

            # Execute rebase for each target commit
            target_commits = self._get_commit_order(set(commit_hunks.keys()))
            print(
                f"DEBUG: Processing {len(target_commits)} target commits in order: {[c[:8] for c in target_commits]}"
            )

            for target_commit in target_commits:
                hunks = commit_hunks[target_commit]
                # Get source commit SHAs for these hunks
                source_commits = [hunk_to_source_commit.get(id(hunk)) for hunk in hunks]
                print(
                    f"DEBUG: Processing target commit {target_commit[:8]} with {len(hunks)} hunks"
                )
                success = self._apply_hunks_to_commit(
                    target_commit, hunks, source_commits
                )
                if not success:
                    print(f"DEBUG: Failed to apply hunks to commit {target_commit[:8]}")
                    return False
                print(
                    f"DEBUG: Successfully applied hunks to commit {target_commit[:8]}"
                )
                print("=" * 80)

            # Handle source commit if it has ignored hunks
            if hasattr(self, "_source_needs_edit") and self._ignored_mappings:
                print(
                    f"DEBUG: Processing source commit with {len(self._ignored_mappings)} ignored hunks"
                )
                success = self._process_source_with_ignored_hunks(
                    self._source_needs_edit, commit_hunks
                )
                if not success:
                    print(
                        f"DEBUG: Failed to process source commit {self._source_needs_edit[:8]}"
                    )
                    return False
                print(
                    f"DEBUG: Successfully processed source commit {self._source_needs_edit[:8]}"
                )
                print("=" * 80)

            # Restore stash if we created one (success path)
            if self._stash_ref:
                try:
                    success = self._restore_stash_by_sha(self._stash_ref)
                    if not success:
                        logger.error(f"Failed to restore stash: {self._stash_ref[:12]}")
                        logger.info(
                            f"Manual restore: git stash apply {self._stash_ref[:12]}"
                        )
                except Exception as e:
                    logger.error(f"Error restoring stash: {e}")
                    logger.info(
                        f"Manual restore: git stash apply {self._stash_ref[:12]}"
                    )
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
        elif operation_type is not None:
            # Stash returned None but operation_type was set
            # This means status reported changes but there were no actual changes to stash
            # This can happen when processing historical commits with --source
            logger.debug(
                f"No actual changes to stash despite status indicating {operation_type} changes"
            )
            # Continue without stashing - working tree is effectively clean

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
        # For options that require git stash push, we need to use a different approach
        # since git stash create doesn't support --staged or --keep-index

        # First, check if this is a standard creation without special options
        if not options or options == []:
            return self._create_and_store_stash(message)

        # For --staged: we need to temporarily manipulate the working tree
        if "--staged" in options:
            return self._create_staged_only_stash(message)

        # For --keep-index: we need to stash everything then restore index
        if "--keep-index" in options:
            return self._create_keep_index_stash(message)

        # For other unsupported options, use atomic stash create approach
        # This avoids race conditions but may not support all options perfectly
        logger.warning(
            f"Using generic atomic stash for options {options}. "
            f"Some options may not be fully supported."
        )

        # Save current HEAD for reference
        head_result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
        if head_result.returncode != 0:
            logger.error("Failed to get HEAD reference")
            return None
        head_sha = head_result.stdout.strip()

        # Try to create a stash using the atomic approach
        # First, create a temporary commit with all changes
        result = self.git_ops.run_git_command(["add", "-A"])
        if result.returncode != 0:
            logger.error(f"Failed to stage all changes: {result.stderr}")
            return None

        # Create temporary commit
        commit_result = self.git_ops.run_git_command(
            ["commit", "--no-verify", "-m", f"TEMP: {message}"]
        )
        if commit_result.returncode != 0:
            # No changes to stash
            logger.info("No changes to stash")
            return None

        # Get the commit SHA
        temp_commit_result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
        if temp_commit_result.returncode != 0:
            logger.error("Failed to get temporary commit SHA")
            # Reset to original state
            self.git_ops.run_git_command(["reset", "--hard", head_sha])
            return None
        # temp_commit_sha would be used here if we needed it for recovery
        # Currently we just use it to confirm the commit succeeded
        _ = temp_commit_result.stdout.strip()

        # Reset back to original HEAD but keep changes
        reset_result = self.git_ops.run_git_command(["reset", "--mixed", head_sha])
        if reset_result.returncode != 0:
            logger.error(
                f"Failed to reset after temporary commit: {reset_result.stderr}"
            )
            self.git_ops.run_git_command(["reset", "--hard", head_sha])
            return None

        # Now create stash from the temporary commit
        stash_create_result = self.git_ops.run_git_command(["stash", "create", message])
        if (
            stash_create_result.returncode != 0
            or not stash_create_result.stdout.strip()
        ):
            logger.error("Failed to create stash from changes")
            return None

        stash_sha = stash_create_result.stdout.strip()

        # Store the stash
        store_result = self.git_ops.run_git_command(
            ["stash", "store", "-m", message, stash_sha]
        )
        if store_result.returncode != 0:
            logger.warning(f"Failed to store stash in list: {store_result.stderr}")
            # Stash object exists but not in list - still usable

        logger.info(f"Created atomic stash with SHA: {stash_sha[:12]}")
        return stash_sha

    def _create_staged_only_stash(self, message: str) -> Optional[str]:
        """Create a stash containing only staged changes.

        Uses git stash create after manipulating the working tree to isolate staged changes.

        Args:
            message: Stash message

        Returns:
            SHA of created stash, or None if failed
        """
        # Strategy: git stash create doesn't support --staged, so we simulate it
        # 1. Create a temporary commit with staged changes
        # 2. Use git stash create to capture the difference
        # 3. Reset the temporary commit

        # Check if there are staged changes
        status_result = self.git_ops.run_git_command(["diff", "--cached", "--quiet"])
        if status_result.returncode == 0:
            logger.info("No staged changes to stash")
            return None

        # Create a temporary tree object from the index
        tree_result = self.git_ops.run_git_command(["write-tree"])
        if tree_result.returncode != 0:
            logger.error(f"Failed to write tree: {tree_result.stderr}")
            return None

        tree_sha = tree_result.stdout.strip()

        # Create stash commit object
        commit_result = self.git_ops.run_git_command(
            ["commit-tree", tree_sha, "-p", "HEAD", "-m", message]
        )
        if commit_result.returncode != 0:
            logger.error(f"Failed to create commit tree: {commit_result.stderr}")
            return None

        stash_sha = commit_result.stdout.strip()

        # Store in stash list
        store_result = self.git_ops.run_git_command(
            ["stash", "store", "-m", message, stash_sha]
        )
        if store_result.returncode != 0:
            logger.warning(f"Failed to store stash in list: {store_result.stderr}")

        logger.info(f"Created staged-only stash with SHA: {stash_sha}")
        return stash_sha

    def _create_keep_index_stash(self, message: str) -> Optional[str]:
        """Create a stash with --keep-index behavior using SHA references.

        Args:
            message: Stash message

        Returns:
            SHA of created stash, or None if failed
        """
        # Strategy for --keep-index:
        # 1. Save current index state
        # 2. Create stash of all changes
        # 3. Restore index to original state

        # Save index state
        index_tree_result = self.git_ops.run_git_command(["write-tree"])
        if index_tree_result.returncode != 0:
            logger.error(f"Failed to save index state: {index_tree_result.stderr}")
            return None

        index_tree = index_tree_result.stdout.strip()

        # Create stash of all changes (staged + unstaged)
        stash_sha = self._create_and_store_stash(message)
        if not stash_sha:
            return None

        # Restore index to saved state
        restore_result = self.git_ops.run_git_command(["read-tree", index_tree])
        if restore_result.returncode != 0:
            logger.error(f"Failed to restore index: {restore_result.stderr}")
            # The stash was created, but we couldn't restore index
            # This is a partial failure
            return stash_sha

        logger.info(f"Created keep-index stash with SHA: {stash_sha}")
        return stash_sha

    def _validate_stash_sha(self, stash_sha: str) -> bool:
        """Validate that a string is a valid SHA format.

        Args:
            stash_sha: String to validate

        Returns:
            True if valid SHA format, False otherwise
        """
        import re

        if not stash_sha or not isinstance(stash_sha, str):
            return False

        # Git SHA-1 is 40 hexadecimal characters
        # Git SHA-256 is 64 hexadecimal characters (future support)
        sha_pattern = re.compile(r"^[a-f0-9]{40}$|^[a-f0-9]{64}$")
        return bool(sha_pattern.match(stash_sha.lower()))

    def _verify_stash_exists(self, stash_sha: str) -> bool:
        """Verify that a stash SHA exists in the git repository.

        Args:
            stash_sha: SHA of the stash to verify

        Returns:
            True if stash exists and is a valid commit, False otherwise
        """
        if not self._validate_stash_sha(stash_sha):
            logger.error(f"Invalid SHA format: {stash_sha}")
            return False

        # Check if the object exists and is a commit
        result = self.git_ops.run_git_command(["cat-file", "-t", stash_sha])
        if result.returncode != 0:
            logger.error(f"Stash SHA does not exist: {stash_sha}")
            return False

        if result.stdout.strip() != "commit":
            logger.error(
                f"SHA exists but is not a commit: {stash_sha} (type: {result.stdout.strip()})"
            )
            return False

        return True

    def _find_stash_ref_by_sha(self, stash_sha: str) -> Optional[str]:
        """Find stash reference (stash@{n}) for a given SHA.

        Args:
            stash_sha: The SHA to find in stash list

        Returns:
            Stash reference like "stash@{0}" if found, None otherwise
        """
        if not self._validate_stash_sha(stash_sha):
            logger.error(f"Invalid SHA format: {stash_sha}")
            return None

        # List all stashes with their SHAs
        result = self.git_ops.run_git_command(["stash", "list", "--format=%H %gd"])

        if result.returncode != 0:
            logger.error(f"Failed to list stashes: {result.stderr}")
            return None

        # Parse output to find matching SHA
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                sha, ref = parts
                if sha == stash_sha:
                    # Extract stash@{n} from format like "(stash@{0})"
                    if ref.startswith("(") and ref.endswith(")"):
                        ref = ref[1:-1]
                    logger.debug(f"Found stash reference {ref} for SHA {stash_sha}")
                    return ref

        logger.warning(f"No stash reference found for SHA {stash_sha}")
        return None

    def _restore_stash_by_sha(self, stash_sha: str) -> bool:
        """Restore stash using its SHA reference.

        Args:
            stash_sha: SHA of the stash to restore

        Returns:
            True if successful, False otherwise
        """
        # Verify stash exists before attempting to restore
        if not self._verify_stash_exists(stash_sha):
            logger.error(f"Cannot restore stash - invalid or missing: {stash_sha[:12]}")
            return False

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

        # Successfully applied, now drop the stash using proper reference
        logger.info("Stash applied successfully, dropping from list")

        # Find the stash reference (stash@{n}) for this SHA
        stash_ref = self._find_stash_ref_by_sha(stash_sha)
        if stash_ref:
            # Use stash reference for drop command
            drop_result = self.git_ops.run_git_command(["stash", "drop", stash_ref])
            if drop_result.returncode != 0:
                logger.warning(
                    f"Failed to drop stash {stash_ref} (non-critical): {drop_result.stderr}"
                )
            else:
                logger.debug(
                    f"Successfully dropped stash {stash_ref} (SHA: {stash_sha[:12]})"
                )
        else:
            # Stash might have been dropped already or doesn't exist in list
            logger.warning(
                f"Could not find stash reference for SHA {stash_sha[:12]}. "
                "Stash may have been dropped already or created outside stash list."
            )

        return True

    def _apply_hunks_to_commit(
        self,
        target_commit: str,
        hunks: List[DiffHunk],
        source_commits: Optional[List[Optional[str]]] = None,
    ) -> bool:
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
            # Check if we have split commit SHAs (for cherry-pick)
            split_commits = [sc for sc in (source_commits or []) if sc is not None]

            if split_commits:
                # Use cherry-pick with 3-way merge (reliable)
                print(f"DEBUG: Cherry-picking {len(split_commits)} split commits")
                for i, commit_sha in enumerate(split_commits, 1):
                    print(
                        f"DEBUG: Cherry-picking {i}/{len(split_commits)}: {commit_sha[:8]}"
                    )
                    result = self.git_ops.run_git_command(
                        ["cherry-pick", "--no-commit", commit_sha]
                    )
                    if result.returncode != 0:
                        print(f"DEBUG: Cherry-pick failed: {result.stderr}")
                        # Check for conflicts
                        conflicted_files = self._get_conflicted_files()
                        if conflicted_files:
                            raise RebaseConflictError(
                                f"Cherry-pick failed with conflicts: {result.stderr}",
                                conflicted_files,
                            )
                        else:
                            raise subprocess.SubprocessError(
                                f"Cherry-pick failed: {result.stderr}"
                            )
                    print(f"DEBUG: Cherry-pick {i} successful")
                print("DEBUG: All cherry-picks successful")
            else:
                # Fall back to patch-based approach
                print("DEBUG: Creating patch from original hunk text")
                patch_content = self._create_patch_from_original_hunks(hunks)
                print(f"DEBUG: Created patch content ({len(patch_content)} chars):")
                print("=" * 50)
                print(patch_content)
                print("=" * 50)
                self._apply_patch_with_3way(patch_content)
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

    def _extract_hunk_changes(self, hunk: DiffHunk) -> List[Dict[str, Any]]:
        """Extract all changes from a hunk, handling multiple changes per hunk.

        Returns:
            List of change dictionaries with 'old_line', 'new_line', and 'context'
        """
        changes: List[Dict[str, Any]] = []
        current_change: Dict[str, Any] = {}
        context_before: List[str] = []

        for line in hunk.lines:
            if line.startswith("@@"):
                continue
            elif line.startswith(" "):
                # Context line
                context_line = line[1:].rstrip("\n")
                context_before.append(context_line)
                # Keep only last 3 context lines
                if len(context_before) > 3:
                    context_before.pop(0)

                # If we have a pending deletion and hit context, finalize it
                if "old_line" in current_change and "new_line" not in current_change:
                    current_change["is_deletion"] = True
                    changes.append(current_change.copy())
                    current_change = {}
            elif line.startswith("-") and not line.startswith("---"):
                # If we already have a pending deletion, finalize it first
                if "old_line" in current_change and "new_line" not in current_change:
                    current_change["is_deletion"] = True
                    changes.append(current_change.copy())
                    current_change = {}

                current_change["old_line"] = line[1:].rstrip("\n")
                current_change["context_before"] = context_before.copy()
            elif line.startswith("+") and not line.startswith("+++"):
                new_line = line[1:].rstrip("\n")

                if "old_line" in current_change:
                    # Modification: both old and new line
                    current_change["new_line"] = new_line
                    changes.append(current_change.copy())
                    current_change = {}
                else:
                    # Pure addition: only new line, use context to find insertion point
                    changes.append(
                        {
                            "new_line": new_line,
                            "context_before": context_before.copy(),
                            "is_addition": True,
                        }
                    )

        # Finalize any pending deletion at end of hunk
        if "old_line" in current_change and "new_line" not in current_change:
            current_change["is_deletion"] = True
            changes.append(current_change.copy())

        return changes

    def _find_target_with_context(
        self, change: Dict[str, Any], file_lines: List[str], used_lines: Set[int]
    ) -> Optional[int]:
        """Find target line using context awareness to avoid duplicates.

        Args:
            change: Dictionary with 'old_line' and 'new_line' (modifications) or
                   'new_line' and 'context_before' (additions)
            file_lines: Current file content
            used_lines: Set of line numbers already processed

        Returns:
            Target line number (1-based) or None if not found
        """
        # Handle pure additions using context matching
        if change.get("is_addition", False):
            context_before = change.get("context_before", [])
            if not context_before:
                print(
                    "DEBUG: Pure addition without context, cannot determine insertion point"
                )
                return None

            # Find where the context sequence appears in the file
            for i in range(len(file_lines) - len(context_before) + 1):
                # Check if context matches
                matches = True
                for j, ctx_line in enumerate(context_before):
                    file_line = file_lines[i + j].rstrip("\n").strip()
                    if file_line != ctx_line.strip():
                        matches = False
                        break

                if matches:
                    # Insert after the context
                    insertion_line = i + len(context_before) + 1  # 1-based
                    if insertion_line not in used_lines:
                        print(
                            f"DEBUG: Found insertion point for addition at line {insertion_line}"
                        )
                        return insertion_line

            print("DEBUG: Could not find context match for addition")
            return None

        # Handle modifications (existing logic)
        if "old_line" not in change:
            print("DEBUG: Change has neither old_line nor is_addition flag")
            return None

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

        # Multiple candidates
        print(f"DEBUG: Multiple candidates for '{old_line}': {candidates}")
        print(f"DEBUG: Used lines: {sorted(used_lines)}")

        # Use the first unused candidate
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
                    # Handle both additions (with new_line) and modifications/deletions (with old_line)
                    change_preview = change.get("old_line", change.get("new_line", ""))[
                        :50
                    ]
                    print(
                        f"DEBUG: Could not find target for change: {change_preview}..."
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

        # Count additions and deletions to adjust new_count in hunk header
        num_additions = sum(
            1 for change, _ in changes_group if change.get("is_addition", False)
        )
        num_deletions = sum(
            1 for change, _ in changes_group if change.get("is_deletion", False)
        )

        # Build the hunk header
        old_count = context_end - context_start + 1
        new_count = (
            old_count + num_additions - num_deletions
        )  # Adjust for additions and deletions
        hunk_lines = []
        hunk_lines.append(
            f"@@ -{context_start},{old_count} +{context_start},{new_count} @@ "
        )

        # Build the hunk content
        for line_num in range(context_start, context_end + 1):
            if line_num > len(file_lines):
                break

            # Check if we need to insert additions/deletions/modifications at this line
            if line_num in changes_by_line:
                change = changes_by_line[line_num]

                if change.get("is_addition", False):
                    # Pure addition: insert new line before this line
                    new_line = change["new_line"]
                    hunk_lines.append(f"+{new_line}")
                    # Then output the current line as context
                    file_line = file_lines[line_num - 1].rstrip("\n")
                    hunk_lines.append(f" {file_line}")
                elif change.get("is_deletion", False):
                    # Pure deletion: remove this line (only output - line, no + line)
                    file_line = file_lines[line_num - 1].rstrip("\n")
                    hunk_lines.append(f"-{file_line}")
                    # Don't output context line after deletion - the line is being removed
                else:
                    # Modification: replace this line
                    file_line = file_lines[line_num - 1].rstrip("\n")
                    new_line = change["new_line"]
                    hunk_lines.append(f"-{file_line}")
                    hunk_lines.append(f"+{new_line}")
            else:
                # Context line
                file_line = file_lines[line_num - 1].rstrip("\n")
                hunk_lines.append(f" {file_line}")

        return hunk_lines

    def _create_corrected_hunk_for_change(
        self, change: Dict[str, Any], target_line_num: int, file_lines: List[str]
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
        # Get current HEAD commit
        head_result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
        if head_result.returncode != 0:
            return f"edit {target_commit}\n"

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

        # Check if source commit is in the commit list
        # When using --source <commit>, check if there are ignored hunks
        if self._context and self._context.source_commit:
            # Get full SHA of source commit for comparison
            source_result = self.git_ops.run_git_command(
                ["rev-parse", self._context.source_commit]
            )
            if source_result.returncode == 0:
                source_sha = source_result.stdout.strip()
                if source_sha in commit_list:
                    # Check if there are ignored hunks from source
                    has_ignored_hunks = bool(
                        hasattr(self, "_ignored_mappings") and self._ignored_mappings
                    )

                    if has_ignored_hunks:
                        print(
                            f"DEBUG: Source commit {source_sha[:8]} has {len(self._ignored_mappings)} ignored hunks"
                        )
                        print("DEBUG: Preserving source commit to keep ignored changes")
                        # Mark source for special edit handling
                        self._source_needs_edit = source_sha
                    else:
                        print(
                            f"DEBUG: Detected --source commit {source_sha[:8]} in rebase sequence"
                        )
                        print(
                            "DEBUG: Excluding source commit from rebase (all hunks processed)"
                        )
                        # Remove source commit from the list - all its changes were squashed elsewhere
                        commit_list = [c for c in commit_list if c != source_sha]

                        if not commit_list:
                            # Only source commit was in the list, use simple edit
                            return f"edit {target_commit}\n"

        # Use comprehensive rebase approach
        print(
            f"DEBUG: Using comprehensive rebase approach for {target_commit[:8]} with {len(commit_list)} commits"
        )
        todo_lines = []
        for commit_hash in commit_list:
            if commit_hash == target_commit:
                todo_lines.append(f"edit {commit_hash}")
            elif (
                hasattr(self, "_source_needs_edit")
                and commit_hash == self._source_needs_edit
            ):
                todo_lines.append(f"edit {commit_hash}")  # Source needs editing
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
        # Check if rebase is already in progress
        if self.is_rebase_in_progress():
            print(
                "DEBUG: Rebase already in progress - completing it before starting new one"
            )
            # Complete the existing rebase by continuing through all edit points
            try:
                self._complete_remaining_rebase()
            except Exception as e:
                print(f"DEBUG: Failed to complete existing rebase: {e}")
                # Clean up the failed rebase state
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

    def _complete_remaining_rebase(self) -> None:
        """Complete remaining edit points in an active rebase without making changes.

        This is used when we need to finish a rebase that has edit points we don't
        need to handle (e.g., source commit edit points that will be handled later).
        """
        max_iterations = 20  # Prevent infinite loops
        iteration = 0

        while self.is_rebase_in_progress() and iteration < max_iterations:
            iteration += 1
            print(f"DEBUG: Completing rebase iteration {iteration}")

            # Just continue without making any changes
            result = self.git_ops.run_git_command(["rebase", "--continue"])

            if result.returncode != 0:
                # Check if it's an empty commit
                if "nothing to commit" in result.stderr:
                    print("DEBUG: Skipping empty commit")
                    self.git_ops.run_git_command(["rebase", "--skip"])
                else:
                    # Some other error - re-raise
                    raise subprocess.SubprocessError(
                        f"Failed to complete rebase: {result.stderr}"
                    )

        if iteration >= max_iterations:
            raise subprocess.SubprocessError(
                "Failed to complete rebase after maximum iterations"
            )

        print("DEBUG: Completed remaining rebase successfully")

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

    def _create_patch_from_original_hunks(self, hunks: List[DiffHunk]) -> str:
        """Create a patch using the ORIGINAL hunk text from git (not reconstructed).

        This preserves the exact hunk text extracted by HunkParser from 'git show',
        avoiding manual reconstruction bugs. Git will handle any line number
        differences with --3way and --recount.

        Args:
            hunks: List of hunks with original text from git

        Returns:
            Patch content string
        """
        patch_lines = []
        current_file = None

        for hunk in hunks:
            # Add file header if this is a new file
            if hunk.file_path != current_file:
                current_file = hunk.file_path
                patch_lines.extend(
                    [f"--- a/{hunk.file_path}", f"+++ b/{hunk.file_path}"]
                )

            # Add ORIGINAL hunk lines from git (not reconstructed)
            patch_lines.extend(hunk.lines)

        return "\n".join(patch_lines) + "\n"

    def _apply_patch_with_3way(self, patch_content: str) -> None:
        """Apply patch using git's 3-way merge and fuzzy matching.

        Uses git apply --3way --recount to let git handle:
        - Line number differences (--recount)
        - Context mismatches (--3way merge)
        - Explicit conflict reporting (not silent corruption)

        Args:
            patch_content: Patch content to apply

        Raises:
            RebaseConflictError: If patch application fails with conflicts
            subprocess.SubprocessError: If patch application fails
        """
        # Write patch to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
            f.write(patch_content)
            patch_file = f.name
            print(f"DEBUG: Wrote patch to temporary file: {patch_file}")

        try:
            # Apply patch with 3-way merge and automatic line number recalculation
            print(f"DEBUG: Running git apply --3way --recount {patch_file}")
            result = self.git_ops.run_git_command(
                [
                    "apply",
                    "--3way",
                    "--recount",
                    patch_file,
                ]
            )
            print(f"DEBUG: git apply returned code: {result.returncode}")
            if result.stdout:
                print(f"DEBUG: git apply stdout: {result.stdout}")
            # Only show stderr if there was an error (returncode != 0)
            # Success can still have warnings about 3-way fallback which are noise
            if result.returncode != 0 and result.stderr:
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

    def _apply_patch(self, patch_content: str) -> None:
        """Apply patch content to working directory (LEGACY - use _apply_patch_with_3way).

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
        """Amend the current commit with changes, handling pre-commit hook modifications and empty commits."""
        # Stage all changes
        result = self.git_ops.run_git_command(["add", "."])
        if result.returncode != 0:
            raise subprocess.SubprocessError(
                f"Failed to stage changes: {result.stderr}"
            )

        # Attempt to amend commit (keep original message)
        result = self.git_ops.run_git_command(["commit", "--amend", "--no-edit"])
        if result.returncode != 0:
            # Check if the failure was due to empty commit
            if "would make" in result.stderr and "empty" in result.stderr:
                print("DEBUG: Amend would create empty commit, using --allow-empty")
                # Allow empty commit - this happens when changes cancel out the original
                retry_result = self.git_ops.run_git_command(
                    ["commit", "--amend", "--no-edit", "--allow-empty"]
                )
                if retry_result.returncode != 0:
                    raise subprocess.SubprocessError(
                        f"Failed to amend empty commit: {retry_result.stderr}"
                    )
                print("DEBUG: Successfully amended with --allow-empty")
            # Check if the failure was due to pre-commit hook modifications
            elif "files were modified by this hook" in result.stderr:
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
                # Check if rebase is actually complete or just stopped at next edit point
                if not self.is_rebase_in_progress():
                    # Rebase completed successfully
                    print("DEBUG: Rebase completed successfully")
                    return
                else:
                    # Rebase stopped at next edit point - need to continue through remaining edits
                    print(
                        "DEBUG: Rebase stopped at next edit point, continuing through remaining edits"
                    )
                    # Continue through any remaining edit points automatically
                    retry_count += 1
                    continue

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
                success = self._restore_stash_by_sha(self._stash_ref)
                if not success:
                    logger.warning(
                        f"Failed to restore stash during cleanup: {self._stash_ref[:12]}"
                    )
            except Exception as e:
                # Stash restoration failed, but don't raise - user can manually recover
                logger.warning(f"Error restoring stash during cleanup: {e}")
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

    def _process_source_with_ignored_hunks(
        self, source_commit: str, approved_hunks_by_target: Dict[str, List[DiffHunk]]
    ) -> bool:
        """Process source commit by removing approved hunks, keeping only ignored hunks.

        This is called when using --source with hunks that require manual selection.
        Instead of losing those hunks, we preserve them in the source commit at its
        original position.

        Args:
            source_commit: The source commit SHA to process
            approved_hunks_by_target: Dict mapping target commits to their approved hunks

        Returns:
            True if successful, False otherwise
        """
        print(f"DEBUG: Processing source commit {source_commit[:8]} with ignored hunks")

        # Get split commit SHAs for ignored hunks from the ignored mappings
        ignored_split_commits = []
        if hasattr(self, "_ignored_mappings"):
            for mapping in self._ignored_mappings:
                if mapping.source_commit_sha:
                    ignored_split_commits.append(mapping.source_commit_sha)
                    print(
                        f"DEBUG: Found ignored split commit: {mapping.source_commit_sha[:8]}"
                    )

        if not ignored_split_commits:
            print(
                "DEBUG: No ignored split commits found, source commit will be removed"
            )
            # Remove the source commit entirely (all hunks were squashed)
            result = self.git_ops.run_git_command(["rebase", "--skip"])
            if result.returncode != 0:
                print(f"DEBUG: Failed to skip source commit: {result.stderr}")
                return False
            return True

        print(
            f"DEBUG: Keeping {len(ignored_split_commits)} ignored hunks in source commit"
        )
        print("DEBUG: Ignored hunks are available in split commits:")
        for i, commit_sha in enumerate(ignored_split_commits, 1):
            print(f"DEBUG:   {i}. {commit_sha[:8]}")

        print(f"DEBUG: Source commit {source_commit[:8]} left unchanged")
        print(
            "DEBUG: To apply ignored hunks manually, cherry-pick the split commits above"
        )

        # Ignored hunks remain in split commits for manual review
        # This is safer than automatically modifying the source commit after rebases
        return True

    def _hunk_id(self, hunk: DiffHunk) -> str:
        """Create unique ID for hunk based on file, line range, and first line of content.

        Args:
            hunk: The hunk to create ID for

        Returns:
            Unique string identifier for the hunk
        """
        # Construct header from line numbers
        header = f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"

        # Use file path, line numbers, and first line of actual changes
        first_change = next(
            (
                line
                for line in hunk.lines
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
            ),
            "",
        )
        return f"{hunk.file_path}:{header}:{first_change[:50]}"

    def _get_hunks_from_commit(self, commit: str) -> List[DiffHunk]:
        """Get all hunks from a commit.

        Args:
            commit: Commit SHA to get hunks from

        Returns:
            List of DiffHunk objects
        """
        from git_autosquash.hunk_parser import HunkParser

        parser = HunkParser(self.git_ops)
        return parser.get_diff_hunks(line_by_line=False, from_commit=commit)

    def _get_commit_message(self, commit: str) -> str:
        """Get commit message (excluding headers like commit SHA, author, etc).

        Args:
            commit: Commit SHA

        Returns:
            Commit message body
        """
        result = self.git_ops.run_git_command(["log", "-1", "--format=%B", commit])
        if result.returncode != 0:
            return "Unknown commit message"
        return result.stdout.strip()

    def _amend_commit_with_message(self, message: str) -> None:
        """Amend current commit with new message.

        Args:
            message: New commit message

        Raises:
            subprocess.SubprocessError: If amend fails
        """
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write(message)
            msg_file = f.name

        try:
            # Stage all changes
            result = self.git_ops.run_git_command(["add", "-A"])
            if result.returncode != 0:
                raise subprocess.SubprocessError(f"Failed to stage: {result.stderr}")

            # Amend with message file
            result = self.git_ops.run_git_command(["commit", "--amend", "-F", msg_file])
            if result.returncode != 0:
                raise subprocess.SubprocessError(
                    f"Failed to amend commit: {result.stderr}"
                )
        finally:
            try:
                os.unlink(msg_file)
            except OSError:
                pass
