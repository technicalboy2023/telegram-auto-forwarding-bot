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


# ────────────────────────────────────────────────────────────
#  Source Channel Management
# ────────────────────────────────────────────────────────────

async def add_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /add_source @channel"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Usage: `/add_source @channel`\n\nExample: `/add_source @DealsChannel`",
        )
        return

    username = args[0].lstrip("@").strip()
    if db.add_source(username):
        await update.message.reply_text(f"✅ Source channel `@{username}` added successfully!")
    else:
        await update.message.reply_text(f"⚠️ `@{username}` is already in your source list.")


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


async def list_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /list_sources"""
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]

    sources = db.get_all_sources()
    if not sources:
        await update.message.reply_text("📭 No source channels configured.\nUse `/add_source @channel` to add one.")
        return

    lines = ["📡 *Source Channels:*"]
    for i, s in enumerate(sources, 1):
        lines.append(f"  {i}\\. `@{s['username']}` — added {s['added_at']}")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


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
        await update.message.reply_text("📭 No replace rules configured.\nUse `/add_replace Old➜New` to create one.")
        return

    lines = ["✂️ *Replace Rules:*"]
    for i, r in enumerate(rules, 1):
        new = f"`{r['new_word']}`" if r["new_word"] else "(removed)"
        lines.append(f"  {i}\\. `{_escape_md(r['old_word'])}` → {new}")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


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
        await update.message.reply_text("📭 No block rules configured.\nUse `/add_block Word` to create one.")
        return

    lines = ["🚫 *Blocked Words:*"]
    for i, r in enumerate(rules, 1):
        lines.append(f"  {i}\\. `{_escape_md(r['word'])}`")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


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

    lines = [
        f"🤖 *Bot Status: {pause_text}*",
        "",
        f"📡 Sources: `{stats['source_count']}`",
        f"🎯 Destination: `@{dest or 'NOT SET'}`",
        f"⏱️ Forward Delay: `{stats['forward_delay']}s`",
        "",
        f"✅ Forwarded: `{stats['total_forwarded']}`",
        f"⛔ Skipped: `{stats['total_skipped']}`",
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
        "\n".join(lines), parse_mode="MarkdownV2", reply_markup=keyboard,
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
        lines.append("*Recent Activity:*")
        for r in recent:
            emoji = "✅" if r["status"] == "forwarded" else "⛔"
            lines.append(f"  {emoji} `@{r.get('source', '?')}` — {r['forwarded_at']}")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2")


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
        await query.answer("Forwarding paused.")
        await query.edit_message_text(
            query.message.text.replace("▶️ RUNNING", "⏸️ PAUSED"),
            reply_markup=query.message.reply_markup,
            parse_mode="MarkdownV2",
        )
    elif data == "resume":
        db.set_paused(False)
        await query.answer("Forwarding resumed.")
        await query.edit_message_text(
            query.message.text.replace("⏸️ PAUSED", "▶️ RUNNING"),
            reply_markup=query.message.reply_markup,
            parse_mode="MarkdownV2",
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
        "⚙️ *Control:*\n"
        "  `/status` — Current status\n"
        "  `/pause` — Pause forwarding\n"
        "  `/resume` — Resume forwarding\n"
        "  `/stats` — Statistics\n"
        "  `/set_delay 5` — Set delay between forwards \(seconds\)\n",
        parse_mode="MarkdownV2",
    )


# ────────────────────────────────────────────────────────────
#  Help handler
# ────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler: /help — alias for start."""
    await start_cmd(update, context)
