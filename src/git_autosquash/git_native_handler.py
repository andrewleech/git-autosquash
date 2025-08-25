"""Git-native handler for ignore functionality using hybrid stash approach."""

import logging
from pathlib import Path
from typing import List, Optional

from git_autosquash.hunk_target_resolver import HunkTargetMapping
from git_autosquash.git_ops import GitOps


class GitNativeIgnoreHandler:
    """Enhanced ignore handler using git native operations for backup/restore.

    This implementation combines the reliability of git's native stash operations
    for backup and restore with precise patch application for hunk-level control.
    """

    def __init__(self, git_ops: GitOps) -> None:
        """Initialize the git-native handler.

        Args:
            git_ops: GitOps instance for git command execution
        """
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)

    def apply_ignored_hunks(self, ignored_mappings: List[HunkTargetMapping]) -> bool:
        """Apply ignored hunks with native git backup/restore.

        Uses a hybrid approach:
        1. Native git stash for comprehensive backup
        2. Proven patch application for precise hunk control
        3. Atomic native restore on any failure

        Args:
            ignored_mappings: List of ignored hunk to commit mappings

        Returns:
            True if successful, False if any hunks could not be applied
        """
        if not ignored_mappings:
            self.logger.info("No ignored hunks to apply")
            return True

        self.logger.info(
            f"Applying {len(ignored_mappings)} ignored hunks with git-native backup"
        )

        # Phase 1: Create comprehensive native backup
        backup_stash = self._create_comprehensive_backup()
        if not backup_stash:
            self.logger.error("Failed to create backup stash")
            return False

        try:
            # Phase 2: Validate file paths for security
            if not self._validate_file_paths(ignored_mappings):
                self.logger.error("Path validation failed")
                return False

            # Phase 3: Apply patches with existing proven logic
            success = self._apply_patches_with_validation(ignored_mappings)

            if success:
                self.logger.info(
                    "✓ Ignored hunks successfully restored to working tree"
                )
                return True
            else:
                self.logger.warning("Patch application failed, initiating restore")
                self._restore_from_stash(backup_stash)
                return False

        except Exception as e:
            # Phase 4: Atomic native restore on any failure
            self.logger.error(f"Exception during patch application: {e}")
            self._restore_from_stash(backup_stash)
            return False

        finally:
            # Phase 5: Clean up backup stash
            self._cleanup_stash(backup_stash)

    def _create_comprehensive_backup(self) -> Optional[str]:
        """Create comprehensive stash backup including untracked files.

        Returns:
            Stash reference if successful, None if failed
        """
        self.logger.debug("Creating comprehensive backup stash")

        success, stash_output = self.git_ops._run_git_command(
            "stash",
            "push",
            "--include-untracked",
            "--message",
            "git-autosquash-comprehensive-backup",
        )

        if success:
            # Extract stash reference - typically "stash@{0}" after creation
            stash_ref = "stash@{0}"
            self.logger.debug(f"Created backup stash: {stash_ref}")
            return stash_ref
        else:
            self.logger.error(f"Failed to create backup stash: {stash_output}")
            return None

    def _validate_file_paths(self, ignored_mappings: List[HunkTargetMapping]) -> bool:
        """Enhanced path validation to prevent security issues.

        Args:
            ignored_mappings: List of mappings to validate

        Returns:
            True if all paths are safe, False otherwise
        """
        try:
            repo_root = Path(self.git_ops.repo_path).resolve()

            for mapping in ignored_mappings:
                file_path = Path(mapping.hunk.file_path)

                # Reject absolute paths
                if file_path.is_absolute():
                    self.logger.error(
                        f"Absolute file path not allowed: {mapping.hunk.file_path}"
                    )
                    return False

                # Check for path traversal by resolving against repo root
                resolved_path = (repo_root / file_path).resolve()
                try:
                    resolved_path.relative_to(repo_root)
                except ValueError:
                    self.logger.error(
                        f"Path traversal detected: {mapping.hunk.file_path}"
                    )
                    return False

            self.logger.debug("All file paths validated successfully")
            return True

        except Exception as e:
            self.logger.error(f"Path validation failed: {e}")
            return False

    def _apply_patches_with_validation(
        self, ignored_mappings: List[HunkTargetMapping]
    ) -> bool:
        """Apply patches using git index manipulation for precise control.

        This enhanced approach uses git's native index operations:
        1. Stage specific hunks to the index
        2. Generate patch using git diff --cached
        3. Reset index and apply patch to working tree
        4. Provides better validation and error handling

        Args:
            ignored_mappings: List of mappings to apply

        Returns:
            True if all patches applied successfully, False otherwise
        """
        return self._apply_patches_via_index(ignored_mappings)

    def _apply_patches_via_index(
        self, ignored_mappings: List[HunkTargetMapping]
    ) -> bool:
        """Apply patches using git index manipulation for precise control.

        This method leverages git's native index operations:
        1. Create temporary patches for each hunk
        2. Stage hunks individually to the index
        3. Generate final patch using git diff --cached
        4. Reset index and apply to working tree

        Args:
            ignored_mappings: List of mappings to apply

        Returns:
            True if all patches applied successfully, False otherwise
        """
        try:
            # Store original index state
            success, original_index = self._capture_index_state()
            if not success:
                self.logger.error("Failed to capture original index state")
                return False

            try:
                # Apply each hunk to index individually for validation
                for mapping in ignored_mappings:
                    if not self._stage_hunk_to_index(mapping.hunk):
                        self.logger.error(
                            f"Failed to stage hunk for {mapping.hunk.file_path}"
                        )
                        return False

                # Generate patch from staged changes
                patch_content = self._generate_patch_from_index()
                if not patch_content:
                    self.logger.error("Failed to generate patch from staged changes")
                    return False

                # Reset index to original state
                self._restore_index_state(original_index)

                # Apply patch to working tree using git apply
                success, error_msg = self.git_ops._run_git_command_with_input(
                    "apply", "--check", input_text=patch_content
                )

                if not success:
                    self.logger.error(f"Patch validation failed: {error_msg}")
                    return False

                success, error_msg = self.git_ops._run_git_command_with_input(
                    "apply", input_text=patch_content
                )

                if success:
                    self.logger.debug("Git-native patch application successful")
                    return True
                else:
                    self.logger.error(
                        f"Git-native patch application failed: {error_msg}"
                    )
                    return False

            except Exception as e:
                self.logger.error(f"Error during index-based patch application: {e}")
                # Ensure index is restored on any error
                self._restore_index_state(original_index)
                return False

        except Exception as e:
            self.logger.error(f"Failed to apply patches via index: {e}")
            return False

    def _capture_index_state(self) -> tuple[bool, str]:
        """Capture the current git index state for restoration.

        Returns:
            Tuple of (success, index_hash) where index_hash can be used to restore
        """
        try:
            # Get current index tree hash
            success, tree_hash = self.git_ops._run_git_command("write-tree")
            if success:
                return True, tree_hash.strip()
            else:
                self.logger.error("Failed to capture index tree state")
                return False, ""
        except Exception as e:
            self.logger.error(f"Error capturing index state: {e}")
            return False, ""

    def _restore_index_state(self, tree_hash: str) -> bool:
        """Restore git index to a previous state.

        Args:
            tree_hash: Tree hash to restore index to

        Returns:
            True if restoration successful
        """
        try:
            if not tree_hash:
                return False

            success, _ = self.git_ops._run_git_command("read-tree", tree_hash)
            if success:
                self.logger.debug(f"Index restored to tree {tree_hash[:8]}")
                return True
            else:
                self.logger.error(f"Failed to restore index to tree {tree_hash}")
                return False
        except Exception as e:
            self.logger.error(f"Error restoring index state: {e}")
            return False

    def _stage_hunk_to_index(self, hunk) -> bool:
        """Stage a specific hunk to the git index using patch application.

        Args:
            hunk: DiffHunk object to stage

        Returns:
            True if hunk was staged successfully
        """
        try:
            # Create a minimal patch for this single hunk
            hunk_patch = self._create_minimal_patch_for_hunk(hunk)
            if not hunk_patch:
                return False

            # Apply patch to index only (--cached)
            success, error_msg = self.git_ops._run_git_command_with_input(
                "apply", "--cached", input_text=hunk_patch
            )

            if success:
                self.logger.debug(f"Staged hunk for {hunk.file_path} to index")
                return True
            else:
                self.logger.warning(
                    f"Failed to stage hunk for {hunk.file_path}: {error_msg}"
                )
                return False

        except Exception as e:
            self.logger.error(f"Error staging hunk to index: {e}")
            return False

    def _create_minimal_patch_for_hunk(self, hunk) -> Optional[str]:
        """Create a minimal git patch for a single hunk.

        Args:
            hunk: DiffHunk object to create patch for

        Returns:
            Patch content string, or None if creation failed
        """
        try:
            # Get blob info for proper headers
            blob_info = self._get_file_blob_info(hunk.file_path)

            # Build minimal patch
            patch_lines = [
                f"diff --git a/{hunk.file_path} b/{hunk.file_path}",
                f"index {blob_info['old_hash']}..{blob_info['new_hash']} {blob_info['mode']}",
                f"--- a/{hunk.file_path}",
                f"+++ b/{hunk.file_path}",
            ]

            # Add hunk content
            patch_lines.extend(hunk.lines)

            return "\n".join(patch_lines) + "\n"

        except Exception as e:
            self.logger.error(f"Failed to create minimal patch for hunk: {e}")
            return None

    def _generate_patch_from_index(self) -> Optional[str]:
        """Generate a patch from currently staged changes using git diff --cached.

        Returns:
            Patch content, or None if generation failed
        """
        try:
            success, patch_content = self.git_ops._run_git_command("diff", "--cached")

            if success and patch_content.strip():
                self.logger.debug(
                    f"Generated patch from index ({len(patch_content)} bytes)"
                )
                return patch_content
            else:
                self.logger.warning("No staged changes found to generate patch")
                return None

        except Exception as e:
            self.logger.error(f"Failed to generate patch from index: {e}")
            return None

    def _get_file_blob_info(self, file_path: str) -> dict:
        """Get git blob information for proper patch headers.

        Args:
            file_path: Path to file

        Returns:
            Dictionary with old_hash, new_hash, and mode
        """
        try:
            # Get current file hash
            success, current_hash = self.git_ops._run_git_command(
                "hash-object", file_path
            )

            # Get HEAD version hash
            success_head, head_hash = self.git_ops._run_git_command(
                "rev-parse", f"HEAD:{file_path}"
            )

            # Get file mode
            success_mode, mode_info = self.git_ops._run_git_command(
                "ls-files", "--stage", file_path
            )

            if success and success_mode:
                # Extract mode from ls-files output (format: mode hash stage filename)
                mode = mode_info.split()[0] if mode_info else "100644"
                return {
                    "old_hash": head_hash.strip() if success_head else "0" * 40,
                    "new_hash": current_hash.strip(),
                    "mode": mode,
                }
            else:
                # Fallback to placeholder values
                return {"old_hash": "0" * 40, "new_hash": "1" * 40, "mode": "100644"}

        except Exception as e:
            self.logger.warning(f"Could not get blob info for {file_path}: {e}")
            return {"old_hash": "0" * 40, "new_hash": "1" * 40, "mode": "100644"}

    def _restore_from_stash(self, stash_ref: str) -> bool:
        """Atomically restore working tree from stash.

        Args:
            stash_ref: Stash reference to restore from

        Returns:
            True if restore succeeded, False otherwise
        """
        self.logger.info(f"Restoring working tree from stash: {stash_ref}")

        success, output = self.git_ops._run_git_command("stash", "pop", stash_ref)

        if success:
            self.logger.info("✓ Working tree restored from backup")
            return True
        else:
            self.logger.error(f"Failed to restore from stash: {output}")
            # Try alternative restore method
            return self._force_restore_from_stash(stash_ref)

    def _force_restore_from_stash(self, stash_ref: str) -> bool:
        """Force restore using checkout method as fallback.

        Args:
            stash_ref: Stash reference to restore from

        Returns:
            True if force restore succeeded, False otherwise
        """
        self.logger.warning("Attempting force restore using checkout method")

        # Reset working tree to clean state first
        success, _ = self.git_ops._run_git_command("reset", "--hard", "HEAD")
        if not success:
            self.logger.error("Failed to reset working tree")
            return False

        # Apply stash changes using checkout
        success, output = self.git_ops._run_git_command(
            "checkout", stash_ref, "--", "."
        )

        if success:
            self.logger.info("✓ Force restore completed")
            return True
        else:
            self.logger.error(f"Force restore failed: {output}")
            return False

    def _cleanup_stash(self, stash_ref: str) -> None:
        """Clean up backup stash.

        Args:
            stash_ref: Stash reference to clean up
        """
        self.logger.debug(f"Cleaning up backup stash: {stash_ref}")

        success, output = self.git_ops._run_git_command("stash", "drop", stash_ref)

        if success:
            self.logger.debug("✓ Backup stash cleaned up")
        else:
            self.logger.warning(f"Failed to clean up stash {stash_ref}: {output}")
            self.logger.warning("Stash may need manual cleanup with: git stash drop")

    def get_stash_info(self) -> List[dict]:
        """Get information about current stashes for debugging.

        Returns:
            List of dictionaries with stash information
        """
        success, output = self.git_ops._run_git_command("stash", "list")

        if not success:
            return []

        stashes = []
        for line in output.split("\n"):
            if line.strip():
                # Parse stash line format: stash@{0}: WIP on branch: message
                parts = line.split(": ", 2)
                if len(parts) >= 3:
                    stashes.append(
                        {"ref": parts[0], "type": parts[1], "message": parts[2]}
                    )

        return stashes
