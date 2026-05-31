"""File organisation and movement logic.

Fixes vs. original:
1. ``file_size`` is now captured *before* the move so ``logger.log_action``
   receives the correct value even when the source no longer exists.
2. ``_handle_duplicate`` now logs a ``'skipped'`` entry for unknown strategy
   values instead of silently returning ``None`` with no record.
"""

import shutil
from pathlib import Path
from typing import Dict, List, Optional

from logger import ActionLogger
from utils import get_unique_path


class FileOrganizer:
    """Executes the actual copy / move operations that organise files."""

    def __init__(
        self,
        output_dir: Path,
        mode: str = 'copy',
        duplicate_strategy: str = 'rename',
        logger: Optional[ActionLogger] = None,
    ):
        """
        Initialise the organiser.

        Args:
            output_dir:          Root directory where category sub-folders
                                 are created.
            mode:                ``'copy'`` (default) or ``'move'``.
            duplicate_strategy:  How to handle name collisions:
                                 * ``'rename'``    – append ``_N`` suffix
                                 * ``'skip'``      – leave the file in place
                                 * ``'overwrite'`` – replace the destination
            logger:              :class:`~logger.ActionLogger` instance.
                                 A new one is created when omitted.
        """
        self.output_dir = output_dir
        self.mode = mode
        self.duplicate_strategy = duplicate_strategy
        self.logger = logger or ActionLogger()

        # Populated during :meth:`organise` for later display.
        self.conflicts: List[Dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def organize(
        self,
        categorized: Dict[str, List[Path]],
        preview: bool = False,
    ) -> Dict[str, int]:
        """
        Organise files into category sub-folders under ``output_dir``.

        Args:
            categorized: ``{ category: [Path, …] }`` mapping, typically
                         produced by :class:`~classifier.FileClassifier`.
            preview:     When True, print planned operations without
                         making any file-system changes.

        Returns:
            ``{ 'total': N, 'successful': N, 'failed': N, 'skipped': N }``
        """
        stats = {'total': 0, 'successful': 0, 'failed': 0, 'skipped': 0}

        if not preview:
            self._create_category_dirs(list(categorized.keys()))

        for category, files in sorted(categorized.items()):
            category_dir = self.output_dir / category

            for file in files:
                stats['total'] += 1
                destination = category_dir / file.name

                # Resolve naming conflicts before acting.
                if destination.exists():
                    destination = self._handle_duplicate(
                        file, destination, category, preview
                    )
                    if destination is None:
                        stats['skipped'] += 1
                        continue

                if preview:
                    print(
                        f"  [{self.mode.upper():4s}] "
                        f"[{category:15s}] {file.name}"
                        f"\n          → {destination}"
                    )
                else:
                    if self._execute_operation(file, destination, category):
                        stats['successful'] += 1
                    else:
                        stats['failed'] += 1

        return stats

    def undo(self, log_path: Path) -> Dict[str, int]:
        """
        Reverse operations recorded in a log file.

        For ``'move'`` operations the file is moved back to its source.
        For ``'copy'`` operations the destination copy is deleted.

        Args:
            log_path: Path to a JSON log produced by a previous run.

        Returns:
            ``{ 'restored': N, 'failed': N, 'skipped': N }``
        """
        log_data = ActionLogger.load_log(log_path)
        stats = {'restored': 0, 'failed': 0, 'skipped': 0}

        print(
            f"\n[Undo] Processing {len(log_data['actions'])} "
            f"action(s) from log …"
        )

        # Process in reverse chronological order.
        for action in reversed(log_data['actions']):
            if action['status'] != 'success':
                stats['skipped'] += 1
                continue

            source      = Path(action['source'])
            destination = Path(action['destination'])

            if not destination.exists():
                print(f"  SKIP : {destination.name} no longer exists at destination.")
                stats['skipped'] += 1
                continue

            try:
                if action['operation'] == 'move':
                    # Recreate parent directory if needed.
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(destination), str(source))
                else:  # copy → just remove the duplicate we created
                    destination.unlink()

                print(f"  ✓ Restored: {source.name}")
                stats['restored'] += 1

            except (OSError, PermissionError, shutil.Error) as exc:
                print(f"  ERROR: Could not restore {source.name}: {exc}")
                stats['failed'] += 1

        return stats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_category_dirs(self, categories: List[str]) -> None:
        """Create ``output_dir/<category>/`` for each category."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for category in categories:
            (self.output_dir / category).mkdir(exist_ok=True)

    def _handle_duplicate(
        self,
        source: Path,
        destination: Path,
        category: str,
        preview: bool = False,
    ) -> Optional[Path]:
        """
        Apply the configured duplicate strategy.

        Args:
            source:      Source file.
            destination: Conflicting destination path.
            category:    Category name (for logging).
            preview:     When True, no log entry is written.

        Returns:
            Adjusted destination path, or None when the file should be
            skipped.
        """
        strategy = self.duplicate_strategy

        if strategy == 'skip':
            self.conflicts.append({
                'source':      source,
                'destination': destination,
                'action':      'skipped',
            })
            if not preview:
                self.logger.log_action(
                    source, destination, self.mode, 'skipped', category
                )
            return None

        if strategy == 'rename':
            new_dest = get_unique_path(destination)
            self.conflicts.append({
                'source':   source,
                'original': destination,
                'renamed':  new_dest,
                'action':   'renamed',
            })
            return new_dest

        if strategy == 'overwrite':
            self.conflicts.append({
                'source':      source,
                'destination': destination,
                'action':      'overwritten',
            })
            return destination

        # Unknown strategy – treat as skip and log a warning.
        print(
            f"  WARNING: Unknown duplicate_strategy '{strategy}'; "
            f"skipping {source.name}."
        )
        self.conflicts.append({
            'source':      source,
            'destination': destination,
            'action':      'skipped (unknown strategy)',
        })
        if not preview:
            self.logger.log_action(
                source, destination, self.mode, 'skipped', category,
                error=f"Unknown duplicate_strategy: {strategy}"
            )
        return None

    def _execute_operation(
        self,
        source: Path,
        destination: Path,
        category: str,
    ) -> bool:
        """
        Perform a single copy or move operation and log the result.

        File size is captured *before* the operation so that the correct
        value is available even after a move removes the source.

        Args:
            source:      Source file path.
            destination: Destination file path.
            category:    Category name (for the log).

        Returns:
            True on success, False on failure.
        """
        # Capture size BEFORE the move (fixes original bug).
        try:
            file_size = source.stat().st_size
        except (OSError, PermissionError):
            file_size = 0

        try:
            if self.mode == 'copy':
                shutil.copy2(source, destination)
            else:  # move
                shutil.move(str(source), str(destination))

            self.logger.log_action(
                source, destination, self.mode,
                'success', category, file_size=file_size
            )
            return True

        except (OSError, PermissionError, shutil.Error) as exc:
            self.logger.log_action(
                source, destination, self.mode,
                'failed', category,
                file_size=file_size,
                error=str(exc)
            )
            print(f"  ERROR: Failed to {self.mode} '{source.name}': {exc}")
            return False
