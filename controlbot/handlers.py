"""
Command handlers for the Control Bot (admin panel).

All handlers check admin_id before executing any command.
Each handler is a coroutine that takes (update, context) from python-telegram-bot.
"""

import json
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database.db import Database
from utils.logger import get_logger

logger = get_logger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.json"


# ────────────────────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────────────────────

def _get_admin_id() -> int:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)["admin_id"]


def _is_admin(update: Update) -> bool:
    """Check if the message sender is the configured admin."""
    user = update.effective_user
    admin_id = _get_admin_id()
    return user is not None and user.id == admin_id


async def _admin_only(update: Update) -> bool:
    """Guard decorator — reply and return False if not admin."""
    if not _is_admin(update):
        await update.message.reply_text("⛔ Access denied. Admin only.")
        return False
    return True


def _escape_html(text: str) -> str:
    """Escape HTML special characters for safe telegram HTML parse_mode."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ────────────────────────────────────────────────────────────
#  Source Channel Management
# ────────────────────────────────────────────────────────────

async def add_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /add_source @channel [@destinationBot]

    With one arg  → adds source, posts will use the global /set_dest bot.
    With two args → adds source with a destination (per-source mapping).
    """
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage:\n"
            "  <code>/add_source @channel</code> — use global /set_dest bot\n"
            "  <code>/add_source @channel @destinationBot</code> — set destination\n\n"
            "Examples:\n"
            "  <code>/add_source @DealsChannel</code>\n"
            "  <code>/add_source @DealsChannel @CueLinksBot</code>",
            parse_mode="HTML",
        )
        return

    username = args[0].lstrip("@").strip()
    dest = args[1].lstrip("@").strip() if len(args) >= 2 else None
    if db.add_source(username, dest=dest):
        if dest:
            await update.message.reply_text(
                f"✅ Source channel <code>@{_escape_html(username)}</code> added!\n"
                f"📡 Forwarding to <code>@{_escape_html(dest)}</code>.\n"
                f"Use <code>/add_dest @{_escape_html(username)} @Bot2</code> to add more destinations.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"✅ Source channel <code>@{_escape_html(username)}</code> added!\n"
                f"📡 Will forward to the global destination (set via <code>/set_dest @bot</code>).",
                parse_mode="HTML",
            )
    else:
        await update.message.reply_text(
            f"⚠️ <code>@{_escape_html(username)}</code> is already in your source list.\n"
            f"Use <code>/set_source_dest @{_escape_html(username)} @Bot</code> to change its destination "
            f"or <code>/add_dest @{_escape_html(username)} @Bot</code> to add more destinations.",
            parse_mode="HTML",
        )


async def set_source_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /set_source_dest @channel @Bot (or 'default' to clear)"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
"❌ Usage: <code>/set_source_dest @channel @Bot</code>\n\n"
            "Set a per-source EXCLUSIVE destination bot.\n"
            "Pass <code>default</code> as the bot to clear the mapping (will use global /set_dest).\n\n"
            "Examples:\n"
            "  <code>/set_source_dest @technicalgeardeals @CueLinksBot</code>\n"
            "  <code>/set_source_dest @btrickdeals @SankmoBot</code>\n"
            "  <code>/set_source_dest @btrickdeals default</code> — clear mapping",
            parse_mode="HTML",
        )
        return

    source = args[0].lstrip("@").strip()
    dest_raw = args[1].strip()

    if dest_raw.lower() in ("default", "reset", "clear", "none", "-"):
        dest: str | None = None
    else:
        dest = dest_raw.lstrip("@").strip() or None

    if db.set_source_destination(source, dest):
        if dest:
            await update.message.reply_text(
                f"✅ Source <code>@{_escape_html(source)}</code> now forwards EXCLUSIVELY to <code>@{_escape_html(dest)}</code>.\n"
                f"Other bots will NOT receive posts from this source.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"✅ Source <code>@{_escape_html(source)}</code> cleared — will now use the global /set_dest bot.",
                parse_mode="HTML",
            )
    else:
        await update.message.reply_text(
            f"⚠️ Source <code>@{_escape_html(source)}</code> not found. Add it first with <code>/add_source @{_escape_html(source)}</code>.",
            parse_mode="HTML",
        )


async def remove_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /remove_source @channel"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: <code>/remove_source @channel</code>\n\n"
            "Example: <code>/remove_source @DealsChannel</code>",
            parse_mode="HTML",
        )
        return

    username = args[0].lstrip("@").strip()
    if db.remove_source(username):
        await update.message.reply_text(
            f"🗑️ Source channel <code>@{_escape_html(username)}</code> removed.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ <code>@{_escape_html(username)}</code> not found in source list.",
            parse_mode="HTML",
        )


