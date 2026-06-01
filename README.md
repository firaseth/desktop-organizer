# 🗂️ Desktop File Organizer
![organizer.png ](‪D:\Desktop\organizer.png)

A safe, zero-dependency CLI tool that automatically sorts files into typed
sub-folders — images, documents, videos, audio, code, and more — with
full undo support and automatic scheduling every 6 hours.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python)
![Tests](https://img.shields.io/badge/tests-53%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Table of Contents

- [Features](#-features)
- [Project Structure](#-project-structure)
- [Quick Start](#-quick-start)
- [Usage](#-usage)
- [Auto-Run Every 6 Hours](#-auto-run-every-6-hours)
- [Default Categories](#-default-categories)
- [Custom Configuration](#-custom-configuration)
- [Undo](#-undo)
- [Running Tests](#-running-tests)
- [Safety Defaults](#-safety-defaults)
- [License](#-license)

---

## ✨ Features

- **Preview mode** — see every planned move before anything is touched
- **Copy by default** — originals never deleted unless you choose `--mode move`
- **Smart duplicate handling** — rename, skip, or overwrite on collision
- **Full undo** — every run writes a JSON log; replay it in reverse anytime
- **Recursive scanning** — flattens nested sub-folders back into root categories
- **One-command scheduling** — `--schedule` installs the 6-hour auto-run on your OS automatically
- **Zero dependencies** — pure Python standard library (3.8+)

---

## 📁 Project Structure
desktop-organizer/
├── organize.py           # CLI entry point
├── scanner.py            # Directory scanning
├── classifier.py         # Extension → category mapping
├── organizer.py          # Copy / move / undo execution
├── logger.py             # JSON + CSV action logging
├── config.py             # Configuration loader
├── utils.py              # Shared helpers
├── default_config.json   # Built-in category rules
├── requirements.txt
└── tests/
    ├── __init__.py
    └── test_organizer.py # 53 unit tests
    ---
    ## 🚀 Quick Start
    ---

## 🚀 Quick Start

No installation required — just Python 3.8 or later.

```bash
git clone https://github.com/firaseth/desktop-organizer.git
cd desktop-organizer

# Safe preview — nothing is changed
python organize.py ~/Desktop --preview

# Organise (copy mode — originals kept)
python organize.py ~/Desktop

# Organise and remove originals
python organize.py ~/Desktop --mode move

# Install auto-run every 6 hours (detects your OS automatically)
python organize.py ~/Desktop --schedule
```

---

## 🔧 Usage
----
## 🔧 Usage
# ─── PREVIEW (safe, no changes) ───────────────────────────────────────
python organize.py ~/Desktop --preview

# ─── BASIC ORGANISE (copy mode, originals kept) ───────────────────────
python organize.py ~/Desktop

# ─── MOVE MODE (removes originals) ───────────────────────────────────
python organize.py ~/Desktop --mode move

# ─── RECURSIVE (pull files from ALL sub-folders) ──────────────────────
python organize.py ~/Desktop --recursive

# ─── RECURSIVE + MOVE (full deep clean) ──────────────────────────────
python organize.py ~/Desktop --recursive --mode move

# ─── CUSTOM OUTPUT FOLDER ────────────────────────────────────────────
python organize.py ~/Desktop --output ~/Sorted

# ─── CUSTOM CONFIG FILE ──────────────────────────────────────────────
python organize.py ~/Desktop --config my_rules.json

# ─── DUPLICATE STRATEGIES ────────────────────────────────────────────
python organize.py ~/Desktop --duplicate-strategy rename     # default: add _1 _2
python organize.py ~/Desktop --duplicate-strategy skip       # leave duplicates alone
python organize.py ~/Desktop --duplicate-strategy overwrite  # replace existing

# ─── EXPORT CSV LOG ──────────────────────────────────────────────────
python organize.py ~/Desktop --export-csv

# ─── UNDO LAST RUN ───────────────────────────────────────────────────
python organize.py --undo ~/Desktop/organized/organize_log_20260601_060000.json

# ─── AUTO-RUN EVERY 6 HOURS (install once) ───────────────────────────
python organize.py ~/Desktop --schedule

# ─── AUTO-RUN WITH FULL CLEAN OPTIONS ────────────────────────────────
python organize.py ~/Desktop --recursive --mode move --schedule

# ─── REMOVE AUTO-RUN ─────────────────────────────────────────────────
python organize.py --unschedule

# ─── COMBINE OPTIONS (recommended daily setup) ───────────────────────
python organize.py ~/Desktop \
  --recursive \
  --mode move \
  --output ~/Desktop/organized \
  --duplicate-strategy rename \
  --export-csv

  ### Options

| Flag | Description |
|---|---|
| `-o`, `--output DIR` | Output directory (default: `<source>/organized`) |
| `-r`, `--recursive` | Scan sub-directories recursively |
| `-m`, `--mode copy\|move` | Operation mode (default: `copy`) |
| `-p`, `--preview` | Show planned actions without making changes |
| `--dry-run` | Alias for `--preview` |
| `-c`, `--config FILE` | Path to a custom JSON config file |
| `-d`, `--duplicate-strategy` | `rename` (default) · `skip` · `overwrite` |
| `--export-csv` | Write a CSV log alongside the JSON log |
| `--undo LOG_FILE` | Undo a previous run from its log file |
| `--schedule` | Install 6-hour auto-run scheduler for your OS |
| `--unschedule` | Remove the auto-run scheduler |
| `-v`, `--verbose` | Print full stack traces on errors |

### Examples

```bash
# Preview with individual file mappings
python organize.py ~/Desktop --preview

# Recursive clean — pulls ALL sub-folder files into root categories
python organize.py ~/Desktop --recursive --mode move --output ~/Desktop

# Install scheduler — runs automatically every 6 hours from now on
python organize.py ~/Desktop --schedule

# Remove the scheduler
python organize.py ~/Desktop --unschedule

# Undo the last run
python organize.py --undo ~/Desktop/organized/organize_log_20260601_060000.json
```

---

## ⏰ Auto-Run Every 6 Hours

Run this once and the tool will clean your Desktop automatically every 6 hours:

```bash
python organize.py ~/Desktop --schedule
```

This detects your operating system and installs the appropriate scheduler:

| OS | Method |
|---|---|
| macOS | launchd plist in `~/Library/LaunchAgents/` |
| Linux | systemd user timer (falls back to cron if systemd unavailable) |
| Windows | Task Scheduler via `schtasks` |

To remove the scheduler at any time:

```bash
python organize.py ~/Desktop --unschedule
```

Logs are written to `/tmp/desktop-organizer.log` (macOS/Linux) or
`%TEMP%\desktop-organizer.log` (Windows).

---

## 📂 Default Categories

| Category | Extensions |
|---|---|
| `images` | `.jpg` `.jpeg` `.png` `.gif` `.bmp` `.svg` `.webp` `.heic` `.tiff` |
| `documents` | `.pdf` `.doc` `.docx` `.txt` `.md` `.rtf` `.odt` `.tex` |
| `spreadsheets` | `.xls` `.xlsx` `.csv` `.ods` `.xlsm` |
| `presentations` | `.ppt` `.pptx` `.key` `.odp` |
| `audio` | `.mp3` `.wav` `.flac` `.aac` `.ogg` `.m4a` `.wma` `.opus` |
| `video` | `.mp4` `.avi` `.mkv` `.mov` `.wmv` `.flv` `.webm` `.m4v` |
| `archives` | `.zip` `.rar` `.7z` `.tar` `.gz` `.bz2` `.xz` `.iso` |
| `executables` | `.exe` `.msi` `.app` `.deb` `.rpm` `.dmg` `.apk` |
| `code` | `.py` `.js` `.ts` `.html` `.css` `.java` `.cpp` `.go` `.rs` `.php` |
| `fonts` | `.ttf` `.otf` `.woff` `.woff2` |
| `ebooks` | `.epub` `.mobi` `.azw` `.azw3` |
| `other` | anything unrecognised |

---

## ⚙️ Custom Configuration

Create a JSON file to define your own categories:

```json
{
  "categories": {
    "raw_photos": [".cr2", ".nef", ".arw", ".dng"],
    "design":     [".psd", ".ai", ".sketch", ".fig"],
    "work_docs":  [".pdf", ".docx"]
  },
  "default_mode": "copy",
  "duplicate_strategy": "rename",
  "exclude_patterns": ["*.tmp", ".DS_Store", "desktop.ini"]
}
```

```bash
python organize.py ~/Desktop --config my_rules.json
```

---

## 🔁 Undo

Every run writes a timestamped JSON log to the output folder.

```bash
python organize.py --undo ~/Desktop/organized/organize_log_20260601_060000.json
```

- **Copy** runs: destination copies are deleted, originals untouched.
- **Move** runs: files are moved back to their original locations.

---

## 🧪 Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

53 tests covering: utils, config, scanner, classifier, organizer (copy & move),
duplicate strategies, undo, logging, CSV export, and preview mode.

---

## 🛡️ Safety Defaults

| Behaviour | Default |
|---|---|
| Operation mode | `copy` — originals never removed |
| Duplicate collision | `rename` — appends `_1`, `_2`, … |
| Hidden files | Excluded |
| Symbolic links | Excluded |
| System files | Excluded (`.DS_Store`, `desktop.ini`, `Thumbs.db`) |
| Confirmation prompt | Always shown in interactive mode |

> **Tip:** Always run `--preview` first when organising a directory for the first time.

---

## 📄 License

MIT — free to use, modify, and distribute.
