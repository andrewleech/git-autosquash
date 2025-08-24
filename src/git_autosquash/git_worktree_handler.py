"""Git worktree-based handler for ignore functionality with complete isolation."""

import logging
import tempfile
from pathlib import Path
from typing import List, Optional

from git_autosquash.blame_analyzer import HunkTargetMapping
from git_autosquash.git_ops import GitOps
from git_autosquash.result import StrategyResult, StrategyExecutionError, Ok, Err
from git_autosquash.resource_managers import git_state_context, worktree_context


class GitWorktreeIgnoreHandler:
    """Enhanced ignore handler using git worktree for complete isolation.

    This implementation provides:
    - Complete isolation from main repository state
    - Simplified error handling via atomic worktree cleanup
    - Foundation for potential parallel processing
    - More natural git operations (direct file application)
    """

    def __init__(self, git_ops: GitOps) -> None:
        """Initialize the git worktree handler.

        Args:
            git_ops: GitOps instance for git command execution
        """
        self.git_ops = git_ops
        self.logger = logging.getLogger(__name__)

    def apply_ignored_hunks_enhanced(
        self, ignored_mappings: List[HunkTargetMapping]
    ) -> StrategyResult[int]:
        """Enhanced version using Result pattern and resource managers.

        This method demonstrates the improved error handling and resource management
        patterns suggested by the principal code reviewer.

        Args:
            ignored_mappings: List of ignored hunk to commit mappings

        Returns:
            Result containing number of successfully applied hunks or error details
        """
        if not ignored_mappings:
            self.logger.info("No ignored hunks to apply")
            return Ok(0)

        self.logger.info(
            f"Applying {len(ignored_mappings)} ignored hunks with enhanced worktree isolation"
        )

        try:
            with git_state_context(self.git_ops) as state_mgr:
                # Save current state
                backup_result = state_mgr.save_current_state()
                if backup_result.is_err():
                    return Err(
                        StrategyExecutionError(
                            strategy="worktree_enhanced",
                            operation="backup_state",
                            message="Failed to create backup",
                            underlying_error=Exception(str(backup_result.unwrap_err())),
                        )
                    )

                try:
                    with worktree_context(self.git_ops) as worktree_path:
                        # Apply hunks in isolated worktree
                        result = self._apply_hunks_in_worktree_enhanced(
                            ignored_mappings, worktree_path
                        )
                        if result.is_err():
                            return result.map_err(
                                lambda e: StrategyExecutionError(
                                    strategy="worktree_enhanced",
                                    operation="apply_hunks",
                                    message="Failed to apply hunks in worktree",
                                    underlying_error=Exception(str(e)) if not isinstance(e, Exception) else e,
                                )
                            )

                        applied_count = result.unwrap()

                        # Extract changes back to main repository
                        extract_result = self._extract_changes_enhanced(worktree_path)
                        if extract_result.is_err():
                            return Err(StrategyExecutionError(
                                strategy="worktree_enhanced",
                                operation="extract_changes",
                                message="Failed to extract changes from worktree",
                                underlying_error=Exception(str(extract_result.unwrap_err())),
                            ))

                        self.logger.info(
                            f"✓ Successfully applied {applied_count} hunks using enhanced worktree strategy"
                        )
                        return Ok(applied_count)

                except Exception as e:
                    return Err(
                        StrategyExecutionError(
                            strategy="worktree_enhanced",
                            operation="worktree_operations",
                            message="Worktree operations failed",
                            underlying_error=e,
                        )
                    )

        except Exception as e:
            return Err(
                StrategyExecutionError(
                    strategy="worktree_enhanced",
                    operation="resource_management",
                    message="Resource management failed",
                    underlying_error=e,
                )
            )

    def _apply_hunks_in_worktree_enhanced(
        self, ignored_mappings: List[HunkTargetMapping], worktree_path: Path
    ) -> StrategyResult[int]:
        """Apply hunks in worktree using enhanced error handling."""
        applied_count = 0

        for mapping in ignored_mappings:
            try:
                # Create patch for this hunk
                patch_content = self._create_minimal_patch_for_hunk(
                    mapping.hunk, self.git_ops
                )
                if not patch_content:
                    self.logger.warning(
                        f"Failed to create patch for hunk in {mapping.hunk.file_path}"
                    )
                    continue

                # Apply patch in worktree
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".patch", delete=False
                ) as patch_file:
                    patch_file.write(patch_content)
                    patch_file.flush()

                    # Apply patch in the worktree directory
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".sh", delete=False
                    ) as script_file:
                        script_file.write(f'''#!/bin/bash
cd "{worktree_path}"
git apply "{patch_file.name}"
''')
                        script_file.flush()
                        Path(script_file.name).chmod(0o755)

                        success, output = self.git_ops._run_git_command(
                            "sh", script_file.name
                        )
                        Path(script_file.name).unlink()  # Clean up script file

                    Path(patch_file.name).unlink()  # Clean up patch file

                    if success:
                        applied_count += 1
                        self.logger.debug(f"Applied hunk for {mapping.hunk.file_path}")
                    else:
                        self.logger.warning(
                            f"Failed to apply hunk for {mapping.hunk.file_path}: {output}"
                        )

            except Exception as e:
                self.logger.warning(
                    f"Exception applying hunk for {mapping.hunk.file_path}: {e}"
                )
                continue

        return Ok(applied_count)

    def _extract_changes_enhanced(self, worktree_path: Path) -> StrategyResult[bool]:
        """Extract changes from worktree back to main repository."""
        try:
            # Get diff from worktree directory
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sh", delete=False
            ) as script_file:
                script_file.write(f'''#!/bin/bash
cd "{worktree_path}"
git diff HEAD
''')
                script_file.flush()
                Path(script_file.name).chmod(0o755)

                success, diff_output = self.git_ops._run_git_command(
                    "sh", script_file.name
                )
                Path(script_file.name).unlink()  # Clean up script file

            if not success:
                return Err(
                    StrategyExecutionError(
                        strategy="worktree_enhanced",
                        operation="get_worktree_diff",
                        message="Failed to get diff from worktree",
                    )
                )

            if not diff_output.strip():
                self.logger.info("No changes to extract from worktree")
                return Ok(True)

            # Apply diff to main repository
            success, apply_output = self.git_ops._run_git_command_with_input(
                "apply", input_text=diff_output
            )

            if success:
                self.logger.debug("Successfully extracted changes from worktree")
                return Ok(True)
            else:
                return Err(
                    StrategyExecutionError(
                        strategy="worktree_enhanced",
                        operation="apply_extracted_diff",
                        message=f"Failed to apply extracted diff: {apply_output}",
                    )
                )

        except Exception as e:
            return Err(
                StrategyExecutionError(
                    strategy="worktree_enhanced",
                    operation="extract_changes",
                    message="Exception during change extraction",
                    underlying_error=e,
                )
            )

    def apply_ignored_hunks(self, ignored_mappings: List[HunkTargetMapping]) -> bool:
        """Apply ignored hunks using isolated git worktree.

        Uses complete isolation approach:
        1. Create comprehensive stash backup
        2. Create temporary isolated worktree
        3. Apply hunks directly in worktree (no index manipulation)
        4. Extract changes back to main working tree
        5. Atomic cleanup of all temporary state

        Args:
            ignored_mappings: List of ignored hunk to commit mappings

        Returns:
            True if successful, False if any hunks could not be applied
        """
        if not ignored_mappings:
            self.logger.info("No ignored hunks to apply")
            return True

        self.logger.info(
            f"Applying {len(ignored_mappings)} ignored hunks with git worktree isolation"
        )

        # Check worktree support
        if not self._check_worktree_support():
            self.logger.warning("Git worktree not supported, cannot proceed")
            return False

        # Phase 1: Create comprehensive native backup
        backup_stash = self._create_comprehensive_backup()
        if not backup_stash:
            self.logger.error("Failed to create backup stash")
            return False

        worktree_path = None
        try:
            # Phase 2: Validate file paths for security
            if not self._validate_file_paths(ignored_mappings):
                self.logger.error("Path validation failed")
                return False

            # Phase 3: Create temporary isolated worktree
            worktree_path = self._create_temporary_worktree()
            if not worktree_path:
                self.logger.error("Failed to create temporary worktree")
                return False

            # Phase 4: Apply hunks in isolated environment
            success = self._apply_hunks_in_worktree(ignored_mappings, worktree_path)

            if success:
                # Phase 5: Extract changes back to main working tree
                success = self._extract_changes_from_worktree(worktree_path)

            if success:
                self.logger.info("✓ Ignored hunks successfully applied via worktree")
                return True
            else:
                self.logger.warning("Worktree processing failed, initiating restore")
                self._restore_from_stash(backup_stash)
                return False

        except Exception as e:
            # Phase 6: Atomic restore on any failure
            self.logger.error(f"Exception during worktree processing: {e}")
            self._restore_from_stash(backup_stash)
            return False

        finally:
            # Phase 7: Clean up worktree and backup
            if worktree_path:
                self._cleanup_worktree(worktree_path)
            self._cleanup_stash(backup_stash)

    def _check_worktree_support(self) -> bool:
        """Check if git worktree is supported in this repository.

        Returns:
            True if worktree commands are available
        """
        try:
            success, output = self.git_ops._run_git_command("worktree", "--help")
            supported = success and "add" in output.lower()

            if supported:
                self.logger.debug("Git worktree support confirmed")
            else:
                self.logger.warning("Git worktree not supported or available")

            return supported

        except Exception as e:
            self.logger.error(f"Failed to check worktree support: {e}")
            return False

    def _create_temporary_worktree(self) -> Optional[str]:
        """Create temporary worktree for isolated hunk processing.

        Returns:
            Path to temporary worktree, or None if creation failed
        """
        try:
            # Create secure temporary directory
            temp_dir = tempfile.mkdtemp(prefix="git-autosquash-", suffix="-worktree")

            # Create detached worktree at current HEAD
            success, output = self.git_ops._run_git_command(
                "worktree", "add", "--detach", temp_dir, "HEAD"
            )

            if success:
                self.logger.debug(f"Created temporary worktree at: {temp_dir}")
                return temp_dir
            else:
                self.logger.error(f"Failed to create worktree: {output}")
                # Clean up temp directory if worktree creation failed
                try:
                    import shutil

                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass
                return None

        except Exception as e:
            self.logger.error(f"Exception creating temporary worktree: {e}")
            return None

    def _apply_hunks_in_worktree(
        self, ignored_mappings: List[HunkTargetMapping], worktree_path: str
    ) -> bool:
        """Apply hunks within isolated worktree environment.

        Args:
            ignored_mappings: List of mappings to apply
            worktree_path: Path to isolated worktree

        Returns:
            True if all hunks applied successfully
        """
        try:
            # Create GitOps instance for the worktree
            worktree_git_ops = GitOps(Path(worktree_path))

            # Apply each hunk directly to worktree files (no staging needed)
            for mapping in ignored_mappings:
                if not self._apply_single_hunk_in_worktree(mapping, worktree_git_ops):
                    self.logger.error(
                        f"Failed to apply hunk for {mapping.hunk.file_path}"
                    )
                    return False

            self.logger.debug(
                f"Successfully applied {len(ignored_mappings)} hunks in worktree"
            )
            return True

        except Exception as e:
            self.logger.error(f"Exception applying hunks in worktree: {e}")
            return False

    def _apply_single_hunk_in_worktree(
        self, mapping: HunkTargetMapping, worktree_git_ops: GitOps
    ) -> bool:
        """Apply a single hunk within the worktree.

        Args:
            mapping: Hunk mapping to apply
            worktree_git_ops: GitOps instance for worktree operations

        Returns:
            True if hunk applied successfully
        """
        try:
            # Create minimal patch for this hunk
            hunk_patch = self._create_minimal_patch_for_hunk(
                mapping.hunk, worktree_git_ops
            )
            if not hunk_patch:
                return False

            # Apply patch directly to worktree (no --cached needed)
            success, error_msg = worktree_git_ops._run_git_command_with_input(
                "apply", input_text=hunk_patch
            )

            if success:
                self.logger.debug(
                    f"Applied hunk for {mapping.hunk.file_path} in worktree"
                )
                return True
            else:
                self.logger.error(
                    f"Failed to apply hunk for {mapping.hunk.file_path}: {error_msg}"
                )
                return False

        except Exception as e:
            self.logger.error(f"Exception applying single hunk: {e}")
            return False

    def _create_minimal_patch_for_hunk(
        self, hunk, worktree_git_ops: GitOps
    ) -> Optional[str]:
        """Create a minimal git patch for a single hunk in worktree context.

        Args:
            hunk: DiffHunk object to create patch for
            worktree_git_ops: GitOps instance for worktree operations

        Returns:
            Patch content string, or None if creation failed
        """
        try:
            # Get blob info using worktree git operations
            blob_info = self._get_file_blob_info(hunk.file_path, worktree_git_ops)

            # Build minimal patch with proper git headers
            patch_lines = [
                f"diff --git a/{hunk.file_path} b/{hunk.file_path}",
                f"index {blob_info['old_hash']}..{blob_info['new_hash']} {blob_info['mode']}",
                f"--- a/{hunk.file_path}",
                f"+++ b/{hunk.file_path}",
            ]

            # Add hunk content
            patch_lines.extend(hunk.lines)

            return "\\n".join(patch_lines) + "\\n"

        except Exception as e:
            self.logger.error(f"Failed to create minimal patch for hunk: {e}")
            return None

    def _extract_changes_from_worktree(self, worktree_path: str) -> bool:
        """Extract processed changes from worktree back to main repository.

        Args:
            worktree_path: Path to worktree containing processed changes

        Returns:
            True if changes extracted successfully
        """
        try:
            # Create GitOps instance for the worktree
            worktree_git_ops = GitOps(Path(worktree_path))

            # Generate patch of all changes in worktree relative to HEAD
            success, patch_content = worktree_git_ops._run_git_command("diff", "HEAD")

            if not success:
                self.logger.error("Failed to generate patch from worktree changes")
                return False

            if not patch_content.strip():
                self.logger.warning("No changes found in worktree to extract")
                return True

            # Validate extracted patch
            success, error_msg = self.git_ops._run_git_command_with_input(
                "apply", "--check", input_text=patch_content
            )

            if not success:
                self.logger.error(f"Extracted patch validation failed: {error_msg}")
                return False

            # Apply the extracted patch to main working tree
            success, error_msg = self.git_ops._run_git_command_with_input(
                "apply", input_text=patch_content
            )

            if success:
                self.logger.info(
                    "Successfully extracted changes from worktree to main repository"
                )
                return True
            else:
                self.logger.error(f"Failed to apply extracted changes: {error_msg}")
                return False

        except Exception as e:
            self.logger.error(f"Exception extracting changes from worktree: {e}")
            return False

    def _cleanup_worktree(self, worktree_path: str) -> None:
        """Remove temporary worktree and associated metadata.

        Args:
            worktree_path: Path to worktree to remove
        """
        if not worktree_path:
            return

        self.logger.debug(f"Cleaning up temporary worktree: {worktree_path}")

        try:
            # Remove worktree (this also cleans up git metadata)
            success, output = self.git_ops._run_git_command(
                "worktree", "remove", "--force", worktree_path
            )

            if success:
                self.logger.debug("✓ Temporary worktree cleaned up")
            else:
                self.logger.warning(f"Git worktree remove failed: {output}")
                # Attempt manual cleanup as fallback
                self._manual_worktree_cleanup(worktree_path)

        except Exception as e:
            self.logger.warning(f"Exception during worktree cleanup: {e}")
            # Attempt manual cleanup as fallback
            self._manual_worktree_cleanup(worktree_path)

    def _manual_worktree_cleanup(self, worktree_path: str) -> None:
        """Manually clean up worktree directory as fallback.

        Args:
            worktree_path: Path to worktree directory
        """
        try:
            import shutil

            if Path(worktree_path).exists():
                shutil.rmtree(worktree_path, ignore_errors=True)
                self.logger.debug("Manual worktree cleanup completed")
        except Exception as e:
            self.logger.warning(f"Manual worktree cleanup failed: {e}")

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
            "git-autosquash-worktree-backup",
        )

        if success:
            # Extract stash reference - typically "stash@{0}" after creation
            stash_ref = "stash@{0}"
            self.logger.debug(f"Created backup stash: {stash_ref}")
            return stash_ref
        else:
            self.logger.error(f"Failed to create backup stash: {stash_output}")
            return None

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
            return False

    def _cleanup_stash(self, stash_ref: str) -> None:
        """Clean up backup stash.

        Args:
            stash_ref: Stash reference to clean up
        """
        if not stash_ref:
            return

        self.logger.debug(f"Cleaning up backup stash: {stash_ref}")

        success, output = self.git_ops._run_git_command("stash", "drop", stash_ref)

        if success:
            self.logger.debug("✓ Backup stash cleaned up")
        else:
            self.logger.warning(f"Failed to clean up stash {stash_ref}: {output}")

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

    def _get_file_blob_info(self, file_path: str, git_ops: GitOps) -> dict:
        """Get git blob information for proper patch headers.

        Args:
            file_path: Path to file
            git_ops: GitOps instance to use for commands

        Returns:
            Dictionary with old_hash, new_hash, and mode
        """
        try:
            # Get current file hash
            success, current_hash = git_ops._run_git_command("hash-object", file_path)

            # Get HEAD version hash
            success_head, head_hash = git_ops._run_git_command(
                "rev-parse", f"HEAD:{file_path}"
            )

            # Get file mode
            success_mode, mode_info = git_ops._run_git_command(
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