async def add_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /add_dest @Channel @Bot — add a bot to source's multi-dest list."""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: <code>/add_dest @channel @bot</code>\n\n"
            "Add another bot destination for a source channel.\n"
            "The source's posts will be forwarded to ALL bots in its destination list.\n\n"
            "Examples:\n"
            "  <code>/add_dest @technicalgeardeals @cuelinks_bot</code>\n"
            "  <code>/add_dest @technicalgeardeals @sankmo_bot</code>\n"
            "  <code>/list_dests @technicalgeardeals</code> — view all destinations",
            parse_mode="HTML",
        )
        return

    source = args[0].lstrip("@").strip()
    bot = args[1].lstrip("@").strip()

    if not source or not bot:
        await update.message.reply_text("❌ Both channel and bot usernames are required.")
        return

    if db.add_source_dest(source, bot):
        await update.message.reply_text(
            f"✅ Added <code>@{_escape_html(bot)}</code> to <code>@{_escape_html(source)}</code>'s destination list.\n"
            f"Use <code>/list_dests @{_escape_html(source)}</code> to see all destinations.",
            parse_mode="HTML",
        )
    else:
        sources = db.get_all_sources()
        found = any(s["username"] == source for s in sources)
        if not found:
            await update.message.reply_text(
                f"⚠️ Source <code>@{_escape_html(source)}</code> not found. Add it first with <code>/add_source @{_escape_html(source)}</code>.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"⚠️ <code>@{_escape_html(bot)}</code> is already in <code>@{_escape_html(source)}</code>'s destination list.\n"
                f"Use <code>/list_dests @{_escape_html(source)}</code> to check.",
                parse_mode="HTML",
            )


async def remove_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /remove_dest @Channel @Bot — remove a bot from source's dest list."""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: <code>/remove_dest @channel @bot</code>\n\n"
            "Remove a bot from a source's destination list.\n\n"
            "Example:\n"
            "  <code>/remove_dest @technicalgeardeals @sankmo_bot</code>",
            parse_mode="HTML",
        )
        return

    source = args[0].lstrip("@").strip()
    bot = args[1].lstrip("@").strip()

    if db.remove_source_dest(source, bot):
        await update.message.reply_text(
            f"🗑️ Removed <code>@{_escape_html(bot)}</code> from <code>@{_escape_html(source)}</code>'s destination list.\n"
            f"Use <code>/list_dests @{_escape_html(source)}</code> to see remaining destinations.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ Could not remove. Check that <code>@{_escape_html(source)}</code> exists and "
            f"<code>@{_escape_html(bot)}</code> is in its destination list.",
            parse_mode="HTML",
        )


