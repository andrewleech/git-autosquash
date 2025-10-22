"""Specialized classes for resolving hunk targets."""

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

from git_autosquash.git_ops import GitOps
from git_autosquash.hunk_parser import DiffHunk
from git_autosquash.batch_git_ops import BatchGitOperations
from git_autosquash.squash_context import SquashContext


class TargetingMethod(Enum):
    """Enum for different targeting methods used to resolve a hunk."""

    BLAME_MATCH = "blame_match"
    CONTEXTUAL_BLAME_MATCH = "contextual_blame_match"  # Found via context lines
    FALLBACK_NEW_FILE = "fallback_new_file"
    FALLBACK_EXISTING_FILE = "fallback_existing_file"
    FALLBACK_CONSISTENCY = "fallback_consistency"


@dataclass
class BlameInfo:
    """Represents git blame information for a line."""

    commit_hash: str
    author: str
    timestamp: str
    line_number: int
    line_content: str


@dataclass
class HunkTargetMapping:
    """Maps a hunk to its target commit for squashing."""

    hunk: DiffHunk
    target_commit: Optional[str]
    confidence: str  # 'high', 'medium', 'low'
    blame_info: List[BlameInfo]
    targeting_method: TargetingMethod = TargetingMethod.BLAME_MATCH
    fallback_candidates: Optional[List[str]] = None
    needs_user_selection: bool = False
    source_commit_sha: Optional[str] = (
        None  # Split commit SHA for cherry-pick (if using split commits)
    )

    def __hash__(self) -> int:
        """Make HunkTargetMapping hashable for use as dictionary keys."""
        return hash(
            (
                self.hunk.file_path,
                self.hunk.old_start,
                self.hunk.old_count,
                self.hunk.new_start,
                self.hunk.new_count,
                self.targeting_method,
            )
        )

    def __eq__(self, other) -> bool:
        """Define equality for hashable objects."""
        if not isinstance(other, HunkTargetMapping):
            return False
        return (
            self.hunk.file_path == other.hunk.file_path
            and self.hunk.old_start == other.hunk.old_start
            and self.hunk.old_count == other.hunk.old_count
            and self.hunk.new_start == other.hunk.new_start
            and self.hunk.new_count == other.hunk.new_count
            and self.targeting_method == other.targeting_method
        )


