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
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ────────────────────────────────────────────────────────────
#  Source Channel Management
# ────────────────────────────────────────────────────────────


async def add_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ Usage: /add_source <@username|ID|InviteLink>"
        )
        return

    identifier = context.args[0].strip()
    db: Database = context.bot_data["db"]

    if db.add_source(identifier):
        await update.message.reply_text(
            f"✅ <b>Source Added</b>\n\n"
            f"Identifier: <code>{_escape_html(identifier)}</code>\n\n"
            f"<i>The bot will try to resolve this entity in the background.</i>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ This source is already in the list.")


async def remove_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /remove_source <identifier>")
        return

    identifier = context.args[0].strip()
    db: Database = context.bot_data["db"]

    if db.remove_source(identifier):
        await update.message.reply_text(
            f"✅ Removed source: <code>{_escape_html(identifier)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ Source not found.")


async def list_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    sources = db.get_all_sources()

    if not sources:
        await update.message.reply_text("📭 No source channels are being monitored.")
        return

    lines = ["📡 <b>Monitored Sources:</b>\n"]
    for src in sources:
        title = src["title"] if src["title"] else "Unknown"
        ident = src["identifier"]
        lines.append(f"🔸 <b>{_escape_html(title)}</b>")
        lines.append(f"   Identifier: <code>{_escape_html(ident)}</code>")
        if src["entity_type"] != "unknown":
            lines.append(f"   Type: <i>{src['entity_type']}</i>")

        routes = db.get_routes_for_source(src["id"])
        if routes:
            r_str = ", ".join(r["identifier"] for r in routes)
            lines.append(f"   Routes: {r_str}")
        else:
            lines.append("   Routes: (Global Default)")
        lines.append("")

    # Split into chunks if too long
    msg = "\n".join(lines)
    for i in range(0, len(msg), 4000):
        await update.message.reply_text(msg[i : i + 4000], parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  Destination Management
# ────────────────────────────────────────────────────────────


async def add_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /add_dest <@username|ID>")
        return

    identifier = context.args[0].strip()
    db: Database = context.bot_data["db"]

    if db.add_destination(identifier):
        await update.message.reply_text(
            f"✅ <b>Destination Added:</b> <code>{_escape_html(identifier)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ Destination already exists.")


async def remove_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /remove_dest <identifier>")
        return

    identifier = context.args[0].strip()
    db: Database = context.bot_data["db"]

    if db.remove_destination(identifier):
        await update.message.reply_text(
            f"✅ Removed destination: <code>{_escape_html(identifier)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ Destination not found.")


async def list_dests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    dests = db.get_all_destinations()

    if not dests:
        await update.message.reply_text(
            "📭 No destinations registered. Use /add_dest first."
        )
        return

    lines = ["🎯 <b>Registered Destinations:</b>\n"]
    for dst in dests:
        title = dst["title"] if dst["title"] else "Unknown"
        lines.append(
            f"🔸 <b>{_escape_html(title)}</b> (<code>{_escape_html(dst['identifier'])}</code>) - <i>{dst['entity_type']}</i>"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def set_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text(
            "⚠️ Usage: /set_dest <identifier>\nMake sure to add it via /add_dest first!"
        )
        return

    identifier = context.args[0].strip()
    db: Database = context.bot_data["db"]

    if db.set_default_dest(identifier):
        await update.message.reply_text(
            f"✅ Global default destination set to <code>{_escape_html(identifier)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "⚠️ Destination not found. Add it using /add_dest first."
        )


async def show_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    dest = db.get_default_dest()

    if dest:
        await update.message.reply_text(
            f"🎯 Global Default: <code>{_escape_html(dest['identifier'])}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("📭 No global destination set.")


async def clear_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    db.clear_default_dest()
    await update.message.reply_text("🗑️ Global default destination cleared.")


# ────────────────────────────────────────────────────────────
#  Routing
# ────────────────────────────────────────────────────────────


async def link_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Usage: /link_source <source_ident> <dest_ident>\nBoth must exist in DB."
        )
        return

    source_ident = context.args[0].strip()
    dest_ident = context.args[1].strip()
    db: Database = context.bot_data["db"]

    if db.add_route(source_ident, dest_ident):
        await update.message.reply_text(
            f"✅ Linked <code>{_escape_html(source_ident)}</code> ➜ <code>{_escape_html(dest_ident)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "⚠️ Failed. Check if both identifiers exist and aren't already linked."
        )


async def unlink_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Usage: /unlink_source <source_ident> <dest_ident|all>"
        )
        return

    source_ident = context.args[0].strip()
    dest_ident = context.args[1].strip()
    db: Database = context.bot_data["db"]

    if dest_ident.lower() == "all":
        count = db.remove_all_routes_for_source(source_ident)
        await update.message.reply_text(
            f"✅ Removed {count} routes for <code>{_escape_html(source_ident)}</code>",
            parse_mode="HTML",
        )
    else:
        if db.remove_route(source_ident, dest_ident):
            await update.message.reply_text(
                f"✅ Unlinked <code>{_escape_html(source_ident)}</code> ➜ <code>{_escape_html(dest_ident)}</code>",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text("⚠️ Route not found.")


# ────────────────────────────────────────────────────────────
#  Replace Rules
# ────────────────────────────────────────────────────────────


async def add_replace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /add_replace OldWord [NewWord]")
        return
    old_word = context.args[0]
    new_word = " ".join(context.args[1:])
    db: Database = context.bot_data["db"]

    inserted = db.add_replace_rule(old_word, new_word)
    verb = "Added" if inserted else "Updated"
    await update.message.reply_text(
        f"✅ {verb} replacement:\n\n"
        f"Old: <code>{_escape_html(old_word)}</code>\n"
        f"New: <code>{_escape_html(new_word)}</code>",
        parse_mode="HTML",
    )


async def remove_replace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /remove_replace OldWord")
        return
    old_word = context.args[0]
    db: Database = context.bot_data["db"]
    if db.remove_replace_rule(old_word):
        await update.message.reply_text(
            f"✅ Removed rule for: <code>{_escape_html(old_word)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ Word not found in replacement list.")


async def list_replaces(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    rules = db.get_all_replace_rules()
    if not rules:
        await update.message.reply_text("📭 No replacement rules set.")
        return
    lines = ["✂️ <b>Replacement Rules:</b>\n"]
    for r in rules:
        nw = r["new_word"] if r["new_word"] else "(deleted)"
        lines.append(
            f"🔸 <code>{_escape_html(r['old_word'])}</code> ➜ <code>{_escape_html(nw)}</code>"
        )
    msg = "\n".join(lines)
    for i in range(0, len(msg), 4000):
        await update.message.reply_text(msg[i : i + 4000], parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  Block Rules
# ────────────────────────────────────────────────────────────


async def add_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /add_block BlockedWord")
        return
    word = context.args[0]
    db: Database = context.bot_data["db"]
    if db.add_block_rule(word):
        await update.message.reply_text(
            f"✅ <b>Blocked word added:</b>\n\n<code>{_escape_html(word)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ Word is already blocked.")


async def remove_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /remove_block BlockedWord")
        return
    word = context.args[0]
    db: Database = context.bot_data["db"]
    if db.remove_block_rule(word):
        await update.message.reply_text(
            f"✅ Removed block rule for: <code>{_escape_html(word)}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ Word not found in block list.")


async def list_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    rules = db.get_all_block_rules()
    if not rules:
        await update.message.reply_text("📭 No blocked words set.")
        return
    lines = ["🚫 <b>Blocked Words:</b>\n"]
    for r in rules:
        lines.append(f"🔸 <code>{_escape_html(r['word'])}</code>")
    msg = "\n".join(lines)
    for i in range(0, len(msg), 4000):
        await update.message.reply_text(msg[i : i + 4000], parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  Header / Footer
# ────────────────────────────────────────────────────────────


async def set_header(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /set_header <text...>")
        return
    text = " ".join(context.args)
    db: Database = context.bot_data["db"]
    db.set_header(text)
    await update.message.reply_text(
        f"✅ <b>Header set to:</b>\n\n{_escape_html(text)}", parse_mode="HTML"
    )


async def clear_header(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    db.clear_header()
    await update.message.reply_text("🗑️ Header cleared.")


async def set_footer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /set_footer <text...>")
        return
    text = " ".join(context.args)
    db: Database = context.bot_data["db"]
    db.set_footer(text)
    await update.message.reply_text(
        f"✅ <b>Footer set to:</b>\n\n{_escape_html(text)}", parse_mode="HTML"
    )


async def clear_footer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    db.clear_footer()
    await update.message.reply_text("🗑️ Footer cleared.")


# ────────────────────────────────────────────────────────────
#  Bot Control / Dashboards
# ────────────────────────────────────────────────────────────


async def set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /set_delay <seconds>")
        return
    try:
        delay = float(context.args[0])
        if delay < 0:
            raise ValueError
        db: Database = context.bot_data["db"]
        db.set_forward_delay(delay)
        await update.message.reply_text(
            f"⏱️ Forward delay set to <b>{delay}</b> seconds.", parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid positive number.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    stats = db.get_all_stats()

    status_emoji = "⏸️ PAUSED" if stats["paused"] else "▶️ RUNNING"
    header_preview = db.get_header() or "(None)"
    footer_preview = db.get_footer() or "(None)"
    default_dest = db.get_default_dest()
    dest_str = default_dest["identifier"] if default_dest else "(None)"

    msg = (
        f"🤖 <b>Bot Status: {status_emoji}</b>\n\n"
        f"📡 <b>Sources:</b> {stats['source_count']}\n"
        f"🎯 <b>Global Dest:</b> <code>{_escape_html(dest_str)}</code>\n"
        f"⏱️ <b>Delay:</b> {stats['forward_delay']}s\n\n"
        f"📌 <b>Header:</b> <code>{_escape_html(header_preview[:30])}</code>...\n"
        f"📌 <b>Footer:</b> <code>{_escape_html(footer_preview[:30])}</code>..."
    )

    keyboard = [
        [
            InlineKeyboardButton("▶️ Resume", callback_data="cmd_resume"),
            InlineKeyboardButton("⏸️ Pause", callback_data="cmd_pause"),
        ],
        [
            InlineKeyboardButton("📈 Stats", callback_data="cmd_stats"),
            InlineKeyboardButton("📋 Sources", callback_data="cmd_sources"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="HTML")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    db.set_paused(True)
    await update.message.reply_text(
        "⏸️ <b>Forwarding Paused</b>\nThe bot will ignore new posts until resumed.",
        parse_mode="HTML",
    )


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    db.set_paused(False)
    await update.message.reply_text(
        "▶️ <b>Forwarding Resumed</b>\nThe bot is now monitoring for new posts.",
        parse_mode="HTML",
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    db: Database = context.bot_data["db"]
    st = db.get_all_stats()
    recent = db.get_recent_history(limit=5)

    msg = (
        f"📈 <b>Lifetime Statistics</b>\n\n"
        f"✅ Total Forwarded: <b>{st['total_forwarded']}</b>\n"
        f"🚫 Total Skipped: <b>{st['total_skipped']}</b>\n\n"
        f"📝 <b>Recent Activity (Last 5):</b>\n"
    )

    if not recent:
        msg += "<i>No recent activity found.</i>"
    else:
        for r in recent:
            src = r["source"] or "Unknown"
            status_ico = "✅" if r["status"] == "forwarded" else "❌"
            msg += f"{status_ico} <code>{_escape_html(src)}</code> <i>({r['forwarded_at']})</i>\n"

    await update.message.reply_text(msg, parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  General Commands
# ────────────────────────────────────────────────────────────


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    welcome = (
        "👋 <b>Welcome to Auto-Forwarding Bot Admin!</b>\n\n"
        "To see the full Pro User Manual and learn how to use this bot, type <code>/help</code>.\n"
        "You can also use the blue <b>Menu</b> button ↙️ to see all commands at a glance."
    )
    await update.message.reply_text(welcome, parse_mode="HTML")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _admin_only(update):
        return
    # Now that we registered commands with Telegram, the built-in menu works.
    help_text = (
        "📘 <b>PRO USER MANUAL — Telegram Auto-Forwarding Bot</b>\n\n"
        "<i>Use this guide to master your bot's features. Note: The bot uses a 1-hour cross-channel duplicate filter automatically.</i>\n\n"
        "📡 <b>SOURCES & DESTINATIONS (SETUP)</b>\n"
        "▪️ <code>/add_source &lt;@username/ID&gt;</code> — Start monitoring a channel for posts\n"
        "▪️ <code>/remove_source &lt;@username/ID&gt;</code> — Stop monitoring a channel\n"
        "▪️ <code>/list_sources</code> — See all monitored channels and their routes\n"
        "▪️ <code>/add_dest &lt;@username/ID&gt;</code> — Register a destination channel/group/bot\n"
        "▪️ <code>/remove_dest &lt;@username/ID&gt;</code> — Remove a destination\n"
        "▪️ <code>/list_dests</code> — See all available destinations\n\n"
        "🎯 <b>ROUTING (WHERE POSTS GO)</b>\n"
        "▪️ <code>/set_dest &lt;@username/ID&gt;</code> — <b>(Recommended)</b> Set a GLOBAL destination where all posts go by default.\n"
        "▪️ <code>/show_dest</code> — See current global destination\n"
        "▪️ <code>/clear_dest</code> — Remove global destination\n"
        "▪️ <code>/link_source &lt;source&gt; &lt;dest&gt;</code> — <i>(Advanced)</i> Route a specific source to a specific destination (overrides global)\n"
        "▪️ <code>/unlink_source &lt;source&gt; &lt;dest&gt;</code> — Remove a specific route\n\n"
        "✍️ <b>CUSTOMIZATION (FILTERS & EDITS)</b>\n"
        "▪️ <code>/add_replace &lt;old&gt; &lt;new&gt;</code> — Auto-replace words (e.g., <i>/add_replace Amazon Flipkart</i>)\n"
        "▪️ <code>/remove_replace &lt;old&gt;</code> — Remove a replacement rule\n"
        "▪️ <code>/list_replaces</code> — See all replacement rules\n"
        "▪️ <code>/add_block &lt;word&gt;</code> — Completely skip posts containing this word\n"
        "▪️ <code>/remove_block &lt;word&gt;</code> — Remove a blocked word\n"
        "▪️ <code>/list_blocks</code> — See all blocked words\n"
        "▪️ <code>/set_header &lt;text&gt;</code> — Add text at the top of every post\n"
        "▪️ <code>/set_footer &lt;text&gt;</code> — Add text at the bottom of every post\n"
        "▪️ <code>/clear_header</code> & <code>/clear_footer</code> — Remove header/footer\n\n"
        "⚙️ <b>BOT CONTROLS & DASHBOARD</b>\n"
        "▪️ <code>/status</code> — Open the Interactive Admin Dashboard (Pause/Resume/Stats)\n"
        "▪️ <code>/stats</code> — View lifetime stats and recent forwarded/skipped history\n"
        "▪️ <code>/pause</code> / <code>/resume</code> — Manually stop/start forwarding\n"
        "▪️ <code>/set_delay &lt;seconds&gt;</code> — Add delay to avoid Telegram flood limits (Default: 3s)\n\n"
        "<i>💡 Tip: You can also tap the blue <b>Menu</b> button next to the chat box to see all commands!</i>"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")


# ────────────────────────────────────────────────────────────
#  Callback Query Handler (Inline Buttons)
# ────────────────────────────────────────────────────────────


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    # Protect buttons just in case
    if query.from_user.id != _get_admin_id():
        await query.answer("⛔ Access denied", show_alert=True)
        return

    await query.answer()
    data = query.data
    db: Database = context.bot_data["db"]
    msg_target = query.message  # Use callback's message, NOT update.message

    if data == "cmd_pause":
        db.set_paused(True)
        await msg_target.reply_text(
            "⏸️ <b>Forwarding Paused</b>\nThe bot will ignore new posts until resumed.",
            parse_mode="HTML",
        )
    elif data == "cmd_resume":
        db.set_paused(False)
        await msg_target.reply_text(
            "▶️ <b>Forwarding Resumed</b>\nThe bot is now monitoring for new posts.",
            parse_mode="HTML",
        )
    elif data == "cmd_stats":
        st = db.get_all_stats()
        recent = db.get_recent_history(limit=5)
        msg = (
            f"📈 <b>Lifetime Statistics</b>\n\n"
            f"✅ Total Forwarded: <b>{st['total_forwarded']}</b>\n"
            f"🚫 Total Skipped: <b>{st['total_skipped']}</b>\n\n"
            f"📝 <b>Recent Activity (Last 5):</b>\n"
        )
        if not recent:
            msg += "<i>No recent activity found.</i>"
        else:
            for r in recent:
                src = r["source"] or "Unknown"
                status_ico = "✅" if r["status"] == "forwarded" else "❌"
                msg += f"{status_ico} <code>{_escape_html(src)}</code> <i>({r['forwarded_at']})</i>\n"
        await msg_target.reply_text(msg, parse_mode="HTML")
    elif data == "cmd_sources":
        sources = db.get_all_sources()
        if not sources:
            await msg_target.reply_text("📭 No source channels are being monitored.")
        else:
            lines = ["📡 <b>Monitored Sources:</b>\n"]
            for src in sources:
                title = src["title"] if src["title"] else "Unknown"
                ident = src["identifier"]
                lines.append(f"🔸 <b>{_escape_html(title)}</b>")
                lines.append(f"   Identifier: <code>{_escape_html(ident)}</code>")
                if src["entity_type"] != "unknown":
                    lines.append(f"   Type: {src['entity_type']}")
                # Show routes for this source
                routes = db.get_routes_for_source(src["id"])
                if routes:
                    dest_names = [r["dest_identifier"] for r in routes]
                    lines.append(f"   Routes: {', '.join(dest_names)}")
                else:
                    lines.append("   Routes: <i>global default</i>")
                lines.append("")
            await msg_target.reply_text("\n".join(lines), parse_mode="HTML")