async def list_dests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /list_dests @Channel — show all dests for a source."""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: <code>/list_dests @channel</code>\n\n"
            "Show all destination bots for a source channel.\n"
            "Example: <code>/list_dests @technicalgeardeals</code>\n\n"
            "Tip: Use <code>/list_sources</code> to see all sources and their destinations.",
            parse_mode="HTML",
        )
        return

    source = args[0].lstrip("@").strip()

    # Check if source exists
    sources = db.get_all_sources()
    src_info = next((s for s in sources if s["username"] == source), None)
    if not src_info:
        await update.message.reply_text(
            f"⚠️ Source <code>@{_escape_html(source)}</code> not found.\n"
            f"Use <code>/list_sources</code> to see all sources.",
            parse_mode="HTML",
        )
        return

    dests = db.get_source_dests(source)
    fallback = src_info.get("destination")
    global_dest = db.get_destination()

    lines = [f"📡 <b>Destinations for @{_escape_html(source)}:</b>", ""]

    if dests:
        for i, d in enumerate(dests, 1):
            lines.append(f"  {i}. <code>@{_escape_html(d)}</code>")
    else:
        lines.append("  <i>No multi-destination list set.</i>")

    lines.append("")
    if fallback:
        lines.append(f"<i>Single dest column:</i> <code>@{_escape_html(fallback)}</code>")
    if global_dest:
        lines.append(f"<i>Global default:</i> <code>@{_escape_html(global_dest)}</code>")

    lines.append("")
    lines.append("<i>Use <code>/add_dest @Channel @Bot</code> to add more.</i>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def list_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /list_sources"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    sources = db.get_all_sources()
    if not sources:
        await update.message.reply_text(
            "📭 No source channels configured.\n"
            r"Use <code>/add_source @channel</code> to add one.",
            parse_mode="HTML",
        )
        return

    lines = ["📡 <b>Source Channels & Their Destinations:</b>", ""]
    for i, s in enumerate(sources, 1):
        username = _escape_html(s["username"])
        added_at = _escape_html(s["added_at"])

        # Check multi-dest first
        dests = db.get_source_dests(s["username"])
        per_source_dest = s.get("destination")

        if dests:
            bots = ", ".join(f"<code>@{_escape_html(d)}</code>" for d in dests)
            dest_html = f"→ {bots}"
        elif per_source_dest:
            dest_html = f"→ <code>@{_escape_html(per_source_dest)}</code> (single)"
        else:
            global_dest = db.get_destination() or "NOT SET"
            dest_html = f"→ <i>global</i> <code>@{_escape_html(global_dest)}</code>"

        lines.append(f"  {i}. <code>@{username}</code> {dest_html}")
        lines.append(f"     <i>added {added_at}</i>")

    lines.append("")
    lines.append("<i>Use <code>/add_dest @Channel @Bot</code> to add more destinations.</i>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  Destination Bot Management
# ────────────────────────────────────────────────────────────

async def set_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /set_dest @BotUsername"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: <code>/set_dest @BotUsername</code>\n\n"
            "Example: <code>/set_dest @CueLinksBot</code>",
            parse_mode="HTML",
        )
        return

    username = args[0].lstrip("@").strip()
    db.set_destination(username)
    await update.message.reply_text(
        f"🎯 Destination bot set to <code>@{_escape_html(username)}</code>!\n"
        "All forwarded posts will be sent here.",
        parse_mode="HTML",
    )


async def show_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /show_dest"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    dest = db.get_destination()
    if dest:
        await update.message.reply_text(
            f"🎯 Current destination: <code>@{_escape_html(dest)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "⚠️ No destination bot set.\n"
            "Use <code>/set_dest @BotUsername</code> to configure.",
            parse_mode="HTML",
        )


# ────────────────────────────────────────────────────────────
#  Word Replacement Rules
# ────────────────────────────────────────────────────────────

async def add_replace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /add_replace OldWord➜NewWord"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = " ".join(context.args) if context.args else ""
    if not args or "➜" not in args:
        await update.message.reply_text(
            "❌ Usage: <code>/add_replace OldWord➜NewWord</code>\n\n"
            "Use the ➜ arrow to separate old and new words.\n"
            "Example: <code>/add_replace @OldChannel➜@MyChannel</code>\n"
            "To remove a word entirely, leave the right side empty: <code>/add_replace @BadChannel➜</code>",
            parse_mode="HTML",
        )
        return

    parts = args.split("➜", 1)
    old_word = parts[0].strip()
    new_word = parts[1].strip() if len(parts) > 1 else ""

    if not old_word:
        await update.message.reply_text("❌ Old word cannot be empty.")
        return

    db.add_replace_rule(old_word, new_word)
    if new_word:
        await update.message.reply_text(
            f"✅ Replace rule added: <code>{_escape_html(old_word)}</code> → <code>{_escape_html(new_word)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"✅ Replace rule added: <code>{_escape_html(old_word)}</code> → (removed)",
            parse_mode="HTML",
        )


async def remove_replace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /remove_replace OldWord"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: <code>/remove_replace OldWord</code>\n\n"
            "Example: <code>/remove_replace @OldChannel</code>",
            parse_mode="HTML",
        )
        return

    old_word = " ".join(args).strip()
    if db.remove_replace_rule(old_word):
        await update.message.reply_text(
            f"🗑️ Replace rule for <code>{_escape_html(old_word)}</code> removed.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ No replace rule found for <code>{_escape_html(old_word)}</code>.",
            parse_mode="HTML",
        )


async def list_replaces(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /list_replaces"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    rules = db.get_all_replace_rules()
    if not rules:
        await update.message.reply_text(
            "📭 No replace rules configured.\n"
            r"Use <code>/add_replace Old➜New</code> to create one.",
            parse_mode="HTML",
        )
        return

    lines = ["✂️ <b>Replace Rules:</b>"]
    for i, r in enumerate(rules, 1):
        old = _escape_html(r["old_word"])
        if r["new_word"]:
            new = f"<code>{_escape_html(r['new_word'])}</code>"
        else:
            new = "(removed)"
        lines.append(f"  {i}. <code>{old}</code> → {new}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  Word Block Rules
# ────────────────────────────────────────────────────────────

async def add_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /add_block BadWord"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: <code>/add_block BadWord</code>\n\n"
            "Posts containing this word will be skipped.\n"
            "Example: <code>/add_block Join @OtherChannel</code>",
            parse_mode="HTML",
        )
        return

    word = " ".join(args).strip()
    if db.add_block_rule(word):
        await update.message.reply_text(
            f"🚫 Block rule added: <code>{_escape_html(word)}</code>\n"
            f"Posts containing this will be skipped.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ <code>{_escape_html(word)}</code> is already in the block list.",
            parse_mode="HTML",
        )


async def remove_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /remove_block BadWord"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: <code>/remove_block BadWord</code>\n\n"
            "Example: <code>/remove_block Join @OtherChannel</code>",
            parse_mode="HTML",
        )
        return

    word = " ".join(args).strip()
    if db.remove_block_rule(word):
        await update.message.reply_text(
            f"🗑️ Block rule for <code>{_escape_html(word)}</code> removed.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ No block rule found for <code>{_escape_html(word)}</code>.",
            parse_mode="HTML",
        )


async def list_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /list_blocks"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    rules = db.get_all_block_rules()
    if not rules:
        await update.message.reply_text(
            "📭 No block rules configured.\n" r"Use <code>/add_block Word</code> to create one.",
            parse_mode="HTML",
        )
        return

    lines = ["🚫 <b>Blocked Words:</b>"]
    for i, r in enumerate(rules, 1):
        lines.append(f"  {i}. <code>{_escape_html(r['word'])}</code>")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  Header / Footer
# ────────────────────────────────────────────────────────────

async def set_header(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /set_header Text"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: <code>/set_header Text</code>\n\n"
            "This text will be added at the TOP of every forwarded post.\n"
            "Example: <code>/set_header 📢 @MyDealsChannel</code>",
            parse_mode="HTML",
        )
        return

    text = " ".join(args).strip()
    db.set_header(text)
    await update.message.reply_text(
        f"📌 Header set:\n\n{_escape_html(text)}",
        parse_mode="HTML",
    )


async def set_footer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /set_footer Text"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: <code>/set_footer Text</code>\n\n"
            "This text will be added at the BOTTOM of every forwarded post.\n"
            "Example: <code>/set_footer 🔔 Join @MyDealsChannel for more!</code>",
            parse_mode="HTML",
        )
        return

    text = " ".join(args).strip()
    db.set_footer(text)
    await update.message.reply_text(
        f"📌 Footer set:\n\n{_escape_html(text)}",
        parse_mode="HTML",
    )


async def clear_header(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /clear_header"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    db.clear_header()
    await update.message.reply_text("🗑️ Header cleared.")


async def clear_footer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /clear_footer"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    db.clear_footer()
    await update.message.reply_text("🗑️ Footer cleared.")


# ────────────────────────────────────────────────────────────
#  Bot Control
# ────────────────────────────────────────────────────────────

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /status"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    stats = db.get_all_stats()
    dest = db.get_destination()
    header = db.get_header()
    footer = db.get_footer()

    pause_text = "⏸️ PAUSED" if stats["paused"] else "▶️ RUNNING"

    safe_dest = _escape_html(dest) if dest else _escape_html("NOT SET")
    lines = [
        f"🤖 <b>Bot Status: {pause_text}</b>",
        "",
        f"📡 Sources: <code>{stats['source_count']}</code>",
        f"🎯 Destination: <code>@{safe_dest}</code>",
        f"⏱️ Forward Delay: <code>{stats['forward_delay']}s</code>",
        "",
        f"✅ Forwarded: <code>{stats['total_forwarded']}</code>",
        f"⛔ Skipped: <code>{stats['total_skipped']}</code>",
        f"📌 Header: {'Set' if header else 'Not set'}",
        f"📌 Footer: {'Set' if footer else 'Not set'}",
    ]

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏸️ Pause", callback_data="pause"),
            InlineKeyboardButton("▶️ Resume", callback_data="resume"),
        ]
    ])

    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=keyboard,
    )


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /pause"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    db.set_paused(True)
    await update.message.reply_text(
        "⏸️ Forwarding PAUSED. Use <code>/resume</code> to continue.",
        parse_mode="HTML",
    )


async def set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /set_delay seconds"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        current = db.get_forward_delay()
        await update.message.reply_text(
            f"⏱️ Current forward delay: <code>{current:.1f}s</code>\n\n"
            "Usage: <code>/set_delay 5</code> (seconds, minimum 1)",
            parse_mode="HTML",
        )
        return

    try:
        seconds = float(args[0])
        if seconds < 1.0:
            await update.message.reply_text("❌ Delay must be at least 1 second.")
            return
        db.set_forward_delay(seconds)
        await update.message.reply_text(
            f"⏱️ Forward delay set to <code>{seconds:.1f}s</code>.",
            parse_mode="HTML",
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Please provide a valid number (e.g., <code>/set_delay 5</code>).",
            parse_mode="HTML",
        )


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /resume"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    db.set_paused(False)
    await update.message.reply_text("▶️ Forwarding RESUMED.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /stats"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    s = db.get_all_stats()
    recent = db.get_recent_history(10)

    lines = [
        "📊 <b>Statistics</b>",
        "",
        f"✅ Total Forwarded: <code>{s['total_forwarded']}</code>",
        f"⛔ Total Skipped: <code>{s['total_skipped']}</code>",
        f"📡 Active Sources: <code>{s['source_count']}</code>",
        "",
    ]

    if recent:
        lines.append("<b>Recent Activity:</b>")
        for r in recent:
            emoji = "✅" if r["status"] == "forwarded" else "⛔"
            source = _escape_html(r.get("source") or "?")
            ts = _escape_html(r["forwarded_at"])
            lines.append(f"  {emoji} <code>@{source}</code> — {ts}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  Callback Query Handler (inline buttons)
# ────────────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button presses from status message."""
    query = update.callback_query
    if not _is_admin(update):
        await query.answer("Access denied.", show_alert=True)
        return

    db: Database = context.bot_data["db"]
    data = query.data

    if data == "pause":
        db.set_paused(True)
        # Toggle the keyboard so the only remaining button is "Resume".
        # This avoids editing the message text (which would lose HTML
        # formatting when re-sent as plain text) and avoids any
        # MarkdownV2 escape-parsing failures on rendered dots like "5.0s".
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Resume", callback_data="resume")]
        ])
        await query.edit_message_reply_markup(reply_markup=keyboard)
        # Send a separate short confirmation (plain text, no parse_mode risks).
        await query.answer("Forwarding paused.")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⏸️ Forwarding PAUSED. Use /resume or the button below to resume.",
        )
    elif data == "resume":
        db.set_paused(False)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ Pause", callback_data="pause")]
        ])
        await query.edit_message_reply_markup(reply_markup=keyboard)
        await query.answer("Forwarding resumed.")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="▶️ Forwarding RESUMED.",
        )


