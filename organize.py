#!/usr/bin/env python3
"""
Desktop File Organizer – Main CLI
==================================
Organises files in a directory into typed sub-folders.

Usage (quick reference):

    # Safe preview – no files are changed
    python organize.py ~/Desktop --preview

    # Organise (copy mode, default)
    python organize.py ~/Desktop

    # Move files instead of copying
    python organize.py ~/Desktop --mode move

    # Undo a previous run
    python organize.py --undo organize_log_20241201_143022.json

Run ``python organize.py --help`` for the full option list.

Fix vs. original:
    Preview mode now calls ``organizer.organize(preview=True)`` so that
    *individual* file → destination mappings are shown, not just category
    counts.
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Dict, Optional

from config import Config
from scanner import DirectoryScanner
from classifier import FileClassifier
from organizer import FileOrganizer
from logger import ActionLogger
from utils import validate_path, format_size


# ---------------------------------------------------------------------------
# CLI controller
# ---------------------------------------------------------------------------

class FileOrganizerCLI:
    """Wires the individual components together and drives the CLI workflow."""

    def __init__(self):
        self.config:     Optional[Config]           = None
        self.scanner:    Optional[DirectoryScanner] = None
        self.classifier: Optional[FileClassifier]   = None
        self.organizer:  Optional[FileOrganizer]    = None
        self.logger:     Optional[ActionLogger]     = None

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, args: argparse.Namespace) -> int:
        """
        Execute the organiser with the parsed *args*.

        Returns:
            Exit code – 0 on success, 1 on error / cancelled.
        """
        if args.undo:
            return self._handle_undo(args.undo)

        # ---- Validate source directory --------------------------------
        source_dir = validate_path(args.source_dir)
        if not source_dir or not source_dir.is_dir():
            print(f"Error: '{args.source_dir}' is not a valid directory.")
            return 1

        # ---- Configuration --------------------------------------------
        config_path = Path(args.config) if args.config else None
        self.config = Config(config_path)

        # ---- Output directory -----------------------------------------
        output_dir = Path(args.output) if args.output else source_dir / 'organized'

        # ---- Mode & duplicate strategy --------------------------------
        mode     = args.mode               or self.config.default_mode
        dup_strat = args.duplicate_strategy or self.config.duplicate_strategy

        # ---- Component setup ------------------------------------------
        self.scanner    = DirectoryScanner(
            exclude_patterns=self.config.exclude_patterns,
            include_hidden=False,
        )
        self.classifier = FileClassifier(self.config)
        self.logger     = ActionLogger(output_dir)
        self.logger.create_log()
        self.organizer  = FileOrganizer(
            output_dir=output_dir,
            mode=mode,
            duplicate_strategy=dup_strat,
            logger=self.logger,
        )

        # ---- Header ---------------------------------------------------
        _banner("Desktop File Organizer")
        print(f"  Source : {source_dir}")
        print(f"  Output : {output_dir}")
        print(f"  Mode   : {mode}")
        print(f"  Dupes  : {dup_strat}")

        # ---- Scan -----------------------------------------------------
        print(f"\n[Scanning] …")
        start_time = time.time()
        files = self.scanner.scan(source_dir, recursive=args.recursive)

        if not files:
            print("  No files found to organise.")
            return 0

        scan_stats = self.scanner.get_stats(files)
        print(
            f"  Found {scan_stats['total_files']} file(s) "
            f"({format_size(scan_stats['total_size'])}), "
            f"{scan_stats['unique_extensions']} distinct extension(s)."
        )

        # ---- Classify -------------------------------------------------
        categorized      = self.classifier.classify(files)
        category_summary = self.classifier.get_summary(categorized)

        # ---- Category overview (always shown) -------------------------
        self._display_category_overview(category_summary, output_dir, mode)

        # ---- Preview / dry-run ----------------------------------------
        is_preview = args.preview or args.dry_run

        if is_preview:
            print("\n[Preview] Individual file mappings:")
            self.organizer.organize(categorized, preview=True)
            print("\n[Preview] No files were modified.")
            return 0

        # ---- Confirmation ---------------------------------------------
        if not self._confirm():
            print("\nOperation cancelled.")
            return 0

        # ---- Execute --------------------------------------------------
        print(f"\n[Organising] {mode.capitalize()}ing files …")
        stats = self.organizer.organize(categorized, preview=False)

        if self.organizer.conflicts:
            self._display_conflicts(self.organizer.conflicts)

        # ---- Persist log ----------------------------------------------
        self.logger.save()

        if args.export_csv:
            csv_path = output_dir / f"organize_log_{int(time.time())}.csv"
            self.logger.export_csv(csv_path)
            print(f"\n  CSV log: {csv_path}")

        # ---- Summary --------------------------------------------------
        elapsed = time.time() - start_time
        self._display_summary(stats, self.logger.get_summary(), elapsed)

        print(f"\n  Log  : {self.logger.log_file}")
        print(f"  Undo : python organize.py --undo {self.logger.log_file}")

        return 0

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _display_category_overview(
        self,
        summary: Dict,
        output_dir: Path,
        mode: str,
    ) -> None:
        print(f"\n[Plan] Category overview ({mode} mode):")
        print(f"  Destination: {output_dir}\n")
        for category, count in sorted(summary.items(), key=lambda x: -x[1]):
            print(
                f"  {category:15s}  {count:4d} file(s)"
                f"  →  {output_dir.name}/{category}/"
            )

    def _display_conflicts(self, conflicts: list) -> None:
        shown = conflicts[:15]
        print(f"\n[Conflicts] {len(conflicts)} naming conflict(s):")
        for c in shown:
            action = c['action']
            if action == 'renamed':
                print(f"  • {c['original'].name}  →  {c['renamed'].name}")
            elif action == 'skipped':
                print(f"  • {c['destination'].name}  (skipped – already exists)")
            elif action == 'overwritten':
                print(f"  • {c['destination'].name}  (overwritten)")
            else:
                print(f"  • {c.get('source', '?').name}  ({action})")
        if len(conflicts) > 15:
            print(f"  … and {len(conflicts) - 15} more (see log)")

    def _display_summary(
        self,
        stats: dict,
        log_summary: dict,
        elapsed: float,
    ) -> None:
        _banner("Organisation Complete")
        print(f"  Processed : {stats['total']}")
        print(f"  Successful: {stats['successful']}")
        print(f"  Skipped   : {stats['skipped']}")
        print(f"  Failed    : {stats['failed']}")

        if log_summary['categories']:
            print("\n  By category:")
            for cat, count in sorted(
                log_summary['categories'].items(), key=lambda x: -x[1]
            ):
                print(f"    {cat:15s}  {count:4d}")

        print(f"\n  Total size: {format_size(log_summary['total_size'])}")
        print(f"  Duration  : {elapsed:.2f}s")

    # ------------------------------------------------------------------
    # Interaction helpers
    # ------------------------------------------------------------------

    def _confirm(self) -> bool:
        try:
            return input("\nProceed with organisation? [y/N]: ").strip().lower() in (
                'y', 'yes'
            )
        except (KeyboardInterrupt, EOFError):
            print()
            return False

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    def _handle_undo(self, log_file: str) -> int:
        log_path = Path(log_file)
        if not log_path.exists():
            print(f"Error: Log file not found: {log_file}")
            return 1

        _banner("Undo File Organisation")
        print(f"  Log: {log_path}")

        try:
            response = input(
                "\nThis will restore files to their original locations. "
                "Continue? [y/N]: "
            )
            if response.strip().lower() not in ('y', 'yes'):
                print("Undo cancelled.")
                return 0
        except (KeyboardInterrupt, EOFError):
            print("\nUndo cancelled.")
            return 0

        organizer = FileOrganizer(Path.cwd(), mode='move')
        stats = organizer.undo(log_path)

        _banner("Undo Complete")
        print(f"  Restored: {stats['restored']}")
        print(f"  Failed  : {stats['failed']}")
        print(f"  Skipped : {stats['skipped']}")
        return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _banner(title: str) -> None:
    """Print a simple section banner."""
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Organise files into typed sub-folders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python organize.py ~/Desktop --preview           # safe dry-run
  python organize.py ~/Desktop                     # copy mode (default)
  python organize.py ~/Desktop --mode move         # move mode
  python organize.py ~/Desktop --recursive         # include sub-directories
  python organize.py ~/Desktop --output ~/Sorted   # custom output location
  python organize.py --undo organize_log_*.json    # undo last run
  python organize.py ~/Desktop --config my.json    # custom category rules
        """,
    )

    parser.add_argument(
        'source_dir',
        nargs='?',
        help="Directory to organise.",
    )
    parser.add_argument(
        '-o', '--output',
        help="Output directory (default: <source>/organized).",
    )
    parser.add_argument(
        '-r', '--recursive',
        action='store_true',
        help="Scan sub-directories recursively.",
    )
    parser.add_argument(
        '-m', '--mode',
        choices=['copy', 'move'],
        help="Operation mode: 'copy' (default) or 'move'.",
    )
    parser.add_argument(
        '-p', '--preview',
        action='store_true',
        help="Show planned actions without making any changes.",
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Alias for --preview.",
    )
    parser.add_argument(
        '-c', '--config',
        help="Path to a custom JSON configuration file.",
    )
    parser.add_argument(
        '-d', '--duplicate-strategy',
        dest='duplicate_strategy',
        choices=['rename', 'skip', 'overwrite'],
        help="How to handle filename collisions (default: rename).",
    )
    parser.add_argument(
        '--export-csv',
        action='store_true',
        help="Write an additional CSV log alongside the JSON log.",
    )
    parser.add_argument(
        '--undo',
        metavar='LOG_FILE',
        help="Undo operations recorded in the given log file.",
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help="Print stack traces on unexpected errors.",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = _build_parser()
    args   = parser.parse_args()

    if not args.undo and not args.source_dir:
        parser.print_help()
        return 1

    cli = FileOrganizerCLI()
    try:
        return cli.run(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        print(f"\nUnexpected error: {exc}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
