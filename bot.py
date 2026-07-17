#!/usr/bin/env python3
"""
Telegram Auto-Forwarding Bot — Main Entry Point
===============================================

Runs TWO components concurrently via asyncio:

1. USERBOT (Telethon) — monitors source channels, customizes posts,
   and forwards them to the destination bot.

2. CONTROL BOT (python-telegram-bot) — admin panel via Telegram bot
   commands to manage all settings.

Usage:
    python bot.py
"""

import logging
import asyncio
import gc
import json
import os
import sys
from pathlib import Path

from userbot.engine import UserbotEngine
from controlbot.bot import build_application
from database.db import Database
from utils.logger import setup_logging
from utils.cleanup import CleanupScheduler

CONFIG_PATH = Path(__file__).parent / "config.json"

logger = None


def load_config() -> dict:
    """Load and return config.json."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def validate_config(cfg: dict) -> bool:
    """Validate that all required config fields are present and non-placeholder."""
    required = ["api_id", "api_hash", "bot_token", "admin_id"]

    missing = [k for k in required if k not in cfg]
    if missing:
        print(f"❌ Missing config keys: {', '.join(missing)}")
        print("   Please fill out config.json with your credentials.")
        return False

    placeholders = ["YOUR_API_ID", "YOUR_API_HASH", "YOUR_CONTROL_BOT_TOKEN"]
    for key, value in cfg.items():
        if key in required and value in placeholders:
            print(f"❌ config.json still has placeholder value for '{key}'")
            print(f"   Current: {value}")
            print("   Please replace it with your actual credentials.")
            return False

    # Validate admin_id is a number
    try:
        admin_id = int(cfg["admin_id"])
        if admin_id == 123456789:
            print("❌ config.json still has the default admin_id (123456789).")
            print("   Get your numeric Telegram ID from @userinfobot and update it.")
            return False
    except (ValueError, TypeError):
        print("❌ admin_id must be a numeric Telegram user ID.")
        return False

    return True


def main():
    """Main entry point. Runs both userbot and control bot."""
    global logger

    # Setup logging first (use WARNING level for low-RAM environments)
    log_level = logging.WARNING if os.environ.get("LOW_RAM") else logging.INFO
    logger = setup_logging(level=log_level)
    logger.info("=" * 50)
    logger.info("Telegram Auto-Forwarding Bot starting...")
    logger.info("=" * 50)

    # Validate config
    cfg = load_config()
    if not validate_config(cfg):
        sys.exit(1)

    logger.info("Config loaded successfully.")

    # --- Initialise database ---
    db = Database()
    logger.info("Database ready.")

    # --- One-shot startup cleanup (runs BEFORE the asyncio event loop) ---
    scheduler = CleanupScheduler(db)
    try:
        startup_report = scheduler.run_full_cleanup()
        logger.info("Startup cleanup: %s", startup_report.summary())
    except Exception as e:
        logger.warning("Startup cleanup failed (continuing anyway): %s", e)

    # --- Build PTB application (Control Bot) ---
    ptb_app = build_application(db)

    # --- Initialize Userbot Engine ---
    userbot = UserbotEngine(db)

    # Auto-restart interval in seconds (set to 0 to disable)
    RESTART_HOURS = 6  # Restart every 6 hours to clear memory leaks
    _no_restart = os.environ.get("NO_RESTART", "").strip().lower()
    if _no_restart not in ("", "0", "false", "no"):
        RESTART_HOURS = 0

    async def run_all():
        """Run both components concurrently."""
        shutdown_event = asyncio.Event()

        # ── Periodic memory cleanup task ──
        async def _memory_cleaner():
            """Run gc.collect() every 5 minutes to keep RAM usage low."""
            while not shutdown_event.is_set():
                await asyncio.sleep(300)  # every 5 min
                gc.collect()
                logger.debug("gc.collect() — RAM cleaned")

        # ── Auto-restart timer ──
        async def _auto_restart():
            """Exit cleanly after RESTART_HOURS so the process manager restarts us."""
            if RESTART_HOURS <= 0:
                return
            await asyncio.sleep(RESTART_HOURS * 3600)
            logger.warning(
                "Auto-restart triggered (%dh). Exiting for clean restart...",
                RESTART_HOURS,
            )
            shutdown_event.set()

        # ── Periodic disk & history cleanup (every CLEANUP_INTERVAL_HOURS, default 24) ──
        async def _auto_cleanup():
            """Prune history rows, VACUUM DB, clear __pycache__ & orphan log files."""
            await scheduler.run_periodically(shutdown_event)

        async def _run_ptb():
            """Run PTB polling in a task."""
            logger.info("Control Bot (PTB) starting polling...")
            try:
                await ptb_app.initialize()
                if ptb_app.post_init:
                    await ptb_app.post_init(ptb_app)
                await ptb_app.start()
                await ptb_app.updater.start_polling(drop_pending_updates=True)
                logger.info("Control Bot is ready — listening for commands.")

                # Wait until shutdown is triggered
                await shutdown_event.wait()

                logger.info("Stopping Control Bot...")
                await ptb_app.updater.stop()
                await ptb_app.stop()
                await ptb_app.shutdown()
                logger.info("Control Bot stopped.")
            except Exception as e:
                logger.error("Control Bot crashed: %s", e, exc_info=True)

        async def _run_userbot():
            """Run Telethon userbot in a task."""
            logger.info("Userbot (Telethon) starting...")
            try:
                await userbot.start()
                await userbot.client.run_until_disconnected()
            except asyncio.CancelledError:
                # Auto-restart or shutdown trigger — disconnect cleanly so the
                # MTProto session file is not corrupted on disk.
                logger.info("Userbot task cancelled — disconnecting cleanly...")
                try:
                    await userbot.stop()
                except Exception as e:
                    logger.warning("Userbot stop() during cancel failed: %s", e)
            except Exception as e:
                logger.error("Userbot crashed: %s", e, exc_info=True)
            finally:
                logger.info("Userbot stopped.")
                # Trigger shutdown if userbot exits first
                if not shutdown_event.is_set():
                    shutdown_event.set()

        # Run both + maintenance tasks concurrently
        ptb_task = asyncio.create_task(_run_ptb())
        ub_task = asyncio.create_task(_run_userbot())
        gc_task = asyncio.create_task(_memory_cleaner())
        restart_task = asyncio.create_task(_auto_restart())
        cleanup_task = asyncio.create_task(_auto_cleanup())

        # Wait for any task to finish
        done, pending = await asyncio.wait(
            [ptb_task, ub_task, gc_task, restart_task, cleanup_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel remaining tasks
        for task in pending:
            task.cancel()

        # Wait for cancellations
        await asyncio.gather(*pending, return_exceptions=True)

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        db.close()
        logger.info("Bot shut down complete. Goodbye!")


if __name__ == "__main__":
    main()