# ────────────────────────────────────────────────────────────
#  Start / Help
# ────────────────────────────────────────────────────────────

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /start — show welcome + available commands."""
    if not await _admin_only(update):
        return

    lines = [
        "🤖 <b>Telegram Auto-Forwarding Bot — Admin Panel</b>",
        "",
        "Welcome! Manage your forwarding setup with these commands:",
        "",
        "📡 <b>Sources:</b>",
        "  <code>/add_source @channel</code> — Add source",
        "  <code>/remove_source @channel</code> — Remove source",
        "  <code>/list_sources</code> — View all sources",
        "",
        "🎯 <b>Destination:</b>",
        "  <code>/set_dest @bot</code> — Set global destination bot",
        "  <code>/show_dest</code> — View current global destination",
        "",
        "📡 <b>Per-Source Mapping:</b>",
        "  <code>/set_source_dest @channel @bot</code> — Set exclusive dest",
        "  <code>/add_dest @channel @bot</code> — Add extra dest",
        "  <code>/remove_dest @channel @bot</code> — Remove dest",
        "  <code>/list_dests @channel</code> — View all dests for a source",
        "",
        "✂️ <b>Customization:</b>",
        "  <code>/add_replace Old➜New</code> — Add word replacement",
        "  <code>/remove_replace Old</code> — Remove replacement",
        "  <code>/list_replaces</code> — View all replacements",
        "  <code>/add_block Word</code> — Block posts with this word",
        "  <code>/remove_block Word</code> — Remove block rule",
        "  <code>/list_blocks</code> — View all block rules",
        "  <code>/set_header Text</code> — Add header",
        "  <code>/set_footer Text</code> — Add footer",
        "  <code>/clear_header</code> — Remove header",
        "  <code>/clear_footer</code> — Remove footer",
        "",
        "⚙️ <b>Control:</b>",
        "  <code>/status</code> — Current status",
        "  <code>/pause</code> — Pause forwarding",
        "  <code>/resume</code> — Resume forwarding",
        "  <code>/stats</code> — Statistics",
        "  <code>/set_delay 5</code> — Set delay between forwards (seconds)",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  Help handler
# ────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /help — alias for start."""
    await start_cmd(update, context)
