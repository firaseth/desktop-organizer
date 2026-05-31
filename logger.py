"""Logging and undo functionality.

Every successful file operation is recorded in a JSON log file so the
entire batch can be reversed with ``organize.py --undo <log>``.

Bug fixed vs. original:
    ``log_action`` previously checked ``source.exists()`` *after* a move
    had already removed the source, so ``file_size`` was always 0 for move
    operations.  The fix: accept an explicit ``file_size`` parameter that
    the caller captures *before* executing the operation.
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from utils import calculate_file_hash


class ActionLogger:
    """Records file operations and produces JSON / CSV reports."""

    def __init__(self, log_dir: Optional[Path] = None):
        """
        Initialise the logger.

        Args:
            log_dir: Directory where log files are written.  Defaults to
                     the current working directory.
        """
        self.log_dir: Path = log_dir or Path.cwd()
        self.log_file: Optional[Path] = None
        self.actions: List[Dict] = []

    # ------------------------------------------------------------------
    # Log-file lifecycle
    # ------------------------------------------------------------------

    def create_log(self) -> Path:
        """
        Create a new timestamped log file path (file is written later by
        :meth:`save`).

        Returns:
            The path that will be used when :meth:`save` is called.
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = self.log_dir / f'organize_log_{timestamp}.json'
        return self.log_file

    def save(self) -> None:
        """Serialise all recorded actions to the JSON log file.

        :meth:`create_log` is called automatically if not already done.
        """
        if not self.log_file:
            self.create_log()

        # Ensure the parent directory exists (output_dir may not yet).
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        log_data = {
            'created': datetime.now().isoformat(),
            'total_actions': len(self.actions),
            'actions': self.actions,
        }

        with open(self.log_file, 'w', encoding='utf-8') as fh:
            json.dump(log_data, fh, indent=2)

    # ------------------------------------------------------------------
    # Recording actions
    # ------------------------------------------------------------------

    def log_action(
        self,
        source: Path,
        destination: Path,
        operation: str,
        status: str,
        category: str,
        file_size: int = 0,
        error: Optional[str] = None,
        verify_hash: bool = False,
    ) -> None:
        """
        Record a single file operation.

        Args:
            source:      Original file path.
            destination: Intended destination path.
            operation:   ``'copy'`` or ``'move'``.
            status:      ``'success'``, ``'failed'``, or ``'skipped'``.
            category:    Category the file was placed into.
            file_size:   Size of the file in bytes.  The caller is
                         responsible for capturing this **before** a move
                         removes the source (fixes the original bug).
            error:       Human-readable error message, when applicable.
            verify_hash: When True *and* status is ``'success'``, compute
                         a SHA-256 hash of the destination for integrity
                         verification.  Adds latency for large files.
        """
        action: Dict = {
            'timestamp':   datetime.now().isoformat(),
            'source':      str(source),
            'destination': str(destination),
            'operation':   operation,
            'status':      status,
            'category':    category,
            'file_size':   file_size,
            'hash':        None,
        }

        if error:
            action['error'] = error

        # Optionally compute a hash of the destination for verification.
        if verify_hash and status == 'success':
            try:
                action['hash'] = calculate_file_hash(destination)
            except (OSError, PermissionError):
                pass

        self.actions.append(action)

    # ------------------------------------------------------------------
    # Export / reporting
    # ------------------------------------------------------------------

    def export_csv(self, csv_path: Path) -> None:
        """
        Write all recorded actions to a CSV file.

        Args:
            csv_path: Destination CSV path.
        """
        if not self.actions:
            return

        fieldnames = [
            'timestamp', 'source', 'destination', 'category',
            'operation', 'status', 'file_size', 'hash', 'error',
        ]

        with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for action in self.actions:
                row = {field: action.get(field, '') for field in fieldnames}
                writer.writerow(row)

    def get_summary(self) -> Dict:
        """
        Summarise all recorded actions.

        Returns:
            Dictionary with keys ``total``, ``successful``, ``failed``,
            ``skipped``, ``categories`` (mapping → count), and
            ``total_size`` (bytes successfully processed).
        """
        successful = sum(1 for a in self.actions if a['status'] == 'success')
        failed     = sum(1 for a in self.actions if a['status'] == 'failed')
        skipped    = sum(1 for a in self.actions if a['status'] == 'skipped')

        categories: Dict[str, int] = {}
        for action in self.actions:
            cat = action['category']
            categories[cat] = categories.get(cat, 0) + 1

        total_size = sum(
            a.get('file_size', 0)
            for a in self.actions
            if a['status'] == 'success'
        )

        return {
            'total':      len(self.actions),
            'successful': successful,
            'failed':     failed,
            'skipped':    skipped,
            'categories': categories,
            'total_size': total_size,
        }

    # ------------------------------------------------------------------
    # Static helpers (used by undo)
    # ------------------------------------------------------------------

    @staticmethod
    def load_log(log_path: Path) -> Dict:
        """
        Load a previously saved log file.

        Args:
            log_path: Path to the JSON log file.

        Returns:
            Parsed log dictionary.

        Raises:
            FileNotFoundError: If *log_path* does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        with open(log_path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