class BlameAnalysisEngine:
    """Core engine for analyzing git blame information."""

    def __init__(self, git_ops: GitOps, merge_base: str, blame_ref: str = "HEAD"):
        """Initialize blame analysis engine.

        Args:
            git_ops: GitOps instance for running git commands
            merge_base: Merge base commit hash to limit scope
            blame_ref: Git ref to use for blame operations (default: HEAD)
        """
        self.git_ops = git_ops
        self.merge_base = merge_base
        self.blame_ref = blame_ref
        self.batch_ops = BatchGitOperations(git_ops, merge_base, blame_ref=blame_ref)

    def get_blame_for_old_lines(self, hunk: DiffHunk) -> List[BlameInfo]:
        """Get blame information for lines being deleted/modified.

        Args:
            hunk: DiffHunk with deletions

        Returns:
            List of BlameInfo objects for the deleted lines
        """
        success, blame_output = self.git_ops._run_git_command(
            "blame",
            "--porcelain",
            f"-L{hunk.old_start},{hunk.old_start + hunk.old_count - 1}",
            self.blame_ref,
            "--",
            hunk.file_path,
        )

        if not success:
            return []

        return self._parse_blame_output_porcelain(blame_output)

    def get_blame_for_context(self, hunk: DiffHunk) -> List[BlameInfo]:
        """Get blame information for context around an addition.

        Args:
            hunk: DiffHunk with additions

        Returns:
            List of BlameInfo objects for surrounding context
        """
        context_lines = 3
        start_line = max(1, hunk.new_start - context_lines)
        end_line = hunk.new_start + context_lines

        success, blame_output = self.git_ops._run_git_command(
            "blame",
            "--porcelain",
            f"-L{start_line},{end_line}",
            self.blame_ref,
            "--",
            hunk.file_path,
        )

        if not success:
            return []

        return self._parse_blame_output_porcelain(blame_output)

    def _parse_blame_output(self, blame_output: str) -> List[BlameInfo]:
        """Parse git blame output into BlameInfo objects.

        Args:
            blame_output: Raw git blame output

        Returns:
            List of parsed BlameInfo objects
        """
        import re

        blame_infos = []

        for line in blame_output.split("\n"):
            if not line.strip():
                continue

            # Parse blame line format:
            # commit_hash path (author timestamp line_num) line_content
            match = re.match(
                r"^([a-f0-9]+)\s+\S+\s+\(([^)]+)\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4})\s+(\d+)\)\s*(.*)",
                line,
            )
            if match:
                commit_hash = match.group(1)
                author = match.group(2).strip()
                timestamp = match.group(3)
                line_number = int(match.group(4))
                line_content = match.group(5)

                blame_info = BlameInfo(
                    commit_hash=commit_hash,
                    author=author,
                    timestamp=timestamp,
                    line_number=line_number,
                    line_content=line_content,
                )
                blame_infos.append(blame_info)

        return blame_infos

    def _parse_blame_output_porcelain(self, blame_output: str) -> List[BlameInfo]:
        """Parse git blame --porcelain output into BlameInfo objects.

        The porcelain format is stable across git versions and designed for machine parsing.
        Format per line:
            <40-byte hex sha> <original line> <final line> [<num lines in group>]
            author <author name>
            author-mail <author email>
            author-time <timestamp>
            author-tz <timezone>
            ... (other fields)
            filename <filename>
            \t<line content>

        Args:
            blame_output: Raw git blame --porcelain output

        Returns:
            List of parsed BlameInfo objects
        """
        import re

        blame_infos = []
        lines = blame_output.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # Parse header line: <commit> <original line> <final line> [<num lines>]
            match = re.match(r"^([a-f0-9]{40})\s+(\d+)\s+(\d+)", line)
            if not match:
                i += 1
                continue

            commit_hash = match.group(1)
            line_number = int(match.group(3))  # final line number

            # Parse metadata fields until we hit the tab-indented line content
            author = ""
            timestamp = ""
            line_content = ""
            i += 1

            while i < len(lines):
                meta_line = lines[i]

                # Line content is tab-indented
                if meta_line.startswith("\t"):
                    line_content = meta_line[1:]  # Remove leading tab
                    i += 1
                    break

                # Parse author and timestamp fields
                if meta_line.startswith("author "):
                    author = meta_line[7:]  # Remove "author " prefix
                elif meta_line.startswith("author-time "):
                    timestamp = meta_line[12:]  # Unix timestamp

                i += 1

            blame_info = BlameInfo(
                commit_hash=commit_hash,
                author=author,
                timestamp=timestamp,
                line_number=line_number,
                line_content=line_content,
            )
            blame_infos.append(blame_info)

        return blame_infos

    def get_contextual_blame(
        self, hunk: DiffHunk, branch_commits: set
    ) -> List[BlameInfo]:
        """Get contextual blame information when primary blame fails.

        Uses ±1 lines around the hunk to find blame information from branch commits.

        Args:
            hunk: DiffHunk to get contextual blame for
            branch_commits: Set of commit hashes within branch scope

        Returns:
            List of BlameInfo objects from contextual lines within branch scope
        """
        # Use old coordinates for git blame HEAD compatibility
        if hunk.has_deletions or hunk.old_count > 0:
            base_start = hunk.old_start
            base_count = hunk.old_count
        else:
            base_start = hunk.old_start
            base_count = 0

        # Calculate context range (±1 line)
        context_lines = 1
        if base_count > 0:
            # For modifications/deletions: search around existing lines
            start_line = max(1, base_start - context_lines)
            end_line = base_start + base_count + context_lines - 1
        else:
            # For pure additions: search around insertion point
            start_line = max(1, base_start - context_lines)
            end_line = base_start + context_lines

        # Get blame for the context range
        success, blame_output = self.git_ops._run_git_command(
            "blame",
            "--porcelain",
            f"-L{start_line},{end_line}",
            self.blame_ref,
            "--",
            hunk.file_path,
        )

        if not success:
            return []

        # Parse blame output and expand short hashes
        raw_blame_infos = self._parse_blame_output_porcelain(blame_output)

        # Collect short hashes and expand them using batch operations
        short_hashes = [
            info.commit_hash for info in raw_blame_infos if len(info.commit_hash) < 40
        ]
        expanded_hashes = (
            self.batch_ops.batch_expand_hashes(short_hashes) if short_hashes else {}
        )

        # Update blame infos with expanded hashes and filter to branch commits
        contextual_blame = []
        for info in raw_blame_infos:
            full_hash = expanded_hashes.get(info.commit_hash, info.commit_hash)
            if full_hash in branch_commits:
                contextual_blame.append(
                    BlameInfo(
                        commit_hash=full_hash,
                        author=info.author,
                        timestamp=info.timestamp,
                        line_number=info.line_number,
                        line_content=info.line_content,
                    )
                )

        return contextual_blame


