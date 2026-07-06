"""
SQLite database module for the Telegram Auto-Forwarding Bot.

Manages all persistent storage:
- Source channels
- Destination bot
- Replace rules (word -> replacement)
- Block rules (blocked words)
- Settings (header, footer, pause status, forward delay)
- Forward history (for dedup & stats)
"""

import sqlite3
import threading
import hashlib
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent.parent / "bot_data.db"


class Database:
    """
    Thread-safe SQLite database wrapper.

    All state is stored in a single SQLite file. Writes are serialized
    via a reentrant lock; reads use WAL mode for concurrent access.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._lock = threading.RLock()

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        self._set_defaults()
        logger.info("Database initialised at %s", self.db_path)

    # ──────────────────────────────────────────────
    #  Schema
    # ──────────────────────────────────────────────

    def _create_tables(self) -> None:
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS source_channels (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    username    TEXT    NOT NULL UNIQUE,
                    channel_id  INTEGER,
                    added_at    TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS destination (
                    id          INTEGER PRIMARY KEY CHECK (id = 1),
                    username    TEXT    NOT NULL,
                    set_at      TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS replace_rules (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    old_word    TEXT    NOT NULL UNIQUE,
                    new_word    TEXT    NOT NULL DEFAULT '',
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS block_rules (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    word        TEXT    NOT NULL UNIQUE,
                    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key         TEXT    PRIMARY KEY,
                    value       TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS forward_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id   INTEGER NOT NULL,
                    message_hash TEXT   NOT NULL,
                    status      TEXT    NOT NULL DEFAULT 'forwarded',
                    forwarded_at TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(source_id, message_hash)
                );

                CREATE INDEX IF NOT EXISTS idx_fwd_source ON forward_history(source_id);
                CREATE INDEX IF NOT EXISTS idx_fwd_hash  ON forward_history(message_hash);
            """)
            self.conn.commit()

            # -- Migration: ensure replace_rules has UNIQUE constraint on old_word
            # (handles upgrades from schema without it)
            cur = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='replace_rules'"
            )
            indexes = [row[0] or "" for row in cur.fetchall()]
            unique_index_present = any("UNIQUE" in idx and "old_word" in idx for idx in indexes)
            if not unique_index_present:
                self.conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_replace_unique ON replace_rules(old_word)"
                )
                # De-dupe pre-existing duplicates by keeping the lowest id row
                self.conn.execute(
                    """DELETE FROM replace_rules
                       WHERE id NOT IN (
                           SELECT MIN(id) FROM replace_rules GROUP BY old_word
                       )"""
                )
                self.conn.commit()
                logger.info("Migrated replace_rules: UNIQUE constraint on old_word applied.")

    def _set_defaults(self) -> None:
        """Ensure default settings rows exist."""
        defaults = {
            "header": "",
            "footer": "",
            "paused": "false",
            "forward_delay": "3.0",        # seconds between forwards
            "total_forwarded": "0",
            "total_skipped": "0",
        }
        with self._lock:
            for key, value in defaults.items():
                self.conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
            self.conn.commit()

    # ──────────────────────────────────────────────
    #  Source Channels
    # ──────────────────────────────────────────────

    def add_source(self, username: str, channel_id: Optional[int] = None) -> bool:
        """Add a source channel. Returns True if added, False if already exists."""
        username = username.lstrip("@").strip()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO source_channels (username, channel_id) VALUES (?, ?)",
                    (username, channel_id),
                )
                self.conn.commit()
                logger.info("Source added: @%s", username)
                return True
            except sqlite3.IntegrityError:
                return False

    def update_source_channel_id(self, username: str, channel_id: int) -> bool:
        """Persist the resolved Telegram channel_id back to the DB so we can
        match messages from private channels later. Returns True if updated."""
        username = username.lstrip("@").strip()
        with self._lock:
            cur = self.conn.execute(
                "UPDATE source_channels SET channel_id = ? WHERE username = ?",
                (channel_id, username),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def remove_source(self, username: str) -> bool:
        """Remove a source channel by username. Returns True if removed."""
        username = username.lstrip("@").strip()
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM source_channels WHERE username = ?", (username,)
            )
            self.conn.commit()
            removed = cur.rowcount > 0
            if removed:
                logger.info("Source removed: @%s", username)
            return removed

    def get_all_sources(self) -> list[dict]:
        """Return all source channels as list of dicts."""
        cur = self.conn.execute(
            "SELECT id, username, channel_id, added_at FROM source_channels ORDER BY id"
        )
        return [dict(row) for row in cur.fetchall()]

    def get_source_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM source_channels")
        return cur.fetchone()[0]

    # ──────────────────────────────────────────────
    #  Destination
    # ──────────────────────────────────────────────

    def set_destination(self, username: str) -> None:
        username = username.lstrip("@").strip()
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO destination (id, username, set_at) VALUES (1, ?, datetime('now'))",
                (username,),
            )
            self.conn.commit()
            logger.info("Destination set to @%s", username)

    def get_destination(self) -> Optional[str]:
        cur = self.conn.execute("SELECT username FROM destination WHERE id = 1")
        row = cur.fetchone()
        return row["username"] if row else None

    # ──────────────────────────────────────────────
    #  Replace Rules
    # ──────────────────────────────────────────────

    def add_replace_rule(self, old_word: str, new_word: str = "") -> bool:
        """Add or replace (upsert) a word-replacement rule keyed by old_word.
        Returns True if a new row was inserted, False if an existing rule was updated.
        """
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO replace_rules (old_word, new_word)
                   VALUES (?, ?)
                   ON CONFLICT(old_word) DO UPDATE SET new_word = excluded.new_word""",
                (old_word, new_word),
            )
            self.conn.commit()
            inserted = cur.rowcount > 0
            logger.info(
                "Replace rule %s: '%s' -> '%s'",
                "added" if inserted else "updated",
                old_word,
                new_word,
            )
            return inserted

    def remove_replace_rule(self, old_word: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM replace_rules WHERE old_word = ?", (old_word,)
            )
            self.conn.commit()
            removed = cur.rowcount > 0
            if removed:
                logger.info("Replace rule removed for: '%s'", old_word)
            return removed

    def get_all_replace_rules(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT id, old_word, new_word, created_at FROM replace_rules ORDER BY id"
        )
        return [dict(row) for row in cur.fetchall()]

    # ──────────────────────────────────────────────
    #  Block Rules
    # ──────────────────────────────────────────────

    def add_block_rule(self, word: str) -> bool:
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO block_rules (word) VALUES (?)", (word,)
                )
                self.conn.commit()
                logger.info("Block rule added: '%s'", word)
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_block_rule(self, word: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM block_rules WHERE word = ?", (word,)
            )
            self.conn.commit()
            removed = cur.rowcount > 0
            if removed:
                logger.info("Block rule removed: '%s'", word)
            return removed

    def get_all_block_rules(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT id, word, created_at FROM block_rules ORDER BY id"
        )
        return [dict(row) for row in cur.fetchall()]

    def get_all_block_words(self) -> list[str]:
        """Return list of blocked words (strings only) for quick lookup."""
        cur = self.conn.execute("SELECT word FROM block_rules")
        return [row["word"] for row in cur.fetchall()]

    # ──────────────────────────────────────────────
    #  Settings
    # ──────────────────────────────────────────────

    def _get_setting(self, key: str, default: str = "") -> str:
        cur = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def _set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            self.conn.commit()

    # -- Header --
    def set_header(self, text: str) -> None:
        self._set_setting("header", text)

    def get_header(self) -> str:
        return self._get_setting("header", "")

    def clear_header(self) -> None:
        self._set_setting("header", "")

    # -- Footer --
    def set_footer(self, text: str) -> None:
        self._set_setting("footer", text)

    def get_footer(self) -> str:
        return self._get_setting("footer", "")

    def clear_footer(self) -> None:
        self._set_setting("footer", "")

    # -- Pause / Resume --
    def is_paused(self) -> bool:
        return self._get_setting("paused", "false") == "true"

    def set_paused(self, paused: bool) -> None:
        self._set_setting("paused", "true" if paused else "false")

    # -- Forward Delay --
    def get_forward_delay(self) -> float:
        try:
            return float(self._get_setting("forward_delay", "3.0"))
        except ValueError:
            return 3.0

    def set_forward_delay(self, seconds: float) -> None:
        self._set_setting("forward_delay", str(seconds))

    # -- Stats --
    def increment_stat(self, key: str) -> None:
        """Atomically increment a numeric stat ('total_forwarded' or 'total_skipped')."""
        with self._lock:
            self.conn.execute(
                "UPDATE settings SET value = CAST(value AS INTEGER) + 1 WHERE key = ?",
                (key,),
            )
            self.conn.commit()

    def get_stat(self, key: str) -> int:
        try:
            return int(self._get_setting(key, "0"))
        except ValueError:
            return 0

    def get_all_stats(self) -> dict:
        return {
            "total_forwarded": self.get_stat("total_forwarded"),
            "total_skipped": self.get_stat("total_skipped"),
            "source_count": self.get_source_count(),
            "paused": self.is_paused(),
            "forward_delay": self.get_forward_delay(),
        }

    # ──────────────────────────────────────────────
    #  Forward History (dedup + log)
    # ──────────────────────────────────────────────

    def is_duplicate(self, source_id: int, message_text: str) -> bool:
        """
        Check if this message has already been forwarded from this source.
        Uses SHA256 of the message text as hash.
        """
        msg_hash = hashlib.sha256(message_text.encode("utf-8")).hexdigest()
        cur = self.conn.execute(
            "SELECT id FROM forward_history WHERE source_id = ? AND message_hash = ?",
            (source_id, msg_hash),
        )
        return cur.fetchone() is not None

    def log_forward(self, source_id: int, message_text: str, status: str = "forwarded") -> None:
        """Record a forward attempt (for dedup & stats)."""
        msg_hash = hashlib.sha256(message_text.encode("utf-8")).hexdigest()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO forward_history (source_id, message_hash, status) VALUES (?, ?, ?)",
                    (source_id, msg_hash, status),
                )
                self.conn.commit()
            except sqlite3.IntegrityError:
                # Already exists — still counts as duplicate
                pass

    def get_forward_count(self) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM forward_history WHERE status = 'forwarded'"
        )
        return cur.fetchone()[0]

    def get_recent_history(self, limit: int = 20) -> list[dict]:
        cur = self.conn.execute(
            """SELECT fh.id, sc.username AS source, fh.status, fh.forwarded_at
               FROM forward_history fh
               LEFT JOIN source_channels sc ON sc.id = fh.source_id
               ORDER BY fh.id DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    # ──────────────────────────────────────────────
    #  Cleanup
    # ──────────────────────────────────────────────

    def close(self) -> None:
        self.conn.close()
        logger.info("Database connection closed.")
