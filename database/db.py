"""
SQLite database module for the Telegram Auto-Forwarding Bot.

Manages all persistent storage:
- Sources (Universal identifier: username/id/invite)
- Destinations (Universal identifier)
- Routes (source -> destination mapping)
- Replace rules (word -> replacement)
- Block rules (blocked words)
- Settings (header, footer, pause status, forward delay, default dest)
- Dedup window (cross-source sliding window dedup)
- Forward history (for stats)
"""

import sqlite3
import threading
import hashlib
import re
from pathlib import Path
from typing import Optional, List, Dict

from utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).parent.parent / "bot_data.db"


def normalize_for_dedup(text: str) -> str:
    """Normalize text for cross-source comparison."""
    if not text:
        return ""

    text = text.lower()
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    # Remove @mentions
    text = re.sub(r"@\w+", "", text)
    # Remove #hashtags
    text = re.sub(r"#\w+", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def content_hash(text: str) -> str:
    """Generate SHA256 hash of normalized text."""
    normalized = normalize_for_dedup(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class Database:
    """
    Thread-safe SQLite database wrapper.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._lock = threading.RLock()

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
        self._migrate_old_tables()
        self._set_defaults()
        logger.info("Database initialised at %s", self.db_path)

    # ──────────────────────────────────────────────
    #  Schema
    # ──────────────────────────────────────────────

    def _create_tables(self) -> None:
        with self._lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    identifier  TEXT    NOT NULL UNIQUE,   -- @username, numeric_id, or invite_hash
                    chat_id     INTEGER,                   -- resolved Telegram chat ID
                    title       TEXT    DEFAULT '',
                    entity_type TEXT    DEFAULT 'unknown',
                    added_at    TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS destinations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    identifier  TEXT    NOT NULL UNIQUE,
                    chat_id     INTEGER,
                    title       TEXT    DEFAULT '',
                    entity_type TEXT    DEFAULT 'unknown',
                    added_at    TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS routes (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    dest_id     INTEGER NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
                    added_at    TEXT    NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(source_id, dest_id)
                );

                CREATE TABLE IF NOT EXISTS dedup_window (
                    content_hash    TEXT    PRIMARY KEY,
                    first_source_id INTEGER NOT NULL,
                    first_seen_at   TEXT    NOT NULL DEFAULT (datetime('now')),
                    forwarded       INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_dedup_seen ON dedup_window(first_seen_at);

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

                -- Legacy forward history mostly for stats now
                CREATE TABLE IF NOT EXISTS forward_history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id   INTEGER NOT NULL,
                    message_hash TEXT   NOT NULL,
                    status      TEXT    NOT NULL DEFAULT 'forwarded',
                    forwarded_at TEXT    NOT NULL DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_fwd_source ON forward_history(source_id);
            """)
            self.conn.commit()

    def _migrate_old_tables(self) -> None:
        """Migrate data from old tables to new universal tables, then drop old tables."""
        with self._lock:
            cur = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='source_channels'"
            )
            if cur.fetchone() is None:
                return  # No old tables

            logger.info("Migrating old database schema to universal entities...")

            # Migrate global destination
            cur = self.conn.execute("SELECT username FROM destination WHERE id = 1")
            row = cur.fetchone()
            if row:
                dest_uname = "@" + row["username"].lstrip("@")
                self.conn.execute(
                    "INSERT OR IGNORE INTO destinations (identifier, title, entity_type) VALUES (?, ?, ?)",
                    (dest_uname, dest_uname, "bot"),
                )
                dest_id_row = self.conn.execute(
                    "SELECT id FROM destinations WHERE identifier = ?", (dest_uname,)
                ).fetchone()
                if dest_id_row:
                    self.conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES ('default_dest_id', ?)",
                        (str(dest_id_row["id"]),),
                    )

            # Migrate sources and their routes
            cur = self.conn.execute(
                "SELECT id, username, channel_id, destination FROM source_channels"
            )
            for src in cur.fetchall():
                src_ident = "@" + src["username"].lstrip("@")
                chat_id = src["channel_id"]
                self.conn.execute(
                    "INSERT OR IGNORE INTO sources (identifier, chat_id, title) VALUES (?, ?, ?)",
                    (src_ident, chat_id, src_ident),
                )
                new_src_id_row = self.conn.execute(
                    "SELECT id FROM sources WHERE identifier = ?", (src_ident,)
                ).fetchone()
                if not new_src_id_row:
                    continue
                new_src_id = new_src_id_row["id"]

                dests_to_link = []
                if src["destination"]:
                    dests_to_link.append("@" + src["destination"].lstrip("@"))

                # Get multi-dests
                cur2 = self.conn.execute(
                    "SELECT bot_username FROM source_destinations WHERE source_id = ?",
                    (src["id"],),
                )
                for sdest in cur2.fetchall():
                    sdest_ident = "@" + sdest["bot_username"].lstrip("@")
                    if sdest_ident not in dests_to_link:
                        dests_to_link.append(sdest_ident)

                for dest_ident in dests_to_link:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO destinations (identifier, title) VALUES (?, ?)",
                        (dest_ident, dest_ident),
                    )
                    dest_id_row = self.conn.execute(
                        "SELECT id FROM destinations WHERE identifier = ?",
                        (dest_ident,),
                    ).fetchone()
                    if dest_id_row:
                        self.conn.execute(
                            "INSERT OR IGNORE INTO routes (source_id, dest_id) VALUES (?, ?)",
                            (new_src_id, dest_id_row["id"]),
                        )

            # Drop old tables
            self.conn.executescript("""
                DROP TABLE IF EXISTS source_destinations;
                DROP TABLE IF EXISTS source_channels;
                DROP TABLE IF EXISTS destination;
            """)
            self.conn.commit()
            logger.info("Migration complete. Old tables dropped.")

    def _set_defaults(self) -> None:
        defaults = {
            "header": "",
            "footer": "",
            "paused": "false",
            "forward_delay": "3.0",
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
    #  Settings Helper
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

    # ──────────────────────────────────────────────
    #  Sources
    # ──────────────────────────────────────────────

    def add_source(self, identifier: str) -> bool:
        identifier = identifier.strip()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO sources (identifier) VALUES (?)", (identifier,)
                )
                self.conn.commit()
                logger.info("Source added: %s", identifier)
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_source(self, identifier: str) -> bool:
        identifier = identifier.strip()
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM sources WHERE identifier = ?", (identifier,)
            )
            self.conn.commit()
            removed = cur.rowcount > 0
            if removed:
                logger.info("Source removed: %s", identifier)
            return removed

    def get_all_sources(self) -> List[Dict]:
        cur = self.conn.execute("SELECT * FROM sources ORDER BY id")
        return [dict(row) for row in cur.fetchall()]

    def get_source_by_identifier(self, identifier: str) -> Optional[Dict]:
        cur = self.conn.execute(
            "SELECT * FROM sources WHERE identifier = ?", (identifier,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def update_source_metadata(
        self, source_id: int, chat_id: int, title: str, entity_type: str
    ) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE sources SET chat_id = ?, title = ?, entity_type = ? WHERE id = ?",
                (chat_id, title, entity_type, source_id),
            )
            self.conn.commit()

    def get_source_count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM sources")
        return cur.fetchone()[0]

    # ──────────────────────────────────────────────
    #  Destinations
    # ──────────────────────────────────────────────

    def add_destination(self, identifier: str) -> bool:
        identifier = identifier.strip()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO destinations (identifier) VALUES (?)", (identifier,)
                )
                self.conn.commit()
                logger.info("Destination added: %s", identifier)
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_destination(self, identifier: str) -> bool:
        identifier = identifier.strip()
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM destinations WHERE identifier = ?", (identifier,)
            )
            self.conn.commit()
            removed = cur.rowcount > 0
            if removed:
                logger.info("Destination removed: %s", identifier)
            return removed

    def get_all_destinations(self) -> List[Dict]:
        cur = self.conn.execute("SELECT * FROM destinations ORDER BY id")
        return [dict(row) for row in cur.fetchall()]

    def get_destination_by_identifier(self, identifier: str) -> Optional[Dict]:
        cur = self.conn.execute(
            "SELECT * FROM destinations WHERE identifier = ?", (identifier,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def update_dest_metadata(
        self, dest_id: int, chat_id: int, title: str, entity_type: str
    ) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE destinations SET chat_id = ?, title = ?, entity_type = ? WHERE id = ?",
                (chat_id, title, entity_type, dest_id),
            )
            self.conn.commit()

    def set_default_dest(self, dest_identifier: str) -> bool:
        dest = self.get_destination_by_identifier(dest_identifier)
        if not dest:
            return False
        self._set_setting("default_dest_id", str(dest["id"]))
        logger.info("Global default destination set to %s", dest_identifier)
        return True

    def clear_default_dest(self) -> None:
        self._set_setting("default_dest_id", "")
        logger.info("Global default destination cleared")

    def get_default_dest(self) -> Optional[Dict]:
        dest_id = self._get_setting("default_dest_id")
        if not dest_id:
            return None
        cur = self.conn.execute("SELECT * FROM destinations WHERE id = ?", (dest_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    # ──────────────────────────────────────────────
    #  Routes (Source -> Destination mapping)
    # ──────────────────────────────────────────────

    def add_route(self, source_ident: str, dest_ident: str) -> bool:
        with self._lock:
            s_row = self.conn.execute(
                "SELECT id FROM sources WHERE identifier = ?", (source_ident,)
            ).fetchone()
            d_row = self.conn.execute(
                "SELECT id FROM destinations WHERE identifier = ?", (dest_ident,)
            ).fetchone()

            if not s_row or not d_row:
                return False

            try:
                self.conn.execute(
                    "INSERT INTO routes (source_id, dest_id) VALUES (?, ?)",
                    (s_row["id"], d_row["id"]),
                )
                self.conn.commit()
                logger.info("Route added: %s -> %s", source_ident, dest_ident)
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_route(self, source_ident: str, dest_ident: str) -> bool:
        with self._lock:
            s_row = self.conn.execute(
                "SELECT id FROM sources WHERE identifier = ?", (source_ident,)
            ).fetchone()
            d_row = self.conn.execute(
                "SELECT id FROM destinations WHERE identifier = ?", (dest_ident,)
            ).fetchone()

            if not s_row or not d_row:
                return False

            cur = self.conn.execute(
                "DELETE FROM routes WHERE source_id = ? AND dest_id = ?",
                (s_row["id"], d_row["id"]),
            )
            self.conn.commit()
            removed = cur.rowcount > 0
            if removed:
                logger.info("Route removed: %s -> %s", source_ident, dest_ident)
            return removed

    def remove_all_routes_for_source(self, source_ident: str) -> int:
        with self._lock:
            s_row = self.conn.execute(
                "SELECT id FROM sources WHERE identifier = ?", (source_ident,)
            ).fetchone()
            if not s_row:
                return 0
            cur = self.conn.execute(
                "DELETE FROM routes WHERE source_id = ?", (s_row["id"],)
            )
            self.conn.commit()
            return cur.rowcount

    def get_routes_for_source(self, source_id: int) -> List[Dict]:
        cur = self.conn.execute(
            """
            SELECT d.* FROM destinations d
            JOIN routes r ON d.id = r.dest_id
            WHERE r.source_id = ?
        """,
            (source_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    # ──────────────────────────────────────────────
    #  Cross-Source Duplicate Filter (1-Hour Window)
    # ──────────────────────────────────────────────

    def check_and_mark_dedup(self, raw_text: str, source_id: int) -> bool:
        """
        Check if content was seen within the 1-hour window.
        Returns True if DUPLICATE. False if NEW.
        """
        c_hash = content_hash(raw_text)
        with self._lock:
            self.conn.execute(
                "DELETE FROM dedup_window WHERE first_seen_at < datetime('now', '-1 hour')"
            )

            cur = self.conn.execute(
                "SELECT content_hash FROM dedup_window WHERE content_hash = ?",
                (c_hash,),
            )
            if cur.fetchone() is not None:
                return True  # Duplicate

            self.conn.execute(
                "INSERT INTO dedup_window (content_hash, first_source_id) VALUES (?, ?)",
                (c_hash, source_id),
            )
            self.conn.commit()
            return False

    def cleanup_dedup_window(self) -> int:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM dedup_window WHERE first_seen_at < datetime('now', '-1 hour')"
            )
            self.conn.commit()
            return cur.rowcount

    # ──────────────────────────────────────────────
    #  Replace & Block Rules
    # ──────────────────────────────────────────────

    def add_replace_rule(self, old_word: str, new_word: str = "") -> bool:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO replace_rules (old_word, new_word) VALUES (?, ?) "
                "ON CONFLICT(old_word) DO UPDATE SET new_word = excluded.new_word",
                (old_word, new_word),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def remove_replace_rule(self, old_word: str) -> bool:
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM replace_rules WHERE old_word = ?", (old_word,)
            )
            self.conn.commit()
            return cur.rowcount > 0

    def get_all_replace_rules(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM replace_rules ORDER BY id")
        return [dict(row) for row in cur.fetchall()]

    def add_block_rule(self, word: str) -> bool:
        with self._lock:
            try:
                self.conn.execute("INSERT INTO block_rules (word) VALUES (?)", (word,))
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_block_rule(self, word: str) -> bool:
        with self._lock:
            cur = self.conn.execute("DELETE FROM block_rules WHERE word = ?", (word,))
            self.conn.commit()
            return cur.rowcount > 0

    def get_all_block_rules(self) -> list[dict]:
        cur = self.conn.execute("SELECT * FROM block_rules ORDER BY id")
        return [dict(row) for row in cur.fetchall()]

    def get_all_block_words(self) -> list[str]:
        cur = self.conn.execute("SELECT word FROM block_rules")
        return [row["word"] for row in cur.fetchall()]

    # ──────────────────────────────────────────────
    #  Settings & Stats
    # ──────────────────────────────────────────────

    def set_header(self, text: str) -> None:
        self._set_setting("header", text)

    def get_header(self) -> str:
        return self._get_setting("header", "")

    def clear_header(self) -> None:
        self._set_setting("header", "")

    def set_footer(self, text: str) -> None:
        self._set_setting("footer", text)

    def get_footer(self) -> str:
        return self._get_setting("footer", "")

    def clear_footer(self) -> None:
        self._set_setting("footer", "")

    def is_paused(self) -> bool:
        return self._get_setting("paused", "false") == "true"

    def set_paused(self, paused: bool) -> None:
        self._set_setting("paused", "true" if paused else "false")

    def get_forward_delay(self) -> float:
        try:
            return float(self._get_setting("forward_delay", "3.0"))
        except ValueError:
            return 3.0

    def set_forward_delay(self, seconds: float) -> None:
        self._set_setting("forward_delay", str(seconds))

    def increment_stat(self, key: str) -> None:
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

    def log_forward(
        self, source_id: int, message_text: str, status: str = "forwarded"
    ) -> None:
        msg_hash = content_hash(message_text) if message_text else "empty"
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO forward_history (source_id, message_hash, status) VALUES (?, ?, ?)",
                    (source_id, msg_hash, status),
                )
                self.conn.commit()
            except sqlite3.IntegrityError:
                pass

    def get_forward_count(self) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM forward_history WHERE status = 'forwarded'"
        )
        return cur.fetchone()[0]

    def get_recent_history(self, limit: int = 20) -> list[dict]:
        cur = self.conn.execute(
            """SELECT fh.id, s.identifier AS source, fh.status, fh.forwarded_at
               FROM forward_history fh
               LEFT JOIN sources s ON s.id = fh.source_id
               ORDER BY fh.id DESC LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def prune_history(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        with self._lock:
            cur = self.conn.execute(
                "DELETE FROM forward_history WHERE forwarded_at < datetime('now', ?)",
                (f"-{int(retention_days)} days",),
            )
            self.conn.commit()
            return cur.rowcount

    def vacuum(self) -> None:
        with self._lock:
            try:
                self.conn.execute("VACUUM")
            except sqlite3.OperationalError:
                pass

    def close(self) -> None:
        self.conn.close()