class FallbackTargetProvider:
    """Provides fallback target candidates when blame analysis fails."""

    def __init__(self, batch_ops: BatchGitOperations, context: SquashContext):
        """Initialize fallback target provider.

        Args:
            batch_ops: BatchGitOperations instance for efficient git operations
            context: SquashContext for centralized blame/HEAD exclusion logic
        """
        self.batch_ops = batch_ops
        self.context = context

    def get_fallback_candidates(
        self, file_path: str, method: TargetingMethod
    ) -> List[str]:
        """Get prioritized list of candidate commits for fallback scenarios.

        Args:
            file_path: Path of the file being processed
            method: Fallback method to determine candidate ordering

        Returns:
            List of commit hashes ordered by priority
        """
        branch_commits = self.batch_ops.get_branch_commits()

        # Only exclude HEAD if working tree is clean (meaning HEAD commit is being processed)
        # If there are working tree or staged changes, HEAD should remain as a valid target
        should_exclude_head = self._should_exclude_head_as_target()

        if should_exclude_head:
            try:
                result = self.batch_ops.git_ops.run_git_command(["rev-parse", "HEAD"])
                if result.returncode == 0:
                    current_head = result.stdout.strip()
                    branch_commits = [
                        commit for commit in branch_commits if commit != current_head
                    ]
                    print(
                        f"DEBUG: Excluded HEAD {current_head[:8]} from fallback candidates (clean working tree)"
                    )
            except Exception as e:
                print(f"WARNING: Error getting current HEAD: {e}")

        if method == TargetingMethod.FALLBACK_NEW_FILE:
            # For new files, return commits ordered by recency, merges last
            ordered_commits = self.batch_ops.get_ordered_commits_by_recency(
                branch_commits
            )
            return [commit.commit_hash for commit in ordered_commits]

        elif method == TargetingMethod.FALLBACK_EXISTING_FILE:
            # For existing files, prioritize commits that touched this file
            file_relevant, other_commits = self.batch_ops.get_file_relevant_commits(
                branch_commits, file_path
            )
            relevant_hashes = [commit.commit_hash for commit in file_relevant]
            other_hashes = [commit.commit_hash for commit in other_commits]
            return relevant_hashes + other_hashes

        # Default fallback
        ordered_commits = self.batch_ops.get_ordered_commits_by_recency(branch_commits)
        return [commit.commit_hash for commit in ordered_commits]

    def _should_exclude_head_as_target(self) -> bool:
        """Determine if HEAD should be excluded as a fallback target.

        HEAD should only be excluded when the working tree is clean, meaning
        we're processing the HEAD commit itself. When there are working tree
        or staged changes, HEAD should remain as a valid target. When processing
        historical commits with --source, HEAD should also remain as a valid target.

        Returns:
            True if HEAD should be excluded from fallback candidates
        """
        return self.context.should_exclude_head_from_fallback()


