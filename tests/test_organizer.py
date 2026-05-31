"""
Tests for Desktop File Organizer.

Covers:
- DirectoryScanner       (scan, hidden files, exclude patterns, stats)
- FileClassifier         (known extensions, 'other' fallback)
- Config                 (loading, property defaults, bad file fallback)
- FileOrganizer          (copy, move, duplicate strategies, undo)
- ActionLogger           (log_action with correct file_size for moves,
                          save, load, export_csv, get_summary)
- utils                  (format_size, get_unique_path, sanitize_filename,
                          is_hidden, matches_pattern)
"""

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root is on the Python path.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import Config
from scanner import DirectoryScanner
from classifier import FileClassifier
from organizer import FileOrganizer
from logger import ActionLogger
import utils


# ---------------------------------------------------------------------------
# Base test case with a temporary directory
# ---------------------------------------------------------------------------

class TempDirTestCase(unittest.TestCase):
    """Base class that creates a fresh temporary directory for each test."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers
    def _make_file(self, name: str, content: str = "x") -> Path:
        p = self.tmp / name
        p.write_text(content, encoding="utf-8")
        return p

    def _make_dir(self, name: str) -> Path:
        d = self.tmp / name
        d.mkdir(parents=True, exist_ok=True)
        return d


# ---------------------------------------------------------------------------
# utils
# ---------------------------------------------------------------------------

class TestUtils(unittest.TestCase):

    def test_format_size_bytes(self):
        self.assertEqual(utils.format_size(512), "512.00 B")

    def test_format_size_kb(self):
        self.assertIn("KB", utils.format_size(2048))

    def test_format_size_mb(self):
        self.assertIn("MB", utils.format_size(2 * 1024 * 1024))

    def test_get_unique_path_no_conflict(self):
        p = Path(tempfile.mkdtemp()) / "nonexistent.txt"
        self.assertEqual(utils.get_unique_path(p), p)
        shutil.rmtree(p.parent, ignore_errors=True)

    def test_get_unique_path_with_conflict(self):
        tmp = Path(tempfile.mkdtemp())
        original = tmp / "file.txt"
        original.write_text("a")
        unique = utils.get_unique_path(original)
        self.assertNotEqual(unique, original)
        self.assertFalse(unique.exists())
        shutil.rmtree(tmp, ignore_errors=True)

    def test_sanitize_filename_removes_invalid(self):
        self.assertNotIn('/', utils.sanitize_filename('a/b'))
        self.assertNotIn(':', utils.sanitize_filename('a:b'))

    def test_sanitize_filename_empty_becomes_unnamed(self):
        self.assertEqual(utils.sanitize_filename('...'), 'unnamed')

    def test_is_hidden_dotfile(self):
        self.assertTrue(utils.is_hidden(Path('.hidden')))

    def test_is_hidden_normal(self):
        self.assertFalse(utils.is_hidden(Path('visible.txt')))

    def test_matches_pattern_true(self):
        self.assertTrue(utils.matches_pattern('file.tmp', ['*.tmp']))

    def test_matches_pattern_false(self):
        self.assertFalse(utils.matches_pattern('file.txt', ['*.tmp']))

    def test_matches_pattern_case_insensitive(self):
        self.assertTrue(utils.matches_pattern('FILE.TMP', ['*.tmp']))


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig(TempDirTestCase):

    def test_default_config_loads(self):
        cfg = Config()
        self.assertIn('images', cfg.categories)

    def test_get_category_jpg(self):
        cfg = Config()
        self.assertEqual(cfg.get_category_for_extension('.jpg'), 'images')

    def test_get_category_unknown(self):
        cfg = Config()
        self.assertEqual(cfg.get_category_for_extension('.xyz'), 'other')

    def test_get_category_without_dot(self):
        cfg = Config()
        self.assertEqual(cfg.get_category_for_extension('pdf'), 'documents')

    def test_invalid_config_file_falls_back(self):
        bad = self.tmp / 'bad.json'
        bad.write_text("not json", encoding='utf-8')
        cfg = Config(bad)
        # Should fall back to built-in defaults silently.
        self.assertIsInstance(cfg.categories, dict)

    def test_add_category(self):
        cfg = Config()
        cfg.add_category('raw_images', ['.cr2', '.nef'])
        self.assertEqual(cfg.get_category_for_extension('.cr2'), 'raw_images')

    def test_save_and_reload(self):
        cfg = Config()
        cfg.add_category('test_cat', ['.tst'])
        save_path = self.tmp / 'saved.json'
        cfg.save(save_path)
        cfg2 = Config(save_path)
        self.assertEqual(cfg2.get_category_for_extension('.tst'), 'test_cat')

    def test_default_mode_property(self):
        cfg = Config()
        self.assertIn(cfg.default_mode, ('copy', 'move'))

    def test_duplicate_strategy_property(self):
        cfg = Config()
        self.assertIn(cfg.duplicate_strategy, ('rename', 'skip', 'overwrite'))


# ---------------------------------------------------------------------------
# DirectoryScanner
# ---------------------------------------------------------------------------

class TestDirectoryScanner(TempDirTestCase):

    def _create_test_tree(self):
        self._make_file('a.txt')
        self._make_file('b.jpg')
        self._make_file('.hidden.txt')   # hidden
        sub = self._make_dir('sub')
        (sub / 'c.pdf').write_text('x')

    def test_scan_finds_files(self):
        self._make_file('one.txt')
        self._make_file('two.jpg')
        scanner = DirectoryScanner()
        files = scanner.scan(self.tmp)
        self.assertEqual(len(files), 2)

    def test_scan_excludes_hidden_by_default(self):
        self._make_file('visible.txt')
        self._make_file('.hidden')
        scanner = DirectoryScanner()
        names = [f.name for f in scanner.scan(self.tmp)]
        self.assertNotIn('.hidden', names)
        self.assertIn('visible.txt', names)

    def test_scan_includes_hidden_when_asked(self):
        self._make_file('.dotfile')
        scanner = DirectoryScanner(include_hidden=True)
        names = [f.name for f in scanner.scan(self.tmp)]
        self.assertIn('.dotfile', names)

    def test_scan_excludes_patterns(self):
        self._make_file('good.txt')
        self._make_file('bad.tmp')
        scanner = DirectoryScanner(exclude_patterns=['*.tmp'])
        names = [f.name for f in scanner.scan(self.tmp)]
        self.assertIn('good.txt', names)
        self.assertNotIn('bad.tmp', names)

    def test_scan_non_recursive_skips_subdir_files(self):
        self._create_test_tree()
        scanner = DirectoryScanner()
        files = scanner.scan(self.tmp, recursive=False)
        names = [f.name for f in files]
        self.assertNotIn('c.pdf', names)

    def test_scan_recursive_includes_subdir_files(self):
        self._create_test_tree()
        scanner = DirectoryScanner()
        files = scanner.scan(self.tmp, recursive=True)
        names = [f.name for f in files]
        self.assertIn('c.pdf', names)

    def test_scan_does_not_return_directories(self):
        self._make_dir('subdir')
        scanner = DirectoryScanner()
        files = scanner.scan(self.tmp)
        self.assertTrue(all(f.is_file() for f in files))

    def test_get_stats(self):
        self._make_file('a.txt', 'hello')
        self._make_file('b.txt', 'world')
        scanner = DirectoryScanner()
        files = scanner.scan(self.tmp)
        stats = scanner.get_stats(files)
        self.assertEqual(stats['total_files'], 2)
        self.assertGreater(stats['total_size'], 0)
        self.assertIn('.txt', stats['extensions'])


# ---------------------------------------------------------------------------
# FileClassifier
# ---------------------------------------------------------------------------

class TestFileClassifier(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.classifier = FileClassifier(Config())

    def _path(self, name):
        return self.tmp / name

    def test_jpg_is_image(self):
        self.assertEqual(self.classifier.get_category(self._path('a.jpg')), 'images')

    def test_pdf_is_document(self):
        self.assertEqual(self.classifier.get_category(self._path('a.pdf')), 'documents')

    def test_mp4_is_video(self):
        self.assertEqual(self.classifier.get_category(self._path('a.mp4')), 'video')

    def test_unknown_is_other(self):
        self.assertEqual(self.classifier.get_category(self._path('a.xyz')), 'other')

    def test_classify_groups_correctly(self):
        files = [
            self._path('img.jpg'),
            self._path('doc.pdf'),
            self._path('img2.png'),
        ]
        categorized = self.classifier.classify(files)
        self.assertIn('images', categorized)
        self.assertEqual(len(categorized['images']), 2)
        self.assertEqual(len(categorized['documents']), 1)

    def test_get_summary_counts(self):
        files = [self._path('a.mp3'), self._path('b.wav')]
        categorized = self.classifier.classify(files)
        summary = self.classifier.get_summary(categorized)
        self.assertEqual(summary.get('audio'), 2)


# ---------------------------------------------------------------------------
# FileOrganizer – copy mode
# ---------------------------------------------------------------------------

class TestFileOrganizerCopy(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.output = self.tmp / 'organized'
        self.src_jpg = self._make_file('photo.jpg', 'jpeg-data')
        self.src_pdf = self._make_file('report.pdf', 'pdf-data')

    def _run(self, duplicate_strategy='rename'):
        cfg = Config()
        classifier = FileClassifier(cfg)
        files = [self.src_jpg, self.src_pdf]
        categorized = classifier.classify(files)
        organizer = FileOrganizer(
            self.output, mode='copy',
            duplicate_strategy=duplicate_strategy
        )
        return organizer.organize(categorized), organizer

    def test_creates_output_dir(self):
        self._run()
        self.assertTrue(self.output.exists())

    def test_creates_category_dirs(self):
        self._run()
        self.assertTrue((self.output / 'images').exists())
        self.assertTrue((self.output / 'documents').exists())

    def test_copies_files(self):
        self._run()
        self.assertTrue((self.output / 'images' / 'photo.jpg').exists())
        self.assertTrue((self.output / 'documents' / 'report.pdf').exists())

    def test_originals_preserved_in_copy_mode(self):
        self._run()
        self.assertTrue(self.src_jpg.exists())
        self.assertTrue(self.src_pdf.exists())

    def test_stats_correct(self):
        stats, _ = self._run()
        self.assertEqual(stats['total'], 2)
        self.assertEqual(stats['successful'], 2)
        self.assertEqual(stats['failed'], 0)

    def test_duplicate_rename(self):
        (self.output / 'images').mkdir(parents=True)
        (self.output / 'images' / 'photo.jpg').write_text('old')
        self._run(duplicate_strategy='rename')
        self.assertTrue((self.output / 'images' / 'photo_1.jpg').exists())

    def test_duplicate_skip(self):
        (self.output / 'images').mkdir(parents=True)
        existing = self.output / 'images' / 'photo.jpg'
        existing.write_text('original')
        stats, _ = self._run(duplicate_strategy='skip')
        self.assertEqual(existing.read_text(), 'original')   # unchanged
        self.assertEqual(stats['skipped'], 1)

    def test_duplicate_overwrite(self):
        (self.output / 'images').mkdir(parents=True)
        existing = self.output / 'images' / 'photo.jpg'
        existing.write_text('old-content')
        self._run(duplicate_strategy='overwrite')
        self.assertEqual(existing.read_text(), 'jpeg-data')  # overwritten


# ---------------------------------------------------------------------------
# FileOrganizer – move mode
# ---------------------------------------------------------------------------

class TestFileOrganizerMove(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.src = self._make_file('clip.mp4', 'video-data')
        self.output = self.tmp / 'out'

    def test_move_removes_source(self):
        cfg = Config()
        categorized = FileClassifier(cfg).classify([self.src])
        organizer = FileOrganizer(self.output, mode='move')
        organizer.organize(categorized)
        self.assertFalse(self.src.exists())

    def test_move_destination_has_file(self):
        cfg = Config()
        categorized = FileClassifier(cfg).classify([self.src])
        organizer = FileOrganizer(self.output, mode='move')
        organizer.organize(categorized)
        self.assertTrue((self.output / 'video' / 'clip.mp4').exists())

    def test_logger_records_correct_file_size_after_move(self):
        """Bug fix: file_size must be > 0 even for move operations."""
        cfg = Config()
        categorized = FileClassifier(cfg).classify([self.src])
        logger = ActionLogger(self.output)
        organizer = FileOrganizer(self.output, mode='move', logger=logger)
        organizer.organize(categorized)

        self.assertTrue(logger.actions, "No actions recorded.")
        action = logger.actions[0]
        self.assertEqual(action['status'], 'success')
        self.assertGreater(
            action['file_size'], 0,
            "file_size must be captured before the move removes the source."
        )


# ---------------------------------------------------------------------------
# FileOrganizer – undo
# ---------------------------------------------------------------------------

class TestFileOrganizerUndo(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.src = self._make_file('doc.pdf', 'content')
        self.output = self.tmp / 'out'

    def _organise_and_get_log(self, mode='move'):
        cfg = Config()
        categorized = FileClassifier(cfg).classify([self.src])
        logger = ActionLogger(self.output)
        logger.create_log()
        organizer = FileOrganizer(self.output, mode=mode, logger=logger)
        organizer.organize(categorized)
        logger.save()
        return logger.log_file

    def test_undo_move_restores_source(self):
        log = self._organise_and_get_log(mode='move')
        self.assertFalse(self.src.exists())

        organizer = FileOrganizer(self.tmp, mode='move')
        organizer.undo(log)
        self.assertTrue(self.src.exists())

    def test_undo_copy_removes_destination(self):
        self.src = self._make_file('img.jpg', 'pixels')   # refresh
        log = self._organise_and_get_log(mode='copy')
        dest = self.output / 'images' / 'img.jpg'
        self.assertTrue(dest.exists())

        organizer = FileOrganizer(self.tmp, mode='move')
        organizer.undo(log)
        self.assertFalse(dest.exists())


# ---------------------------------------------------------------------------
# ActionLogger
# ---------------------------------------------------------------------------

class TestActionLogger(TempDirTestCase):

    def test_log_action_records_entry(self):
        log = ActionLogger(self.tmp)
        log.log_action(
            self.tmp / 'a.txt', self.tmp / 'out' / 'a.txt',
            'copy', 'success', 'documents', file_size=100
        )
        self.assertEqual(len(log.actions), 1)
        self.assertEqual(log.actions[0]['file_size'], 100)

    def test_save_and_load_roundtrip(self):
        log = ActionLogger(self.tmp)
        log.create_log()
        log.log_action(
            self.tmp / 'x.py', self.tmp / 'code' / 'x.py',
            'copy', 'success', 'code', file_size=42
        )
        log.save()

        data = ActionLogger.load_log(log.log_file)
        self.assertEqual(data['total_actions'], 1)
        self.assertEqual(data['actions'][0]['category'], 'code')

    def test_export_csv(self):
        log = ActionLogger(self.tmp)
        log.log_action(
            self.tmp / 'a.mp3', self.tmp / 'audio' / 'a.mp3',
            'move', 'success', 'audio', file_size=500
        )
        csv_path = self.tmp / 'out.csv'
        log.export_csv(csv_path)
        self.assertTrue(csv_path.exists())

        with open(csv_path, newline='', encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['category'], 'audio')

    def test_get_summary(self):
        log = ActionLogger(self.tmp)
        log.log_action(
            self.tmp / 'a.jpg', self.tmp / 'images' / 'a.jpg',
            'copy', 'success', 'images', file_size=200
        )
        log.log_action(
            self.tmp / 'b.jpg', self.tmp / 'images' / 'b.jpg',
            'copy', 'failed', 'images', file_size=0, error='Permission denied'
        )
        summary = log.get_summary()
        self.assertEqual(summary['successful'], 1)
        self.assertEqual(summary['failed'], 1)
        self.assertEqual(summary['total_size'], 200)


# ---------------------------------------------------------------------------
# Preview mode (smoke test – no file changes)
# ---------------------------------------------------------------------------

class TestPreviewMode(TempDirTestCase):

    def test_preview_does_not_create_files(self):
        self._make_file('photo.jpg')
        output = self.tmp / 'out'
        cfg = Config()
        scanner = DirectoryScanner()
        classifier = FileClassifier(cfg)
        files = scanner.scan(self.tmp)
        categorized = classifier.classify(files)
        organizer = FileOrganizer(output, mode='copy')
        organizer.organize(categorized, preview=True)
        self.assertFalse(output.exists())


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main(verbosity=2)
