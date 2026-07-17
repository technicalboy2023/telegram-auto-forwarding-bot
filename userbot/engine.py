"""
Telethon Userbot Engine — monitors source channels & forwards posts.

Responsibilities:
- Start Telethon client with user account
- Load source channels from database
- Register NewMessage event handler on all source channels
- Process each new post through PostCustomizer
- Forward customized posts to destination entities
- Cross-source duplicate detection (1-hour window)
- Rate limiting
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
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    Channel,
    Chat,
    User,
)

from userbot.customizer import PostCustomizer
from database.db import Database
from utils.logger import get_logger

logger = get_logger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class UserbotEngine:
    def __init__(self, db: Database):
        self.db = db
        self.client: Optional[TelegramClient] = None
        self.customizer = PostCustomizer()
        self._running = False
        self._source_map: dict[int, dict] = {}  # chat_id -> source_db_row
        self._forward_count = 0
        self._config_reload_interval = 120  # seconds

        # Load credentials
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)

        session_path = str(Path(__file__).parent.parent / "userbot_session")

        self.client = TelegramClient(
            session_path,
            cfg["api_id"],
            cfg["api_hash"],
            device_model="AutoForwarder",
            system_version="1.0",
            app_version="2.0",
        )

        # Register event handlers
        self.client.add_event_handler(self._on_new_message, events.NewMessage)

    # ──────────────────────────────────────────────
    #  Lifecycle
    # ──────────────────────────────────────────────

    async def start(self) -> None:
        """Start the MTProto client and background tasks."""
        logger.info("Starting Userbot Engine...")
        self._running = True

        await self.client.connect()
        if not await self.client.is_user_authorized():
            logger.error("❌ Userbot session is NOT authorized!")
            logger.error("Please run 'python3 login.py' in a terminal to authenticate first.")
            await self.client.disconnect()
            raise PermissionError("Userbot session unauthorized. Run login.py first.")

        # Load initial config
        replace_rules = self.db.get_all_replace_rules()
        block_words = self.db.get_all_block_words()
        header = self.db.get_header()
        footer = self.db.get_footer()
        self.customizer.update_config(replace_rules, block_words, header, footer)

        # Resolve all sources
        await self._resolve_sources()

        # Start background config reloader
        asyncio.create_task(self._reload_config_loop())

        logger.info("Userbot Engine started and listening for messages.")

    async def stop(self) -> None:
        """Stop the client and disconnect."""
        logger.info("Stopping Userbot Engine...")
        self._running = False
        if self.client and self.client.is_connected():
            await self.client.disconnect()

    # ──────────────────────────────────────────────
    #  Source Resolution
    # ──────────────────────────────────────────────

    def _classify_entity(self, entity) -> str:
        if isinstance(entity, Channel):
            return "supergroup" if getattr(entity, "megagroup", False) else "channel"
        elif isinstance(entity, Chat):
            return "group"
        elif isinstance(entity, User):
            return "bot" if getattr(entity, "bot", False) else "user"
        return "unknown"

    async def _resolve_sources(self) -> None:
        """Resolve all source channels from DB to Telegram entities."""
        sources = self.db.get_all_sources()
        self._source_map.clear()

        # Pre-fill cache (crucial for private groups/channels)
        try:
            logger.info("Pre-fetching dialogs to populate entity cache...")
            await self.client.get_dialogs(limit=None)
        except Exception as e:
            logger.warning("Failed to fetch dialogs: %s", e)

        for src in sources:
            identifier = src["identifier"]
            chat_id = src["chat_id"]

            entity = None
            try:
                # Handle Invite Links
                if "t.me/joinchat/" in identifier or "t.me/+" in identifier:
                    hash_part = identifier.split("/")[-1]
                    if hash_part.startswith("+"):
                        hash_part = hash_part[1:]
                    try:
                        # Attempt to join if not already joined
                        updates = await self.client(ImportChatInviteRequest(hash_part))
                        if updates.chats:
                            entity = updates.chats[0]
                    except Exception as invite_err:
                        # Might already be joined, try to find it in dialogs
                        # But we don't have ID... so we skip unless chat_id is known
                        logger.warning(
                            "Invite link error for %s: %s", identifier, invite_err
                        )

                # Try by chat_id if we have it
                if not entity and chat_id:
                    try:
                        entity = await self.client.get_entity(chat_id)
                    except Exception:
                        pass

                # Try by identifier string directly
                if not entity:
                    try:
                        if identifier.lstrip("-").isdigit():
                            entity = await self.client.get_entity(int(identifier))
                        else:
                            entity = await self.client.get_entity(identifier)
                    except Exception as e:
                        logger.warning(
                            "Could not resolve source '%s': %s", identifier, e
                        )
                        continue

            except Exception as e:
                logger.warning(
                    "Unexpected error resolving source '%s': %s", identifier, e
                )
                continue

            if entity:
                resolved_id = entity.id
                title = (
                    getattr(entity, "title", "")
                    or getattr(entity, "first_name", "")
                    or ""
                )
                entity_type = self._classify_entity(entity)

                # Update DB
                self.db.update_source_metadata(
                    src["id"], resolved_id, title, entity_type
                )

                # Map it for event matching
                self._source_map[resolved_id] = src
                logger.info(
                    "Resolved source: %s (ID: %s) [%s]",
                    title or identifier,
                    resolved_id,
                    entity_type,
                )

        logger.info(
            "Resolved %d/%d source channels", len(self._source_map), len(sources)
        )

    async def _reload_config_loop(self) -> None:
        """Periodically reload config and sources."""
        while self._running:
            await asyncio.sleep(self._config_reload_interval)
            try:
                replace_rules = self.db.get_all_replace_rules()
                block_words = self.db.get_all_block_words()
                header = self.db.get_header()
                footer = self.db.get_footer()
                self.customizer.update_config(
                    replace_rules, block_words, header, footer
                )
                await self._resolve_sources()
            except Exception as e:
                logger.error("Config reload failed: %s", e)

    # ──────────────────────────────────────────────
    #  Message Handling
    # ──────────────────────────────────────────────

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        """Called when a new message arrives in ANY chat."""
        if not self._running:
            return

        if self.db.is_paused():
            return

        chat = await event.get_chat()
        if not chat:
            return

        chat_id = chat.id
        source_db_row = self._source_map.get(chat_id)

        # Ignore if not from a monitored source
        if not source_db_row:
            return

        source_db_id = source_db_row["id"]
        source_title = source_db_row["title"] or source_db_row["identifier"]
        message = event.message

        logger.info("New post detected in '%s' (MsgID: %s)", source_title, message.id)

        # 1. Check Cross-Source Dedup (1-Hour Window)
        raw_text = message.text or message.raw_text or ""
        if raw_text:
            if self.db.check_and_mark_dedup(raw_text, source_db_id):
                logger.info(
                    "Cross-source duplicate skipped (src=%s, msg=%d, window=1h)",
                    source_title,
                    message.id,
                )
                self.db.increment_stat("total_skipped")
                return

        # 2. Extract media (we don't forward raw files yet unless we send as is)
        media = message.media

        # 3. Customizer (Block check, word replace, header/footer)
        customized_text = self.customizer.process(raw_text)
        if customized_text is None:
            logger.info(
                "Post skipped (src=%s, msg=%d): Blocked by customizer",
                source_title,
                message.id,
            )
            self.db.increment_stat("total_skipped")
            self.db.log_forward(source_db_id, raw_text, status="blocked")
            return

        # 4. Resolve Destinations
        routes = self.db.get_routes_for_source(source_db_id)
        dests_to_use = []
        if routes:
            dests_to_use = routes
        else:
            default_dest = self.db.get_default_dest()
            if default_dest:
                dests_to_use = [default_dest]

        if not dests_to_use:
            logger.warning(
                "No destination configured for source %s and no global default. Skipping.",
                source_title,
            )
            return

        forward_delay = self.db.get_forward_delay()

        # 5. Forward to all targets
        for dest_row in dests_to_use:
            dest_ident = dest_row["identifier"]
            dest_chat_id = dest_row["chat_id"]
            dest_title = dest_row["title"] or dest_ident

            await asyncio.sleep(forward_delay)

            try:
                # Resolve InputEntity
                target_entity = None
                if dest_chat_id:
                    target_entity = await self.client.get_input_entity(dest_chat_id)
                else:
                    if dest_ident.lstrip("-").isdigit():
                        target_entity = await self.client.get_input_entity(
                            int(dest_ident)
                        )
                    else:
                        target_entity = await self.client.get_input_entity(dest_ident)

                await self._send_post(target_entity, customized_text, media)

                logger.info("Forwarded to '%s' successfully.", dest_title)
                self.db.increment_stat("total_forwarded")
                self.db.log_forward(source_db_id, raw_text, status="forwarded")

                # Memory management for low-RAM
                self._forward_count += 1
                if self._forward_count % 5 == 0:
                    gc.collect()

            except Exception as e:
                logger.error("Failed to forward to '%s': %s", dest_ident, e)
                self.db.log_forward(
                    source_db_id, raw_text, status=f"error: {type(e).__name__}"
                )

    async def _send_post(
        self, target_entity: object, text: str, media: Optional[object]
    ) -> None:
        """Sends the text/media to the target, handling API errors."""
        try:
            # We use send_message / send_file instead of forward_messages
            # so we can apply our customized text and remove the "Forwarded from" tag.

            # Send with media
            if media and (
                isinstance(media, MessageMediaPhoto)
                or isinstance(media, MessageMediaDocument)
            ):
                await asyncio.wait_for(
                    self.client.send_file(
                        target_entity,
                        file=media,
                        caption=text,
                        parse_mode=None,  # Already raw/html handled by userbot if they want, but here it's raw text
                    ),
                    timeout=30.0,
                )
            # Send text only
            elif text:
                await asyncio.wait_for(
                    self.client.send_message(
                        target_entity,
                        message=text,
                        parse_mode=None,
                        link_preview=False,
                    ),
                    timeout=30.0,
                )

        except asyncio.TimeoutError:
            logger.error("Send timeout to destination.")
            raise
        except FloodWaitError as e:
            logger.warning("FloodWait: Sleeping for %d seconds...", e.seconds)
            await asyncio.sleep(min(e.seconds, 60))
            raise
        except PeerFloodError:
            logger.error("PeerFloodError: Rate limited heavily by Telegram.")
            await asyncio.sleep(60)
            raise
        except ChatWriteForbiddenError:
            logger.error("ChatWriteForbidden: Bot/User is blocked or lacks permission.")
            raise
        except Exception as e:
            logger.error("Unexpected sending error: %s", e)
            raise
