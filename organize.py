
#!/usr/bin/env python3
"""
Desktop File Organizer – Main CLI
==================================
Organises files in a directory into typed sub-folders.

Quick reference:
    python organize.py ~/Desktop --preview        # safe dry-run
    python organize.py ~/Desktop                  # copy mode
    python organize.py ~/Desktop --mode move      # move mode
    python organize.py ~/Desktop --schedule       # install 6-hour auto-run
    python organize.py ~/Desktop --unschedule     # remove auto-run
    python organize.py --undo organize_log_*.json # undo last run
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
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
# Scheduler  (--schedule / --unschedule)
# ---------------------------------------------------------------------------

TASK_NAME   = "DesktopOrganizer"
PLIST_LABEL = "com.desktoporganizer"
PLIST_PATH  = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"
SYSTEMD_SVC = Path.home() / ".config" / "systemd" / "user" / "desktop-organizer.service"
SYSTEMD_TMR = Path.home() / ".config" / "systemd" / "user" / "desktop-organizer.timer"


def _python_exe() -> str:
    """Return the absolute path to the current Python interpreter."""
    return sys.executable


def _script_path() -> str:
    """Return the absolute path to this script."""
    return str(Path(__file__).resolve())


def _log_path() -> str:
    """Return a platform-appropriate log file path."""
    if platform.system() == "Windows":
        return str(Path(tempfile.gettempdir()) / "desktop-organizer.log")
    return "/tmp/desktop-organizer.log"


def _build_run_args(source_dir: Path, output_dir: Path,
                    mode: str, dup: str, recursive: bool) -> list:
    """Build the argument list used in every scheduled invocation."""
    args = [
        _python_exe(), _script_path(),
        str(source_dir),
        "--output", str(output_dir),
        "--mode", mode,
        "--duplicate-strategy", dup,
    ]
    if recursive:
        args.append("--recursive")
    return args


# ---- macOS ---------------------------------------------------------------

def _schedule_macos(source_dir: Path, output_dir: Path,
                    mode: str, dup: str, recursive: bool) -> int:
    run_args = _build_run_args(source_dir, output_dir, mode, dup, recursive)
    prog_args = "\n".join(f"    <string>{a}</string>" for a in run_args)

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{PLIST_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
{prog_args}
  </array>

  <key>StartInterval</key>
  <integer>21600</integer>

  <key>StandardOutPath</key>
  <string>{_log_path()}</string>

  <key>StandardErrorPath</key>
  <string>{_log_path()}</string>

  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
"""
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(plist, encoding="utf-8")

    # Unload first in case it was previously loaded
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)],
                   capture_output=True)
    result = subprocess.run(["launchctl", "load", str(PLIST_PATH)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR loading plist: {result.stderr.strip()}")
        return 1

    print(f"  ✅  macOS launchd agent installed.")
    print(f"      Plist : {PLIST_PATH}")
    print(f"      Logs  : {_log_path()}")
    print(f"      Runs  : every 6 hours (and once at login)")
    return 0


def _unschedule_macos() -> int:
    if not PLIST_PATH.exists():
        print("  No scheduler found (plist does not exist).")
        return 0
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)],
                   capture_output=True)
    PLIST_PATH.unlink()
    print(f"  ✅  macOS launchd agent removed.")
    return 0


# ---- Linux ---------------------------------------------------------------

def _has_systemd_user() -> bool:
    result = subprocess.run(
        ["systemctl", "--user", "is-system-running"],
        capture_output=True, text=True
    )
    return result.returncode in (0, 1)  # 1 = degraded but running


