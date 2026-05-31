"""File classification by extension."""

from pathlib import Path
from typing import Dict, List

from config import Config


class FileClassifier:
    """Classifies a collection of files into named categories based on their
    extensions, as defined in the active :class:`~config.Config`."""

    def __init__(self, config: Config):
        """
        Initialise the classifier.

        Args:
            config: Loaded configuration object that supplies the
                    extension-to-category mapping.
        """
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, files: List[Path]) -> Dict[str, List[Path]]:
        """
        Partition *files* into a dictionary keyed by category name.

        Files whose extension is not mapped to any category are placed
        in the ``'other'`` bucket.

        Args:
            files: Iterable of file paths to classify.

        Returns:
            ``{ category_name: [Path, …], … }``
        """
        categorized: Dict[str, List[Path]] = {}

        for file in files:
            category = self.get_category(file)
            categorized.setdefault(category, []).append(file)

        return categorized

    def get_category(self, file: Path) -> str:
        """
        Return the category name for a single file.

        Args:
            file: A file path.

        Returns:
            Category string (e.g. ``'images'``), or ``'other'`` when
            the extension is unrecognised.
        """
        return self.config.get_category_for_extension(file.suffix)

    def get_summary(self, categorized: Dict[str, List[Path]]) -> Dict[str, int]:
        """
        Summarise categorisation results as a count per category.

        Args:
            categorized: Output of :meth:`classify`.

        Returns:
            ``{ category_name: file_count, … }``
        """
        return {cat: len(files) for cat, files in categorized.items()}
