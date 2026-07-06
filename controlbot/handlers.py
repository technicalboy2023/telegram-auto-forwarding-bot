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


def _escape_md(text: str) -> str:
    """Escape Markdown special characters."""
    special = r"_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


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
            "  `/add_source @channel` — use global /set_dest bot\n"
            "  `/add_source @channel @destinationBot` — set destination\n\n"
            "Examples:\n"
            "  `/add_source @DealsChannel`\n"
            "  `/add_source @DealsChannel @CueLinksBot`\n",
        )
        return

    username = args[0].lstrip("@").strip()
    dest = args[1].lstrip("@").strip() if len(args) >= 2 else None
    if dest and not dest:
        await update.message.reply_text("❌ Destination bot username cannot be empty.")
        return

    if db.add_source(username, dest=dest):
        if dest:
            await update.message.reply_text(
                f"✅ Source channel `@{username}` added!\n"
                f"📡 Forwarding to `@{dest}`.\n"
                f"Use `/add_dest @{username} @Bot2` to add more destinations.",
            )
        else:
            await update.message.reply_text(
                f"✅ Source channel `@{username}` added!\n"
                f"📡 Will forward to the global destination (set via `/set_dest @bot`).",
            )
    else:
        await update.message.reply_text(
            f"⚠️ `@{username}` is already in your source list.\n"
            f"Use `/set_source_dest @{username} @Bot` to change its destination "
            f"or `/add_dest @{username} @Bot` to add more destinations.",
        )


async def set_source_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /set_source_dest @channel @Bot (or 'default' to clear)"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: `/set_source_dest @channel @Bot`\n\n"
            "Set a per-source EXCLUSIVE destination bot.\n"
            "Pass `default` as the bot to clear the mapping (will use global /set_dest).\n\n"
            "Examples:\n"
            "  `/set_source_dest @technicalgeardeals @CueLinksBot`\n"
            "  `/set_source_dest @btrickdeals @SankmoBot`\n"
            "  `/set_source_dest @btrickdeals default` — clear mapping",
        )
        return

    source = args[0].lstrip("@").strip()
    dest_raw = args[1].strip()

    # 'default' (case-insensitive) clears the mapping
    if dest_raw.lower() in ("default", "reset", "clear", "none", "-"):
        dest: str | None = None
    else:
        dest = dest_raw.lstrip("@").strip() or None

    if db.set_source_destination(source, dest):
        if dest:
            await update.message.reply_text(
                f"✅ Source `@{source}` now forwards EXCLUSIVELY to `@{dest}`.\n"
                f"Other bots will NOT receive posts from this source.",
            )
        else:
            await update.message.reply_text(
                f"✅ Source `@{source}` cleared — will now use the global /set_dest bot.",
            )
    else:
        await update.message.reply_text(
            f"⚠️ Source `@{source}` not found. Add it first with `/add_source @{source}`.",
        )


async def remove_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /remove_source @channel"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: `/remove_source @channel`\n\nExample: `/remove_source @DealsChannel`",
        )
        return

    username = args[0].lstrip("@").strip()
    if db.remove_source(username):
        await update.message.reply_text(f"🗑️ Source channel `@{username}` removed.")
    else:
        await update.message.reply_text(f"⚠️ `@{username}` not found in source list.")


async def add_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /add_dest @Channel @Bot — add a bot to source's multi-dest list."""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: `/add_dest @channel @bot`\n\n"
            "Add another bot destination for a source channel.\n"
            "The source's posts will be forwarded to ALL bots in its destination list.\n\n"
            "Examples:\n"
            "  `/add_dest @technicalgeardeals @cuelinks_bot`\n"
            "  `/add_dest @technicalgeardeals @sankmo_bot`\n"
            "  `/list_dests @technicalgeardeals` — view all destinations",
        )
        return

    source = args[0].lstrip("@").strip()
    bot = args[1].lstrip("@").strip()

    if not source or not bot:
        await update.message.reply_text("❌ Both channel and bot usernames are required.")
        return

    if db.add_source_dest(source, bot):
        await update.message.reply_text(
            f"✅ Added `@{bot}` to `@{source}`'s destination list.\n"
            f"Use `/list_dests @{source}` to see all destinations.",
        )
    else:
        # Try to give a helpful error message
        sources = db.get_all_sources()
        found = any(s["username"] == source for s in sources)
        if not found:
            await update.message.reply_text(
                f"⚠️ Source `@{source}` not found. Add it first with `/add_source @{source}`.",
            )
        else:
            await update.message.reply_text(
                f"⚠️ `@{bot}` is already in `@{source}`'s destination list "
                f"or source not found.\nUse `/list_dests @{source}` to check.",
            )