def _schedule_linux_systemd(source_dir: Path, output_dir: Path,
                             mode: str, dup: str, recursive: bool) -> int:
    run_args = _build_run_args(source_dir, output_dir, mode, dup, recursive)
    exec_line = " ".join(run_args)

    service = f"""[Unit]
Description=Desktop File Organizer

[Service]
Type=oneshot
ExecStart={exec_line}
StandardOutput=journal
StandardError=journal
"""
    timer = """[Unit]
Description=Run Desktop File Organizer every 6 hours

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
"""
    SYSTEMD_SVC.parent.mkdir(parents=True, exist_ok=True)
    SYSTEMD_SVC.write_text(service, encoding="utf-8")
    SYSTEMD_TMR.write_text(timer,   encoding="utf-8")

    cmds = [
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "desktop-organizer.timer"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR running {' '.join(cmd)}: {result.stderr.strip()}")
            return 1

    print(f"  ✅  Linux systemd user timer installed.")
    print(f"      Service : {SYSTEMD_SVC}")
    print(f"      Timer   : {SYSTEMD_TMR}")
    print(f"      Check   : systemctl --user status desktop-organizer.timer")
    print(f"      Logs    : journalctl --user -u desktop-organizer.service -f")
    return 0


def _schedule_linux_cron(source_dir: Path, output_dir: Path,
                          mode: str, dup: str, recursive: bool) -> int:
    run_args = _build_run_args(source_dir, output_dir, mode, dup, recursive)
    cmd_str  = " ".join(run_args)
    cron_line = f"0 */6 * * * {cmd_str} >> {_log_path()} 2>&1\n"

    # Read existing crontab
    existing = subprocess.run(["crontab", "-l"],
                               capture_output=True, text=True)
    current = existing.stdout if existing.returncode == 0 else ""

    # Remove any previous desktop-organizer entry
    lines = [l for l in current.splitlines()
             if "desktop-organizer" not in l and "organize.py" not in l]
    lines.append(cron_line.rstrip())
    new_crontab = "\n".join(lines) + "\n"

    proc = subprocess.run(["crontab", "-"], input=new_crontab,
                           capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"  ERROR updating crontab: {proc.stderr.strip()}")
        return 1

    print(f"  ✅  Linux cron job installed.")
    print(f"      Schedule : every 6 hours (0 */6 * * *)")
    print(f"      Logs     : {_log_path()}")
    print(f"      View     : crontab -l")
    return 0


def _unschedule_linux() -> int:
    removed_any = False

    # systemd
    if SYSTEMD_TMR.exists() or SYSTEMD_SVC.exists():
        subprocess.run(["systemctl", "--user", "disable", "--now",
                        "desktop-organizer.timer"], capture_output=True)
        for f in (SYSTEMD_TMR, SYSTEMD_SVC):
            if f.exists():
                f.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                       capture_output=True)
        print("  ✅  systemd user timer removed.")
        removed_any = True

    # cron
    existing = subprocess.run(["crontab", "-l"],
                               capture_output=True, text=True)
    if existing.returncode == 0:
        lines = [l for l in existing.stdout.splitlines()
                 if "desktop-organizer" not in l and "organize.py" not in l]
        new_crontab = "\n".join(lines) + "\n" if lines else ""
        subprocess.run(["crontab", "-"], input=new_crontab,
                       capture_output=True, text=True)
        print("  ✅  cron entry removed (if it existed).")
        removed_any = True

    if not removed_any:
        print("  No scheduler entries found.")
    return 0


# ---- Windows -------------------------------------------------------------

def _schedule_windows(source_dir: Path, output_dir: Path,
                      mode: str, dup: str, recursive: bool) -> int:
    log      = _log_path()
    bat_path = Path(os.environ.get("APPDATA", "C:\\Users\\Public")) \
               / "desktop-organizer" / "run.bat"
    bat_path.parent.mkdir(parents=True, exist_ok=True)

    # Build the command line for the batch file
    rec_flag = " --recursive" if recursive else ""
    bat_content = (
        f'@echo off\n'
        f'"{_python_exe()}" "{_script_path()}" '
        f'"{source_dir}" '
        f'--output "{output_dir}" '
        f'--mode {mode} '
        f'--duplicate-strategy {dup}'
        f'{rec_flag} >> "{log}" 2>&1\n'
    )
    bat_path.write_text(bat_content, encoding="utf-8")

    # Delete old task silently (ignore error if it doesn't exist)
    subprocess.run(
        f'schtasks /Delete /TN "{TASK_NAME}" /F',
        shell=True, capture_output=True
    )

    # Create new task using the batch file
    create_cmd = (
        f'schtasks /Create /TN "{TASK_NAME}" '
        f'/TR "{bat_path}" '
        f'/SC HOURLY /MO 6 '
        f'/RL HIGHEST /F'
    )
    result = subprocess.run(create_cmd, shell=True,
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip() or result.stdout.strip()}")
        return 1

    print(f"  ✅  Windows Task Scheduler task '{TASK_NAME}' installed.")
    print(f"      Batch : {bat_path}")
    print(f"      Runs  : every 6 hours")
    print(f"      Logs  : {log}")
    print(f"      View  : schtasks /Query /TN \"{TASK_NAME}\" /FO LIST")
    return 0


def _unschedule_windows() -> int:
    result = subprocess.run(
        f'schtasks /Delete /TN "{TASK_NAME}" /F',
        shell=True, capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"  ✅  Windows Task Scheduler task '{TASK_NAME}' removed.")
    else:
        print(f"  Task '{TASK_NAME}' not found (nothing to remove).")
    return 0


