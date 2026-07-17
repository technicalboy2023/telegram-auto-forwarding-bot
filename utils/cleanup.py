"""
Auto-cleanup scheduler for the Telegram Auto-Forwarding Bot.

Runs every CLEANUP_INTERVAL_HOURS hours (default 24):
  1.  prunes forward_history rows older than HISTORY_RETENTION_DAYS (default 30)
  2.  VACUUMs the SQLite database to reclaim disk space
  3.  removes orphaned log files older than LOG_RETENTION_DAYS (default 7)
  4.  deletes project-level __pycache__/ directories and stray *.pyc
  5.  deletes common temp/auto-generated files (*.tmp, *~, .DS_Store, *.bak, *.swp)

SAFETY GUARANTEES
-----------------
A hard-coded ``PROTECTED_FILE_NAMES`` set and ``PROTECTED_DIR_NAMES`` set are
checked on every path before deletion.  The bot cannot accidentally delete:
  - bot_data.db  /  bot_data.db-wal  /  bot_data.db-shm
  - userbot_session.session  /  userbot_session.session-journal
  - config.json  /  .env  /  .env.example
  - venv/  /  .venv/  /  .git/  /  site-packages/
  - the currently-active log (bot.log) and its rotating backups
  - the entire logs/ directory root

Each cleanup step is wrapped in try/except so a single failure cannot
prevent later steps from running, and asyncio.CancelledError is
re-raised cleanly so shutdown is graceful.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)


# ════════════════════════════════════════════════════════════════════════════
#  Configuration (env-overridable; sane defaults for LOW_RAM environments)
# ════════════════════════════════════════════════════════════════════════════

HISTORY_RETENTION_DAYS: int = int(os.environ.get("HISTORY_RETENTION_DAYS", "7"))  # Keep only 7 days of DB history
LOG_RETENTION_DAYS: int = int(os.environ.get("LOG_RETENTION_DAYS", "7"))      # Keep only 7 days of logs
# Note: We run the scanner every 24 hours, but it only deletes data older than 7 days.
# This prevents the issue where a server restart resets a 7-day timer.
CLEANUP_INTERVAL_HOURS: int = int(os.environ.get("CLEANUP_INTERVAL_HOURS", "24"))
_no_cleanup_raw = os.environ.get("NO_CLEANUP", "").strip().lower()
DISABLE_CLEANUP: bool = _no_cleanup_raw not in ("", "0", "false", "no")

# Project root is the parent of utils/.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
LOGS_DIR: Path = PROJECT_ROOT / "logs"


# ════════════════════════════════════════════════════════════════════════════
#  Hard-coded safety exclusions — NEVER delete anything matching these
# ════════════════════════════════════════════════════════════════════════════

# File names that must never be deleted
PROTECTED_FILE_NAMES: frozenset[str] = frozenset(
    {
        "bot_data.db",
        "bot_data.db-wal",
        "bot_data.db-shm",
        "userbot_session.session",
        "userbot_session.session-journal",
        "config.json",
        ".env",
        ".env.example",
        ".gitignore",
        # currently active log + RotatingFileHandler-managed backups
        "bot.log",
        "bot.log.1",
        "bot.log.2",
        "bot.log.3",
        "bot.log.4",
        "bot.log.5",
    }
)

# Directory names that must never be touched (neither removed nor descended into)
PROTECTED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        "venv",
        ".venv",
        "site-packages",
    }
)

# File globs considered "temp / auto-generated" — safe to delete if matched
TEMP_FILE_PATTERNS: tuple[str, ...] = (
    "*.tmp",
    "*~",
    "*.bak",
    "*.swp",
    ".DS_Store",
)


# ════════════════════════════════════════════════════════════════════════════
#  Cleanup report
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class CleanupReport:
    """Result of one cleanup pass. All counters are zero on a no-op run."""

    history_rows_pruned: int = 0
    db_vacuumed: bool = False
    pycache_dirs_removed: int = 0
    pyc_files_removed: int = 0
    orphan_logs_removed: int = 0
    temp_files_removed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def summary(self) -> str:
        parts: list[str] = []
        if self.history_rows_pruned:
            parts.append(f"history={self.history_rows_pruned}")
        if self.db_vacuumed:
            parts.append("vacuumed")
        if self.pycache_dirs_removed or self.pyc_files_removed:
            parts.append(
                f"pycache={self.pycache_dirs_removed}d/{self.pyc_files_removed}f"
            )
        if self.orphan_logs_removed:
            parts.append(f"orphan_logs={self.orphan_logs_removed}")
        if self.temp_files_removed:
            parts.append(f"temp_files={self.temp_files_removed}")
        if self.errors:
            parts.append(f"errors={self.error_count}")
        return ", ".join(parts) if parts else "(nothing to clean)"


# ════════════════════════════════════════════════════════════════════════════
#  Scheduler
# ════════════════════════════════════════════════════════════════════════════


class CleanupScheduler:
    """
    Periodic and one-shot cleanup driver.

    Usage:
        scheduler = CleanupScheduler(db)
        # One-shot (synchronous, safe to call from main() before asyncio.run):
        report = scheduler.run_full_cleanup()
        logger.info("Cleanup: %s", report.summary())

        # Periodic (asyncio, called from inside the bot's event loop):
        task = asyncio.create_task(scheduler.run_periodically(shutdown_event))
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    # ──────────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────────

    def run_full_cleanup(self) -> CleanupReport:
        """
        Run all cleanup stages synchronously. Each stage is wrapped in
        try/except so a single failure cannot abort the others.

        Safe to call from main() before asyncio.run(). Safe to call
        multiple times (idempotent — only deletes what's actually stale).
        """
        report = CleanupReport()

        # 1. Forward history + VACUUM ----------------------------------
        try:
            pruned = self.db.prune_history(HISTORY_RETENTION_DAYS)
            report.history_rows_pruned = pruned

            # Clean up dedup window
            dedup_pruned = self.db.cleanup_dedup_window()

            if pruned > 0 or dedup_pruned > 0:
                # Only VACUUM when we actually deleted something
                self.db.vacuum()
                report.db_vacuumed = True
        except Exception as e:
            logger.error("History cleanup failed: %s", e, exc_info=True)
            report.errors.append(f"history: {e}")

        # 2. __pycache__ / stray .pyc ----------------------------------
        try:
            d, f = self._cleanup_pycache()
            report.pycache_dirs_removed = d
            report.pyc_files_removed = f
        except Exception as e:
            logger.error("pycache cleanup failed: %s", e, exc_info=True)
            report.errors.append(f"pycache: {e}")

        # 3. Orphaned log files (older than LOG_RETENTION_DAYS) --------
        try:
            report.orphan_logs_removed = self._cleanup_orphan_logs()
        except Exception as e:
            logger.error("log cleanup failed: %s", e, exc_info=True)
            report.errors.append(f"logs: {e}")

        # 4. Temp / auto-generated files ------------------------------
        try:
            report.temp_files_removed = self._cleanup_temp_files()
        except Exception as e:
            logger.error("temp cleanup failed: %s", e, exc_info=True)
            report.errors.append(f"temp: {e}")

        return report

    async def run_periodically(self, shutdown_event: asyncio.Event) -> None:
        """
        Awaitable coroutine to be wrapped in asyncio.create_task().

        Sleeps CLEANUP_INTERVAL_HOURS seconds, then runs run_full_cleanup()
        inside asyncio.to_thread() so the blocking file/DB work does not
        freeze the event loop. Returns cleanly on CancelledError or when
        shutdown_event is set, so other tasks can finish.
        """
        if DISABLE_CLEANUP:
            logger.info("Auto-cleanup disabled (NO_CLEANUP env var).")
            return

        interval_seconds = CLEANUP_INTERVAL_HOURS * 3600
        logger.info(
            "Auto-cleanup scheduler running every %d hour(s) (history=%dd, logs=%dd).",
            CLEANUP_INTERVAL_HOURS,
            HISTORY_RETENTION_DAYS,
            LOG_RETENTION_DAYS,
        )

        try:
            while not shutdown_event.is_set():
                # Sleep until either the interval elapses OR shutdown sets.
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(), timeout=interval_seconds
                    )
                    # Shutdown was set — exit cleanly.
                    break
                except asyncio.TimeoutError:
                    pass  # interval elapsed; run cleanup below

                # Run blocking cleanup in a worker thread so the event
                # loop (PTB polling + Telethon) stays responsive.
                try:
                    report = await asyncio.to_thread(self.run_full_cleanup)
                    logger.info("Auto-cleanup: %s", report.summary())
                except Exception as e:
                    logger.error("Auto-cleanup pass failed: %s", e, exc_info=True)
        except asyncio.CancelledError:
            # Main loop is being torn down — exit quietly.
            logger.info("Auto-cleanup cancelled (shutdown).")
            raise

    # ──────────────────────────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_protected_dir(path: Path) -> bool:
        """True if any portion of *path* matches a protected directory name."""
        return any(part in PROTECTED_DIR_NAMES for part in path.parts)

    @staticmethod
    def _is_protected_file(name: str) -> bool:
        return name in PROTECTED_FILE_NAMES

    def _cleanup_pycache(self) -> Tuple[int, int]:
        """
        Remove __pycache__/ directories and stray *.pyc files under
        PROJECT_ROOT. Descends into subdirs but stops at protected dirs
        (venv, .git, site-packages). Returns (dirs_removed, files_removed).
        """
        dirs_to_remove: list[Path] = []
        files_to_remove: list[Path] = []

        # topdown=True — prune the dirs list to never walk protected trees.
        for root, dirs, files in os.walk(PROJECT_ROOT, topdown=True):
            root_path = Path(root)

            # Skip walking into any directory in PROTECTED_DIR_NAMES (shared helper).
            # __pycache__ is also filtered below so we never descend into it.
            if self._is_protected_dir(root_path):
                dirs[:] = []
                continue

            # Drop protected subtrees from os.walk and queue __pycache__ for removal.
            for d in list(dirs):
                if d in PROTECTED_DIR_NAMES or d == "__pycache__":
                    dirs.remove(d)
                    if d == "__pycache__":
                        dirs_to_remove.append(root_path / "__pycache__")

            # Stray *.pyc at project level (rare — usually inside __pycache__).
            for fname in files:
                if fname.endswith(".pyc") and fname != "__pycache__":
                    files_to_remove.append(root_path / fname)

        # Pass 2: actually delete.
        dirs_removed = 0
        for d in dirs_to_remove:
            try:
                shutil.rmtree(d, ignore_errors=True)
                dirs_removed += 1
                logger.debug("Removed __pycache__: %s", d)
            except OSError as e:
                logger.warning("Failed to remove %s: %s", d, e)

        files_removed = 0
        for f in files_to_remove:
            try:
                f.unlink()
                files_removed += 1
                logger.debug("Removed stray pyc: %s", f)
            except OSError as e:
                logger.warning("Failed to remove %s: %s", f, e)

        return dirs_removed, files_removed

    def _cleanup_orphan_logs(self) -> int:
        """
        Delete *.log / *.log.N files in LOGS_DIR whose mtime is older
        than LOG_RETENTION_DAYS. The active bot.log and its rotating
        backups (managed by RotatingFileHandler itself) are hard-coded
        as protected and never deleted here.
        """
        if not LOGS_DIR.exists():
            return 0

        cutoff = time.time() - LOG_RETENTION_DAYS * 86400
        removed = 0
        try:
            entries = list(LOGS_DIR.iterdir())
        except OSError as e:
            logger.warning("Cannot list %s: %s", LOGS_DIR, e)
            return 0

        for entry in entries:
            name = entry.name
            if self._is_protected_file(name):
                continue
            if not (
                name.endswith(".log")
                or name.endswith(".log.gz")
                or name.endswith(".log.1")
                or name.endswith(".log.2")
            ):
                # Only target log-shaped files, never random files in logs/.
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            if mtime >= cutoff:
                continue
            try:
                if entry.is_file():
                    entry.unlink()
                    removed += 1
                    logger.debug("Removed orphan log: %s", name)
            except OSError as e:
                logger.warning("Failed to remove %s: %s", name, e)
        return removed

    def _cleanup_temp_files(self) -> int:
        """
        Delete files matching TEMP_FILE_PATTERNS (*.tmp, *~, .DS_Store,
        *.bak, *.swp) under PROJECT_ROOT, skipping protected directories.
        """
        removed = 0
        for root, dirs, files in os.walk(PROJECT_ROOT, topdown=True):
            root_path = Path(root)
            if self._is_protected_dir(root_path):
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if d not in PROTECTED_DIR_NAMES]

            for fname in files:
                if not any(fnmatch.fnmatch(fname, pat) for pat in TEMP_FILE_PATTERNS):
                    continue
                if self._is_protected_file(fname):
                    continue
                fpath = root_path / fname
                try:
                    fpath.unlink()
                    removed += 1
                    logger.debug("Removed temp file: %s", fpath)
                except OSError as e:
                    logger.warning("Failed to remove %s: %s", fpath, e)
        return removed