async def remove_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /remove_dest @Channel @Bot — remove a bot from source's dest list."""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Usage: `/remove_dest @channel @bot`\n\n"
            "Remove a bot from a source's destination list.\n\n"
            "Example:\n"
            "  `/remove_dest @technicalgeardeals @sankmo_bot`",
        )
        return

    source = args[0].lstrip("@").strip()
    bot = args[1].lstrip("@").strip()

    if db.remove_source_dest(source, bot):
        await update.message.reply_text(
            f"🗑️ Removed `@{bot}` from `@{source}`'s destination list.\n"
            f"Use `/list_dests @{source}` to see remaining destinations.",
        )
    else:
        await update.message.reply_text(
            f"⚠️ Could not remove. Check that `@{source}` exists and "
            f"`@{bot}` is in its destination list.",
        )


async def list_dests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /list_dests @Channel — show all dests for a source."""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: `/list_dests @channel`\n\n"
            "Show all destination bots for a source channel.\n"
            "Example: `/list_dests @technicalgeardeals`\n"
            "\n"
            "Tip: Use `/list_sources` to see all sources and their destinations.",
        )
        return

    source = args[0].lstrip("@").strip()

    # Check if source exists
    sources = db.get_all_sources()
    src_info = next((s for s in sources if s["username"] == source), None)
    if not src_info:
        await update.message.reply_text(
            f"⚠️ Source `@{source}` not found.\nUse `/list_sources` to see all sources.",
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
            "📭 No source channels configured.\nUse `/add_source @channel` to add one.",
            parse_mode=None,
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
            "❌ Usage: `/set_dest @BotUsername`\n\nExample: `/set_dest @CueLinksBot`",
        )
        return

    username = args[0].lstrip("@").strip()
    db.set_destination(username)
    await update.message.reply_text(
        f"🎯 Destination bot set to `@{username}`\\!\nAll forwarded posts will be sent here\\.",
        parse_mode="MarkdownV2",
    )


async def show_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /show_dest"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    dest = db.get_destination()
    if dest:
        await update.message.reply_text(f"🎯 Current destination: `@{dest}`")
    else:
        await update.message.reply_text("⚠️ No destination bot set.\nUse `/set_dest @BotUsername` to configure.")


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
            "❌ Usage: `/add_replace OldWord➜NewWord`\n\n"
            "Use the ➜ arrow to separate old and new words.\n"
            "Example: `/add_replace @OldChannel➜@MyChannel`\n"
            "To remove a word entirely, leave the right side empty: `/add_replace @BadChannel➜`",
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
        await update.message.reply_text(f"✅ Replace rule added: `{old_word}` → `{new_word}`")
    else:
        await update.message.reply_text(f"✅ Replace rule added: `{old_word}` → (removed)")


async def remove_replace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /remove_replace OldWord"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: `/remove_replace OldWord`\n\nExample: `/remove_replace @OldChannel`",
        )
        return

    old_word = " ".join(args).strip()
    if db.remove_replace_rule(old_word):
        await update.message.reply_text(f"🗑️ Replace rule for `{old_word}` removed.")
    else:
        await update.message.reply_text(f"⚠️ No replace rule found for `{old_word}`.")


async def list_replaces(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /list_replaces"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    rules = db.get_all_replace_rules()
    if not rules:
        await update.message.reply_text(
            "📭 No replace rules configured.\nUse `/add_replace Old➜New` to create one.",
            parse_mode=None,
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
            "❌ Usage: `/add_block BadWord`\n\n"
            "Posts containing this word will be skipped.\n"
            "Example: `/add_block Join @OtherChannel`",
        )
        return

    word = " ".join(args).strip()
    if db.add_block_rule(word):
        await update.message.reply_text(f"🚫 Block rule added: `{word}`\nPosts containing this will be skipped.")
    else:
        await update.message.reply_text(f"⚠️ `{word}` is already in the block list.")


async def remove_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /remove_block BadWord"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: `/remove_block BadWord`\n\nExample: `/remove_block Join @OtherChannel`",
        )
        return

    word = " ".join(args).strip()
    if db.remove_block_rule(word):
        await update.message.reply_text(f"🗑️ Block rule for `{word}` removed.")
    else:
        await update.message.reply_text(f"⚠️ No block rule found for `{word}`.")


async def list_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /list_blocks"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    rules = db.get_all_block_rules()
    if not rules:
        await update.message.reply_text(
            "📭 No block rules configured.\nUse `/add_block Word` to create one.",
            parse_mode=None,
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
            "❌ Usage: `/set_header Text`\n\n"
            "This text will be added at the TOP of every forwarded post.\n"
            "Example: `/set_header 📢 @MyDealsChannel`",
        )
        return

    text = " ".join(args).strip()
    db.set_header(text)
    await update.message.reply_text(f"📌 Header set:\n\n{text}")


async def set_footer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /set_footer Text"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: `/set_footer Text`\n\n"
            "This text will be added at the BOTTOM of every forwarded post.\n"
            "Example: `/set_footer 🔔 Join @MyDealsChannel for more!`",
        )
        return

    text = " ".join(args).strip()
    db.set_footer(text)
    await update.message.reply_text(f"📌 Footer set:\n\n{text}")


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

    # Build using HTML so the dynamic fields (counts, delay, destination) never
    # break the parser. The whole message is also editable by handle_callback
    # using the same HTML parse mode safely.
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
    await update.message.reply_text("⏸️ Forwarding PAUSED. Use `/resume` to continue.")


async def set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /set_delay seconds"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        current = db.get_forward_delay()
        await update.message.reply_text(
            f"⏱️ Current forward delay: `{current:.1f}s`\n\n"
            "Usage: `/set_delay 5` (seconds, minimum 1)",
        )
        return

    try:
        seconds = float(args[0])
        if seconds < 1.0:
            await update.message.reply_text("❌ Delay must be at least 1 second.")
            return
        db.set_forward_delay(seconds)
        await update.message.reply_text(f"⏱️ Forward delay set to `{seconds:.1f}s`.")
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid number (e.g., `/set_delay 5`).")


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
        "📊 *Statistics*",
        "",
        f"✅ Total Forwarded: `{s['total_forwarded']}`",
        f"⛔ Total Skipped: `{s['total_skipped']}`",
        f"📡 Active Sources: `{s['source_count']}`",
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

    await update.message.reply_text(
        "🤖 *Telegram Auto\\-Forwarding Bot — Admin Panel*\n\n"
        "Welcome\\! Manage your forwarding setup with these commands:\n\n"
        "📡 *Sources:*\n"
        "  `/add_source @channel` — Add source\n"
        "  `/remove_source @channel` — Remove source\n"
        "  `/list_sources` — View all sources\n\n"
        "🎯 *Destination:*\n"
        "  `/set_dest @bot` — Set destination bot\n"
        "  `/show_dest` — View current destination\n\n"
        "✂️ *Customization:*\n"
        "  `/add_replace Old➜New` — Add word replacement\n"
        "  `/remove_replace Old` — Remove replacement\n"
        "  `/list_replaces` — View all replacements\n"
        "  `/add_block Word` — Block posts with this word\n"
        "  `/remove_block Word` — Remove block rule\n"
        "  `/list_blocks` — View all block rules\n"
        "  `/set_header Text` — Add header\n"
        "  `/set_footer Text` — Add footer\n"
        "  `/clear_header` — Remove header\n"
        "  `/clear_footer` — Remove footer\n\n"
        "🎯 *Multi-Destination:*\n"
        "  `/add_dest @channel @bot` — Add another destination bot\n"
        "  `/remove_dest @channel @bot` — Remove destination bot\n"
        "  `/list_dests @channel` — View all destinations of a source\n"
        "  `/set_source_dest @channel @bot` — Set/change single destination\n\n"
        "⚙️ *Control:*\n"
        "  `/status` — Current status\n"
        "  `/pause` — Pause forwarding\n"
        "  `/resume` — Resume forwarding\n"
        "  `/stats` — Statistics\n"
        "  `/set_delay 5` — Set delay between forwards " r"\(seconds\)" "\n",
        parse_mode="MarkdownV2",
    )


# ────────────────────────────────────────────────────────────
#  Help handler
# ────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /help — alias for start."""
    await start_cmd(update, context)
