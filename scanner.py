"""Directory scanning functionality."""

from pathlib import Path
from typing import List

from utils import is_hidden, matches_pattern


class DirectoryScanner:
    """Scans a directory tree and collects regular files eligible for
    organisation."""

    def __init__(
        self,
        exclude_patterns: List[str] = None,
        include_hidden: bool = False,
    ):
        """
        Initialise the scanner.

        Args:
            exclude_patterns: Glob patterns for filenames to skip
                              (e.g. ``['*.tmp', '.DS_Store']``).
            include_hidden:   When *False* (default) hidden files are
                              silently ignored.
        """
        self.exclude_patterns: List[str] = exclude_patterns or []
        self.include_hidden: bool = include_hidden

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, directory: Path, recursive: bool = False) -> List[Path]:
        """
        Walk *directory* and return every file that passes the inclusion
        filters.

        Args:
            directory: Root directory to scan.
            recursive: When True the full subtree is scanned, not just the
                       immediate children.

        Returns:
            Sorted list of :class:`pathlib.Path` objects for matching files.
        """
        files: List[Path] = []

        try:
            # ``iterdir()`` for the top level, ``rglob('*')`` for recursive.
            # Using ``rglob`` avoids the ``**/*`` pattern which unnecessarily
            # yields directories as intermediate results.
            iterator = directory.rglob('*') if recursive else directory.iterdir()

            for item in iterator:
                if self._should_include(item):
                    files.append(item)

        except PermissionError as exc:
            print(f"Warning: Permission denied accessing '{directory}': {exc}")

        return sorted(files)

    def get_stats(self, files: List[Path]) -> dict:
        """
        Compute basic statistics for a list of files.

        Args:
            files: File paths as returned by :meth:`scan`.

        Returns:
            Dictionary with keys:
            * ``total_files``       – number of files
            * ``total_size``        – cumulative size in bytes
            * ``extensions``        – mapping of extension → count
            * ``unique_extensions`` – number of distinct extensions
        """
        total_size = 0
        extensions: dict = {}

        for file in files:
            try:
                size = file.stat().st_size
                total_size += size
                ext = file.suffix.lower() or '(none)'
                extensions[ext] = extensions.get(ext, 0) + 1
            except (OSError, PermissionError):
                continue

        return {
            'total_files': len(files),
            'total_size': total_size,
            'extensions': extensions,
            'unique_extensions': len(extensions),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_include(self, path: Path) -> bool:
        """
        Decide whether *path* should appear in the results.

        A path is excluded when it is:
        * a directory,
        * a symbolic link (treated as unsafe to move),
        * a hidden file/directory and ``include_hidden`` is False, or
        * matched by one of the ``exclude_patterns``.

        Args:
            path: Candidate path.

        Returns:
            True when the file should be included.
        """
        if path.is_dir():
            return False

        if path.is_symlink():
            return False

        if not self.include_hidden and is_hidden(path):
            return False

        if self.exclude_patterns and matches_pattern(path.name, self.exclude_patterns):
            return False

        return True
