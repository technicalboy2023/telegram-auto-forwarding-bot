"""
Control Bot — Admin panel via Telegram bot commands.

Uses python-telegram-bot to provide a command-based interface
for managing the auto-forwarding setup. Only the configured
admin_id can use the bot.
"""

import json
from pathlib import Path

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from utils.logger import get_logger

logger = get_logger(__name__)

from controlbot.handlers import (
    add_source,
    remove_source,
    list_sources,
    link_source,
    unlink_source,
    add_dest,
    remove_dest,
    list_dests,
    set_dest,
    show_dest,
    clear_dest,
    add_replace,
    remove_replace,
    list_replaces,
    add_block,
    remove_block,
    list_blocks,
    set_header,
    set_footer,
    clear_header,
    clear_footer,
    status,
    pause,
    resume,
    stats,
    start_cmd,
    help_cmd,
    handle_callback,
    set_delay,
    _get_admin_id,
    _escape_html,
)
from database.db import Database

logger = get_logger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


async def _register_commands(app: Application) -> None:
    """Register all bot commands with Telegram for auto-suggest menu."""
    commands = [
        BotCommand("start", "🚀 Start & show all commands"),
        BotCommand("help", "📖 Show help & all commands"),
        BotCommand("add_source", "📡 Add source (@user/ID/link)"),
        BotCommand("remove_source", "🗑️ Remove a source"),
        BotCommand("list_sources", "📋 List all sources & routes"),
        BotCommand("add_dest", "🎯 Add a new destination"),
        BotCommand("remove_dest", "🗑️ Remove a destination"),
        BotCommand("list_dests", "📋 Show all destinations"),
        BotCommand("link_source", "🔗 Link source to a destination"),
        BotCommand("unlink_source", "➖ Unlink source from a destination"),
        BotCommand("set_dest", "⭐ Set global default destination"),
        BotCommand("show_dest", "👁️ Show global destination"),
        BotCommand("clear_dest", "🗑️ Clear global destination"),
        BotCommand("add_replace", "✂️ Add word replacement rule"),
        BotCommand("remove_replace", "🗑️ Remove a replacement rule"),
        BotCommand("list_replaces", "📋 List all replacements"),
        BotCommand("add_block", "🚫 Block posts with a word"),
        BotCommand("remove_block", "🗑️ Remove block rule"),
        BotCommand("list_blocks", "📋 List blocked words"),
        BotCommand("set_header", "📌 Set header text"),
        BotCommand("set_footer", "📌 Set footer text"),
        BotCommand("clear_header", "🗑️ Remove header"),
        BotCommand("clear_footer", "🗑️ Remove footer"),
        BotCommand("status", "📊 Bot status dashboard"),
        BotCommand("pause", "⏸️ Pause forwarding"),
        BotCommand("resume", "▶️ Resume forwarding"),
        BotCommand("stats", "📈 Statistics & recent activity"),
        BotCommand("set_delay", "⏱️ Set forward delay (seconds)"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Registered %d commands with Telegram.", len(commands))


def build_application(db: Database) -> Application:
    """
    Build and return a configured PTB Application instance.

    Args:
        db: Shared Database instance (passed via bot_data)
    """
    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)

    token = cfg["bot_token"]

    app = Application.builder().token(token).post_init(_register_commands).build()

    # Inject DB into bot_data so handlers can access it
    app.bot_data["db"] = db

    # ── Register command handlers ──
    _add_handler(app, "start", start_cmd)
    _add_handler(app, "help", help_cmd)

    # Source management
    _add_handler(app, "add_source", add_source)
    _add_handler(app, "remove_source", remove_source)
    _add_handler(app, "list_sources", list_sources)

    # Destination management
    _add_handler(app, "add_dest", add_dest)
    _add_handler(app, "remove_dest", remove_dest)
    _add_handler(app, "list_dests", list_dests)
    _add_handler(app, "set_dest", set_dest)
    _add_handler(app, "show_dest", show_dest)
    _add_handler(app, "clear_dest", clear_dest)

    # Routing
    _add_handler(app, "link_source", link_source)
    _add_handler(app, "unlink_source", unlink_source)

    # Replace rules
    _add_handler(app, "add_replace", add_replace)
    _add_handler(app, "remove_replace", remove_replace)
    _add_handler(app, "list_replaces", list_replaces)

    # Block rules
    _add_handler(app, "add_block", add_block)
    _add_handler(app, "remove_block", remove_block)
    _add_handler(app, "list_blocks", list_blocks)

    # Header / Footer
    _add_handler(app, "set_header", set_header)
    _add_handler(app, "set_footer", set_footer)
    _add_handler(app, "clear_header", clear_header)
    _add_handler(app, "clear_footer", clear_footer)

    # Bot control
    _add_handler(app, "status", status)
    _add_handler(app, "pause", pause)
    _add_handler(app, "resume", resume)
    _add_handler(app, "stats", stats)
    _add_handler(app, "set_delay", set_delay)

    # Callback queries (inline buttons)
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Global error handler ──
    app.add_error_handler(_on_ptb_error)

    logger.info("Control bot handlers registered")

    return app


async def _on_ptb_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Global PTB error handler — logs the exception and notifies the admin
    on Telegram so silent failures don't leave the admin wondering.
    """
    logger.error("Unhandled exception in PTB handler:", exc_info=context.error)

    try:
        chat_id = None
        if isinstance(update, Update) and update.effective_chat:
            chat_id = update.effective_chat.id
        elif isinstance(update, Update) and update.callback_query:
            chat_id = (
                update.callback_query.message.chat_id
                if update.callback_query.message
                else None
            )

        if chat_id is not None:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "⚠️ <b>Internal Error</b>\n\n"
                    f"Something went wrong: <code>{_escape_html(type(context.error).__name__)}</code>\n"
                    "Check logs on the server for full traceback."
                ),
                parse_mode="HTML",
            )
    except Exception:
        # Last-resort guard — don't let the error handler itself crash the poll loop
        logger.exception("Error handler itself failed")


def _add_handler(app: Application, command: str, handler) -> None:
    """Register a CommandHandler if the handler is not None."""
    if handler is not None:
        app.add_handler(CommandHandler(command, handler))