# ---- Public dispatcher ---------------------------------------------------

def install_schedule(source_dir: Path, output_dir: Path,
                     mode: str, dup: str, recursive: bool) -> int:
    """Install the 6-hour scheduler for the current OS."""
    _banner("Install Auto-Scheduler")
    print(f"  Source  : {source_dir}")
    print(f"  Output  : {output_dir}")
    print(f"  Mode    : {mode}")
    print(f"  Every   : 6 hours\n")

    system = platform.system()
    if system == "Darwin":
        return _schedule_macos(source_dir, output_dir, mode, dup, recursive)
    elif system == "Linux":
        if _has_systemd_user():
            return _schedule_linux_systemd(source_dir, output_dir,
                                           mode, dup, recursive)
        else:
            return _schedule_linux_cron(source_dir, output_dir,
                                        mode, dup, recursive)
    elif system == "Windows":
        return _schedule_windows(source_dir, output_dir, mode, dup, recursive)
    else:
        print(f"  ERROR: Unsupported OS '{system}'.")
        return 1


def remove_schedule() -> int:
    """Remove the 6-hour scheduler for the current OS."""
    _banner("Remove Auto-Scheduler")
    system = platform.system()
    if system == "Darwin":
        return _unschedule_macos()
    elif system == "Linux":
        return _unschedule_linux()
    elif system == "Windows":
        return _unschedule_windows()
    else:
        print(f"  ERROR: Unsupported OS '{system}'.")
        return 1


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

    def run(self, args: argparse.Namespace) -> int:
        """Execute the organiser with the parsed *args*."""

        # ---- Undo --------------------------------------------------------
        if args.undo:
            return self._handle_undo(args.undo)

        # ---- Validate source directory -----------------------------------
        source_dir = validate_path(args.source_dir)
        if not source_dir or not source_dir.is_dir():
            print(f"Error: '{args.source_dir}' is not a valid directory.")
            return 1

        # ---- Configuration -----------------------------------------------
        config_path = Path(args.config) if args.config else None
        self.config = Config(config_path)

        # ---- Output directory --------------------------------------------
        output_dir = Path(args.output) if args.output else source_dir / "organized"

        # ---- Mode & duplicate strategy -----------------------------------
        mode      = args.mode               or self.config.default_mode
        dup_strat = args.duplicate_strategy or self.config.duplicate_strategy

        # ---- Schedule / unschedule (no file ops needed) ------------------
        if args.unschedule:
            return remove_schedule()

        if args.schedule:
            return install_schedule(
                source_dir, output_dir,
                mode, dup_strat, args.recursive
            )

        # ---- Component setup ---------------------------------------------
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

        # ---- Header ------------------------------------------------------
        _banner("Desktop File Organizer")
        print(f"  Source : {source_dir}")
        print(f"  Output : {output_dir}")
        print(f"  Mode   : {mode}")
        print(f"  Dupes  : {dup_strat}")

        # ---- Scan --------------------------------------------------------
        print("\n[Scanning] …")
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

        # ---- Classify ----------------------------------------------------
        categorized      = self.classifier.classify(files)
        category_summary = self.classifier.get_summary(categorized)

        # ---- Category overview -------------------------------------------
        self._display_category_overview(category_summary, output_dir, mode)

        # ---- Preview / dry-run -------------------------------------------
        if args.preview or args.dry_run:
            print("\n[Preview] Individual file mappings:")
            self.organizer.organize(categorized, preview=True)
            print("\n[Preview] No files were modified.")
            return 0

        # ---- Confirmation ------------------------------------------------
        if not self._confirm():
            print("\nOperation cancelled.")
            return 0

        # ---- Execute -----------------------------------------------------
        print(f"\n[Organising] {mode.capitalize()}ing files …")
        stats = self.organizer.organize(categorized, preview=False)

        if self.organizer.conflicts:
            self._display_conflicts(self.organizer.conflicts)

        # ---- Persist log -------------------------------------------------
        self.logger.save()

        if args.export_csv:
            csv_path = output_dir / f"organize_log_{int(time.time())}.csv"
            self.logger.export_csv(csv_path)
            print(f"\n  CSV log: {csv_path}")

        # ---- Summary -----------------------------------------------------
        elapsed = time.time() - start_time
        self._display_summary(stats, self.logger.get_summary(), elapsed)

        print(f"\n  Log  : {self.logger.log_file}")
        print(f"  Undo : python organize.py --undo {self.logger.log_file}")

        return 0

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _display_category_overview(self, summary: Dict,
                                    output_dir: Path, mode: str) -> None:
        print(f"\n[Plan] Category overview ({mode} mode):")
        print(f"  Destination: {output_dir}\n")
        for category, count in sorted(summary.items(), key=lambda x: -x[1]):
            print(f"  {category:15s}  {count:4d} file(s)"
                  f"  →  {output_dir.name}/{category}/")

    def _display_conflicts(self, conflicts: list) -> None:
        shown = conflicts[:15]
        print(f"\n[Conflicts] {len(conflicts)} naming conflict(s):")
        for c in shown:
            action = c["action"]
            if action == "renamed":
                print(f"  • {c['original'].name}  →  {c['renamed'].name}")
            elif action == "skipped":
                print(f"  • {c['destination'].name}  (skipped – already exists)")
            elif action == "overwritten":
                print(f"  • {c['destination'].name}  (overwritten)")
            else:
                print(f"  • {c.get('source', '?').name}  ({action})")
        if len(conflicts) > 15:
            print(f"  … and {len(conflicts) - 15} more (see log)")

    def _display_summary(self, stats: dict, log_summary: dict,
                          elapsed: float) -> None:
        _banner("Organisation Complete")
        print(f"  Processed : {stats['total']}")
        print(f"  Successful: {stats['successful']}")
        print(f"  Skipped   : {stats['skipped']}")
        print(f"  Failed    : {stats['failed']}")
        if log_summary["categories"]:
            print("\n  By category:")
            for cat, count in sorted(log_summary["categories"].items(),
                                     key=lambda x: -x[1]):
                print(f"    {cat:15s}  {count:4d}")
        print(f"\n  Total size: {format_size(log_summary['total_size'])}")
        print(f"  Duration  : {elapsed:.2f}s")

    def _confirm(self) -> bool:
        try:
            return input("\nProceed with organisation? [y/N]: ").strip().lower() \
                   in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            print()
            return False

    def _handle_undo(self, log_file: str) -> int:
        log_path = Path(log_file)
        if not log_path.exists():
            print(f"Error: Log file not found: {log_file}")
            return 1

        _banner("Undo File Organisation")
        print(f"  Log: {log_path}")

        try:
            response = input("\nThis will restore files to their original "
                             "locations. Continue? [y/N]: ")
            if response.strip().lower() not in ("y", "yes"):
                print("Undo cancelled.")
                return 0
        except (KeyboardInterrupt, EOFError):
            print("\nUndo cancelled.")
            return 0

        organizer = FileOrganizer(Path.cwd(), mode="move")
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
    bar = "=" * 60
    print(f"\n{bar}\n  {title}\n{bar}")


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
  python organize.py ~/Desktop --schedule          # install 6-hour auto-run
  python organize.py ~/Desktop --unschedule        # remove auto-run
  python organize.py --undo organize_log_*.json    # undo last run
        """,
    )

    parser.add_argument("source_dir", nargs="?",
                        help="Directory to organise.")
    parser.add_argument("-o", "--output",
                        help="Output directory (default: <source>/organized).")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Scan sub-directories recursively.")
    parser.add_argument("-m", "--mode", choices=["copy", "move"],
                        help="Operation mode: 'copy' (default) or 'move'.")
    parser.add_argument("-p", "--preview", action="store_true",
                        help="Show planned actions without making any changes.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Alias for --preview.")
    parser.add_argument("-c", "--config",
                        help="Path to a custom JSON configuration file.")
    parser.add_argument("-d", "--duplicate-strategy",
                        dest="duplicate_strategy",
                        choices=["rename", "skip", "overwrite"],
                        help="How to handle filename collisions (default: rename).")
    parser.add_argument("--export-csv", action="store_true",
                        help="Write an additional CSV log alongside the JSON log.")
    parser.add_argument("--undo", metavar="LOG_FILE",
                        help="Undo operations recorded in the given log file.")
    parser.add_argument("--schedule", action="store_true",
                        help="Install 6-hour auto-run scheduler for your OS "
                             "(macOS: launchd, Linux: systemd/cron, Windows: Task Scheduler).")
    parser.add_argument("--unschedule", action="store_true",
                        help="Remove the auto-run scheduler.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print stack traces on unexpected errors.")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = _build_parser()
    args   = parser.parse_args()

    # --unschedule needs no source_dir
    if args.unschedule and not args.source_dir:
        return remove_schedule()

    if not args.undo and not args.source_dir:
        parser.print_help()
        return 1

    cli = FileOrganizerCLI()
    try:
        return cli.run(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        return 1
    except Exception as exc:
        print(f"\nUnexpected error: {exc}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
