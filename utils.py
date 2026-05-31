"""Utility functions for file operations and validation."""

import hashlib
import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional


def calculate_file_hash(file_path: Path, algorithm: str = 'sha256') -> str:
    """
    Calculate hash of a file for integrity verification.

    Args:
        file_path: Path to the file.
        algorithm: Hash algorithm to use (default: sha256).

    Returns:
        Hex digest of the file hash, or an error string if the file
        cannot be read.
    """
    hash_func = hashlib.new(algorithm)

    try:
        with open(file_path, 'rb') as f:
            # Read in 64 KB chunks to handle large files efficiently.
            for chunk in iter(lambda: f.read(65536), b''):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except (IOError, OSError) as exc:
        return f"ERROR: {exc}"


def validate_path(path: str) -> Optional[Path]:
    """
    Validate and resolve a string path.

    Args:
        path: String path to validate.

    Returns:
        Resolved Path object if the path exists, otherwise None.
    """
    try:
        resolved = Path(path).resolve()
        if not resolved.exists():
            return None
        return resolved
    except (OSError, ValueError):
        return None


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename by removing characters that are invalid on any
    major operating system.

    Args:
        filename: Original filename string.

    Returns:
        Sanitized filename string.  Guaranteed to be non-empty.
    """
    # Characters forbidden on Windows, macOS, or Linux.
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, '_', filename)

    # Strip leading/trailing dots and spaces (Windows reserves them).
    sanitized = sanitized.strip('. ')

    if not sanitized:
        sanitized = 'unnamed'

    return sanitized


def format_size(size_bytes: int) -> str:
    """
    Format a byte count as a human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted string such as "1.23 MB".
    """
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def get_unique_path(path: Path) -> Path:
    """
    Return a path that does not yet exist, appending ``_N`` before the
    extension when necessary.

    Args:
        path: Proposed destination path.

    Returns:
        ``path`` unchanged if it does not exist, otherwise
        ``<stem>_1<suffix>``, ``<stem>_2<suffix>``, … until a free name
        is found.
    """
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1

    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def is_hidden(path: Path) -> bool:
    """
    Determine whether a file or directory is hidden.

    On Unix-like systems a leading dot signals a hidden file.  On Windows
    the ``FILE_ATTRIBUTE_HIDDEN`` flag is checked in addition to the dot
    convention.

    Args:
        path: Path to inspect.

    Returns:
        True if the path is hidden, False otherwise.
    """
    if path.name.startswith('.'):
        return True

    if os.name == 'nt':
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
            # INVALID_FILE_ATTRIBUTES is 0xFFFFFFFF (== -1 as signed int).
            if attrs != -1 and bool(attrs & 0x2):  # FILE_ATTRIBUTE_HIDDEN
                return True
        except (AttributeError, OSError):
            pass

    return False


def matches_pattern(filename: str, patterns: list) -> bool:
    """
    Test whether *filename* matches any of the given glob *patterns*.

    Matching is case-insensitive on all platforms.

    Args:
        filename: The bare filename (not a full path) to test.
        patterns: Iterable of glob patterns (e.g. ``['*.tmp', '.DS_Store']``).

    Returns:
        True if the filename matches at least one pattern.
    """
    lower_name = filename.lower()
    return any(fnmatch(lower_name, pattern.lower()) for pattern in patterns)
