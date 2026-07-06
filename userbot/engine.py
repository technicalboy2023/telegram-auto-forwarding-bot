"""
Telethon Userbot Engine — monitors source channels & forwards posts.

Responsibilities:
- Start Telethon client with user account
- Load source channels from database
- Register NewMessage event handler on all source channels
- Process each new post through PostCustomizer
- Forward customized posts to destination bot
- Media support: photos, videos, documents with captions
- Duplicate detection via message hash
- Rate limiting (configurable delay between forwards)
- Automatic reconnection on disconnect
"""

import asyncio
import gc
import json
from pathlib import Path
from typing import Optional

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    PeerFloodError,
    ChatWriteForbiddenError,
)
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
)

from userbot.customizer import PostCustomizer
from database.db import Database
from utils.logger import get_logger

logger = get_logger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class UserbotEngine:
    """
    Core engine that monitors source channels via a user account
    and forwards new posts to the destination bot.

    Uses Telethon for MTProto connection.
    """

    def __init__(self, db: Database):
        self.db = db
        self.client: Optional[TelegramClient] = None
        self.customizer = PostCustomizer()
        self._running = False
        self._source_entities: dict[str, object] = {}
        self._forward_count = 0
        self._config_reload_interval = 120  # seconds (reduced for low-RAM VPS)

        # Load credentials
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        self.api_id = cfg["api_id"]
        self.api_hash = cfg["api_hash"]
        self.phone = cfg["phone"]

    # ──────────────────────────────────────────────
    #  Lifecycle
    # ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start the userbot — connect, resolve sources, register handlers."""
        logger.info("Starting Userbot Engine...")

        # Use minimal entity cache to save RAM on low-memory VPS
        self.client = TelegramClient(
            "userbot_session",  # session file name
            self.api_id,
            self.api_hash,
            # Optimizations for 256MB RAM:
            device_model="CLI",           # minimal device info
            system_version="1.0",           # minimal system info
            app_version="1.0",              # minimal app version
        )

        # Register event handler (catch_up=False skips replaying old messages, saves RAM)
        self.client.add_event_handler(
            self._on_new_message,
            events.NewMessage(incoming=True),
        )
        # Disable catch-up to avoid memory spike from backlog of missed messages
        self.client.catch_up = False

        await self.client.start(phone=self.phone)
        me = await self.client.get_me()
        logger.info("Userbot logged in as @%s (ID: %d)", me.username, me.id)

        self._running = True

        # Resolve source channel entities
        await self._resolve_sources()

        # Start config reload loop
        asyncio.create_task(self._reload_config_loop())

        # Keep the client alive
        await self.client.run_until_disconnected()

    async def stop(self) -> None:
        """Gracefully disconnect the Telethon client."""
        self._running = False
        if self.client:
            await self.client.disconnect()
            logger.info("Userbot disconnected.")

    # ──────────────────────────────────────────────
    #  Source Channel Resolution
    # ──────────────────────────────────────────────

    async def _resolve_sources(self) -> None:
        """Resolve all source channels from DB to InputPeerChannel objects."""
        sources = self.db.get_all_sources()
        self._source_entities.clear()

        for src in sources:
            username = src["username"]
            try:
                entity = await self.client.get_input_entity(f"@{username}")
                self._source_entities[username] = entity
                logger.info("Resolved source: @%s (ID: %s)", username, getattr(entity, "channel_id", "?"))
            except Exception as e:
                logger.warning("Could not resolve @%s: %s", username, e)

        logger.info("Resolved %d/%d source channels", len(self._source_entities), len(sources))

    async def _reload_config_loop(self) -> None:
        """Periodically reload customization config and source list."""
        while self._running:
            await asyncio.sleep(self._config_reload_interval)
            try:
                # Reload customization rules
                replace_rules = self.db.get_all_replace_rules()
                block_words = self.db.get_all_block_words()
                header = self.db.get_header()
                footer = self.db.get_footer()
                self.customizer.update_config(replace_rules, block_words, header, footer)

                # Refresh source channels
                await self._resolve_sources()
            except Exception as e:
                logger.error("Config reload failed: %s", e)

    # ──────────────────────────────────────────────
    #  Message Handler
    # ──────────────────────────────────────────────

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        """Handle a new message from a monitored source channel."""
        if not self._running:
            return

        # Check if paused
        if self.db.is_paused():
            return

        # Get message info
        message = event.message
        chat = await event.get_chat()

        # Verify this is from a monitored source
        source_username = getattr(chat, "username", None)
        if not source_username or source_username.lower() not in {
            s.lower() for s in self._source_entities
        }:
            return  # Not from a tracked source

        logger.info("New post from @%s (msg_id=%d)", source_username, message.id)

        # Get source DB id
        sources = self.db.get_all_sources()
        source_db_id = None
        for s in sources:
            if s["username"].lower() == source_username.lower():
                source_db_id = s["id"]
                break

        if source_db_id is None:
            return

        # Prepare text content
        raw_text = message.text or message.raw_text or ""

        # Duplicate check (skip for empty text — media without caption
        # already has no text to dedup against)
        if raw_text and self.db.is_duplicate(source_db_id, raw_text):
            logger.debug("Duplicate post skipped (src=%s, msg=%d)", source_username, message.id)
            return

        # Process through customizer
        caption_text = raw_text
        processed_caption = self.customizer.process_caption(caption_text)

        # Check if blocked
        if raw_text and processed_caption is None:
            self.db.increment_stat("total_skipped")
            self.db.log_forward(source_db_id, raw_text, status="skipped")
            logger.info("Post skipped (blocked) from @%s", source_username)
            return

        # Get destination
        dest_username = self.db.get_destination()
        if not dest_username:
            logger.warning("No destination bot set — post not forwarded")
            return

        # Forward with rate limiting
        await self._forward_message(
            dest_username,
            message,
            processed_caption,
            source_db_id,
            raw_text,
        )

    async def _send_single_forward(
        self,
        dest_entity,
        original_message,
        processed_caption: Optional[str],
    ) -> None:
        """Send a single message/media to the destination entity."""
        media = original_message.media

        if media and isinstance(media, MessageMediaPhoto):
            await self.client.send_file(
                dest_entity,
                media.photo,
                caption=processed_caption or "",
            )
        elif media and isinstance(media, MessageMediaDocument):
            await self.client.send_file(
                dest_entity,
                media.document,
                caption=processed_caption or "",
            )
        else:
            if processed_caption:
                await self.client.send_message(dest_entity, processed_caption)

    async def _forward_message(
        self,
        dest_username: str,
        original_message,
        processed_caption: Optional[str],
        source_db_id: int,
        raw_text: str,
    ) -> None:
        """Forward a message to the destination bot with media support."""
        try:
            # Rate limiting delay
            delay = self.db.get_forward_delay()
            await asyncio.sleep(delay)

            dest_entity = await self.client.get_input_entity(f"@{dest_username}")

            await self._send_single_forward(
                dest_entity, original_message, processed_caption
            )

            # Guard against sending empty plain-text messages
            if not processed_caption and not original_message.media:
                logger.debug("Skipping empty message from src=%d", source_db_id)
                return

            # Log success
            self.db.increment_stat("total_forwarded")
            self.db.log_forward(source_db_id, raw_text, status="forwarded")

            logger.info(
                "Forwarded to @%s | source_id=%d | delay=%.1fs",
                dest_username,
                source_db_id,
                delay,
            )

            # Free memory every 5 forwards (critical for 256MB VPS, but batched)
            self._forward_count += 1
            if self._forward_count % 5 == 0:
                gc.collect()
                # Periodically clear Telethon's entity cache to prevent RAM bloat
                if hasattr(self.client, 'session') and hasattr(self.client.session, '_cache'):
                    try:
                        self.client.session._cache.clear()
                    except Exception:
                        pass

        except FloodWaitError as e:
            logger.warning("Flood wait: %d seconds. Waiting...", e.seconds)
            await asyncio.sleep(e.seconds)
            # Retry once after waiting
            try:
                delay = self.db.get_forward_delay()
                await asyncio.sleep(delay)
                dest_entity = await self.client.get_input_entity(f"@{dest_username}")
                await self._send_single_forward(
                    dest_entity, original_message, processed_caption
                )
                # Log success after retry
                self.db.increment_stat("total_forwarded")
                self.db.log_forward(source_db_id, raw_text, status="forwarded")
                logger.info(
                    "Forwarded to @%s | source_id=%d | delay=%.1fs (after flood wait)",
                    dest_username,
                    source_db_id,
                    delay,
                )
                self._forward_count += 1
                if self._forward_count % 5 == 0:
                    gc.collect()
            except PeerFloodError:
                logger.error("Peer flood error on retry — cooling down 60s")
            except ChatWriteForbiddenError:
                logger.error("Cannot write to @%s on retry — bot may have restricted forwarding.", dest_username)
            except Exception as retry_err:
                logger.error("Forward retry failed: %s", retry_err, exc_info=True)
        except PeerFloodError:
            logger.error("Peer flood error — Telegram rate limit hit. Cooling down 60s...")
            await asyncio.sleep(60)
        except ChatWriteForbiddenError:
            logger.error(
                "Cannot write to @%s — bot may have blocked or restricted forwarding.",
                dest_username,
            )
        except Exception as e:
            logger.error("Forward failed: %s", e, exc_info=True)