class FileConsistencyTracker:
    """Tracks target consistency across hunks from the same file."""

    def __init__(self):
        """Initialize file consistency tracker."""
        self._file_target_cache: Dict[str, str] = {}

    def get_consistent_target(self, file_path: str) -> Optional[str]:
        """Get previously assigned target for consistency.

        Args:
            file_path: File path to check

        Returns:
            Target commit hash if one was previously assigned, None otherwise
        """
        return self._file_target_cache.get(file_path)

    def set_target_for_file(self, file_path: str, target_commit: str) -> None:
        """Set target commit for a file to ensure consistency.

        Args:
            file_path: File path
            target_commit: Commit hash to use as target
        """
        self._file_target_cache[file_path] = target_commit

    def clear(self) -> None:
        """Clear the consistency cache."""
        self._file_target_cache.clear()


class HunkTargetResolver:
    """Main resolver that orchestrates hunk target resolution."""

    def __init__(
        self,
        git_ops: GitOps,
        merge_base: str,
        context: SquashContext,
        blame_ref: str = "HEAD",
    ):
        """Initialize hunk target resolver.

        Args:
            git_ops: GitOps instance for running git commands
            merge_base: Merge base commit hash to limit scope
            context: SquashContext for centralized blame/HEAD exclusion logic
            blame_ref: Git ref to use for blame operations (default: HEAD)
        """
        self.git_ops = git_ops
        self.merge_base = merge_base
        self.blame_ref = blame_ref
        self.context = context
        self.batch_ops = BatchGitOperations(git_ops, merge_base, blame_ref=blame_ref)
        self.blame_engine = BlameAnalysisEngine(
            git_ops, merge_base, blame_ref=blame_ref
        )
        self.fallback_provider = FallbackTargetProvider(self.batch_ops, context=context)
        self.consistency_tracker = FileConsistencyTracker()

    def resolve_targets(self, hunks: List[DiffHunk]) -> List[HunkTargetMapping]:
        """Resolve target commits for a list of hunks.

        Args:
            hunks: List of DiffHunk objects to analyze

        Returns:
            List of HunkTargetMapping objects with target commit information
        """
        mappings = []

        for hunk in hunks:
            mapping = self._resolve_single_hunk(hunk)
            mappings.append(mapping)

        return mappings

    def _should_exclude_head_from_blame_analysis(self) -> bool:
        """Determine if HEAD should be excluded from blame analysis.

        HEAD should be excluded from blame analysis when processing the HEAD
        commit itself (clean working tree), but included when processing
        working tree or staged changes OR when processing historical commits.

        Returns:
            True if HEAD should be excluded from blame analysis
        """
        return self.context.should_exclude_head_from_blame()

    def _resolve_single_hunk(self, hunk: DiffHunk) -> HunkTargetMapping:
        """Resolve target for a single hunk.

        Args:
            hunk: DiffHunk to analyze

        Returns:
            HunkTargetMapping with target commit information
        """
        # Check if this is a new file
        if self._is_new_file(hunk.file_path):
            return self._create_fallback_mapping(
                hunk, TargetingMethod.FALLBACK_NEW_FILE
            )

        # Try blame-based analysis first (don't use consistency tracker here)
        if hunk.has_deletions:
            blame_info = self.blame_engine.get_blame_for_old_lines(hunk)
        else:
            blame_info = self.blame_engine.get_blame_for_context(hunk)

        # Filter commits to only those within our branch scope
        # Exclude HEAD when processing HEAD commit (clean working tree)
        branch_commits = set(self.batch_ops.get_branch_commits())
        if self._should_exclude_head_from_blame_analysis():
            try:
                result = self.git_ops.run_git_command(["rev-parse", "HEAD"])
                if result.returncode == 0:
                    current_head = result.stdout.strip()
                    branch_commits.discard(current_head)
                    print(
                        f"DEBUG: Excluded HEAD {current_head[:8]} from blame analysis (clean working tree)"
                    )
            except Exception as e:
                print(f"WARNING: Error getting current HEAD for blame filtering: {e}")

        relevant_blame = [
            info for info in blame_info if info.commit_hash in branch_commits
        ]

        # If no relevant blame found, try contextual blame as fallback
        if not relevant_blame:
            contextual_blame = self.blame_engine.get_contextual_blame(
                hunk, branch_commits
            )
            if contextual_blame:
                relevant_blame = contextual_blame

        if not relevant_blame:
            return self._create_fallback_mapping(
                hunk, TargetingMethod.FALLBACK_EXISTING_FILE, blame_info
            )

        # Determine best target from blame info
        target_commit, confidence = self._analyze_blame_consensus(relevant_blame)

        # Don't use consistency tracker - each hunk should use its own blame results
        # Different parts of a file can be modified by different commits

        # Determine targeting method based on whether contextual blame was used
        targeting_method = (
            TargetingMethod.CONTEXTUAL_BLAME_MATCH
            if not blame_info
            or not [info for info in blame_info if info.commit_hash in branch_commits]
            else TargetingMethod.BLAME_MATCH
        )

        return HunkTargetMapping(
            hunk=hunk,
            target_commit=target_commit,
            confidence=confidence,
            blame_info=relevant_blame,
            targeting_method=targeting_method,
            needs_user_selection=False,
        )

    def _analyze_blame_consensus(self, blame_info: List[BlameInfo]) -> tuple[str, str]:
        """Analyze blame info to find consensus target with confidence.

        For fixup commits (formatting, style changes), we prioritize the most recent
        commit that touched the lines, as that's typically where the fixup should go.

        Args:
            blame_info: List of BlameInfo objects

        Returns:
            Tuple of (target_commit, confidence_level)
        """
        # Group by commit and count occurrences
        commit_counts: Dict[str, int] = {}
        for info in blame_info:
            commit_counts[info.commit_hash] = commit_counts.get(info.commit_hash, 0) + 1

        # Get commit info for recency comparison
        commit_hashes = list(commit_counts.keys())
        commit_info_dict = self.batch_ops.batch_load_commit_info(commit_hashes)

        # Find most recent commit, use frequency as tie-breaker
        # This ensures formatting/style fixes go to the newest commit that touched the code
        most_recent_commit, count = max(
            commit_counts.items(),
            key=lambda x: (
                getattr(commit_info_dict.get(x[0]), "timestamp", 0),  # PRIMARY: recency
                x[1],  # TIE-BREAKER: frequency
            ),
        )

        total_lines = len(blame_info)
        confidence_ratio = count / total_lines

        if confidence_ratio >= 0.8:
            confidence = "high"
        elif confidence_ratio >= 0.5:
            confidence = "medium"
        else:
            confidence = "low"

        return most_recent_commit, confidence

    def _is_new_file(self, file_path: str) -> bool:
        """Check if a file is new (didn't exist at merge-base).

        Args:
            file_path: Path to check

        Returns:
            True if file is new, False if it existed at merge-base
        """
        # Use the more efficient individual file check
        return self.batch_ops.is_new_file(file_path)

    def _create_fallback_mapping(
        self,
        hunk: DiffHunk,
        method: TargetingMethod,
        blame_info: Optional[List[BlameInfo]] = None,
    ) -> HunkTargetMapping:
        """Create a fallback mapping that needs user selection.

        Args:
            hunk: DiffHunk to create mapping for
            method: Fallback method used
            blame_info: Optional blame info if available

        Returns:
            HunkTargetMapping with fallback candidates
        """
        candidates = self.fallback_provider.get_fallback_candidates(
            hunk.file_path, method
        )

        return HunkTargetMapping(
            hunk=hunk,
            target_commit=None,
            confidence="low",
            blame_info=blame_info or [],
            targeting_method=method,
            fallback_candidates=candidates,
            needs_user_selection=True,
        )

    def get_commit_summary(self, commit_hash: str) -> str:
        """Get a short summary of a commit for display.

        Args:
            commit_hash: Commit hash to summarize

        Returns:
            Short commit summary (hash + subject)
        """
        commit_info = self.batch_ops.batch_load_commit_info([commit_hash])
        if commit_hash in commit_info:
            info = commit_info[commit_hash]
            return f"{info.short_hash} {info.subject}"
        return commit_hash[:8]

    def set_target_for_file(self, file_path: str, target_commit: str) -> None:
        """Set target commit for a file to ensure consistency.

        Args:
            file_path: File path
            target_commit: Commit hash to use as target
        """
        self.consistency_tracker.set_target_for_file(file_path, target_commit)

    def clear_caches(self) -> None:
        """Clear all internal caches for fresh analysis."""
        self.batch_ops.clear_caches()
        self.consistency_tracker.clear()
