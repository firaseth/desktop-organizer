"""Configuration management for the file organizer."""

import json
from pathlib import Path
from typing import Dict, List, Optional


class Config:
    """Loads, validates, and exposes configuration for file organization."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialise the configuration.

        Args:
            config_path: Optional path to a custom JSON config file.
                         Defaults to ``default_config.json`` next to this
                         module.
        """
        self.config_path = config_path or self._default_config_path()
        self.data = self._load_config()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _default_config_path(self) -> Path:
        """Return the path to the bundled default configuration file."""
        return Path(__file__).parent / 'default_config.json'

    def _load_config(self) -> Dict:
        """
        Load configuration from *self.config_path*.

        Falls back to a minimal built-in configuration if the file cannot
        be read or parsed.
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
                # Basic validation: 'categories' must be a mapping.
                if not isinstance(data.get('categories'), dict):
                    raise ValueError("'categories' must be a JSON object.")
                return data
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
            print(f"Warning: Could not load config '{self.config_path}': {exc}")
            print("         Falling back to built-in defaults.")
            return self._builtin_defaults()

    @staticmethod
    def _builtin_defaults() -> Dict:
        """Return a minimal safe configuration when no file is available."""
        return {
            "categories": {
                "other": []
            },
            "default_mode": "copy",
            "duplicate_strategy": "rename",
            "exclude_patterns": []
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def categories(self) -> Dict[str, List[str]]:
        """Mapping of category name → list of extensions (lower-cased)."""
        return self.data.get('categories', {})

    @property
    def default_mode(self) -> str:
        """Default operation mode: ``'copy'`` or ``'move'``."""
        mode = self.data.get('default_mode', 'copy')
        return mode if mode in ('copy', 'move') else 'copy'

    @property
    def duplicate_strategy(self) -> str:
        """How duplicate filenames are handled: ``'rename'``, ``'skip'``, or
        ``'overwrite'``."""
        strategy = self.data.get('duplicate_strategy', 'rename')
        return strategy if strategy in ('rename', 'skip', 'overwrite') else 'rename'

    @property
    def exclude_patterns(self) -> List[str]:
        """List of glob patterns for files that should be ignored."""
        return self.data.get('exclude_patterns', [])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_category_for_extension(self, extension: str) -> str:
        """
        Look up the category that owns *extension*.

        Args:
            extension: File extension, with or without a leading dot.

        Returns:
            Category name, or ``'other'`` when the extension is unknown.
        """
        # Normalise to lower-case with a leading dot.
        ext = extension.lower()
        if not ext.startswith('.'):
            ext = f'.{ext}'

        for category, extensions in self.categories.items():
            if ext in [e.lower() for e in extensions]:
                return category

        return 'other'

    def add_category(self, name: str, extensions: List[str]) -> None:
        """
        Add or replace a category at runtime.

        Args:
            name:       Category name (e.g. ``'raw_images'``).
            extensions: List of extensions (e.g. ``['.cr2', '.nef']``).
        """
        self.data.setdefault('categories', {})[name] = extensions

    def save(self, path: Optional[Path] = None) -> None:
        """
        Persist the current configuration to disk.

        Args:
            path: Destination file.  Defaults to the path used when this
                  instance was created.
        """
        save_path = path or self.config_path
        with open(save_path, 'w', encoding='utf-8') as fh:
            json.dump(self.data, fh, indent=2)
        print(f"Configuration saved to: {save_path}")
