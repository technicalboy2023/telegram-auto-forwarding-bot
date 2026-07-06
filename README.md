# 🤖 Telegram Auto-Forwarding Bot

> **Dual-component bot**: Monitors Telegram channels, customizes posts, and auto-forwards to any destination bot — fully managed via Telegram commands.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Deploy](https://img.shields.io/badge/Deploy-Alwaysdata%20Free-brightgreen)](https://alwaysdata.com)

---

## 📋 Contents

- [What It Does](#-what-it-does)
- [Architecture](#-architecture)
- [Prerequisites](#-prerequisites)
- [Quick Setup (Alwaysdata)](#-quick-setup-alwaysdata)
- [🚀 Start Forwarding — Telegram Setup](#-start-forwarding--telegram-setup)
- [✂️ Customization Examples](#-customization-examples)
- [Local Setup](#-local-setup)
- [All Commands](#-all-commands)
- [Project Structure](#-project-structure)
- [How It Works](#-how-it-works)
- [🧹 24h Auto-Cleanup](#-24h-auto-cleanup)
- [Troubleshooting](#-troubleshooting)
- [Updating](#-updating)

---

## 🎯 What It Does

| # | Feature | Detail |
|---|---------|--------|
| 1 | **Monitor** | Watch unlimited source Telegram channels for new posts |
| 2 | **Customize** | Replace words, block posts, add header/footer |
| 3 | **Forward** | Send customized posts to any destination bot (CueLinks, etc.) |
| 4 | **Media** | Supports photos, videos, documents with captions |
| 5 | **Dedup** | Never forward the same post twice |
| 6 | **Control** | Manage everything via Telegram bot commands |
| 7 | **24/7** | Runs continuously, auto-restarts on crash |

---

## 🏗️ Architecture

```
┌──────────────────────────────┐
│  SOURCE CHANNELS             │
│  @Channel1  @Channel2  ...   │
└──────────┬───────────────────┘
           │ New Post
           ▼
┌──────────────────────────────┐
│  USERBOT (Telethon)          │
│  • Monitor channels          │
│  • Dedup check               │
└──────────┬───────────────────┘
           │ Raw Post
           ▼
┌──────────────────────────────┐
│  CUSTOMIZER                  │
│  1. Block check              │
│  2. Word replace             │
│  3. Add header               │
│  4. Add footer               │
└──────────┬───────────────────┘
           │ Customized Post
           ▼
┌──────────────────────────────┐
│  DESTINATION BOT             │
│  @CueLinksBot / @AnyBot      │
└──────────────────────────────┘

┌──────────────────────────────┐
│  CONTROL BOT (PTB)           │
│  Admin panel via /commands   │◄── You (Admin)
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  SQLite Database             │
│  Sources, Rules, Stats, Logs │
└──────────────────────────────┘
```

Two components run in a single `asyncio` event loop:
- **Userbot** (Telethon MTProto) → Your personal account, monitors + forwards
- **Control Bot** (python-telegram-bot) → Bot token from @BotFather, admin commands

---

## 🔐 Prerequisites

### Before Setup, You Need:

| # | Item | How to Get |
|---|------|------------|
| 1 | **API ID + API Hash** | [my.telegram.org](https://my.telegram.org) → Login → API Development Tools |
| 2 | **Bot Token** | Telegram: `@BotFather` → `/newbot` → Copy token |
| 3 | **Your Telegram ID** | Telegram: `@userinfobot` → `/start` → Copy numeric ID |
| 4 | **Python 3.10+** | `python3 --version` |
| 5 | **Source Channels** | Join the channels you want to monitor (from your personal account) |
| 6 | **Destination Bot** | `@CueLinksBot` or any bot — start it and configure auto-posting if needed |

---

## 🚀 Quick Setup (Alwaysdata 24/7 — FREE)

> **No credit card needed!** Alwaysdata gives free 256MB/1GB hosting — this bot is optimized for it.

### Step 1: Sign Up (FREE)

Go to: https://www.alwaysdata.com/en/register/?p=2012

→ Email + Password → **No credit card!**

### Step 2: SSH Into Server

```bash
ssh YOUR_USERNAME@ssh-YOUR_USERNAME.alwaysdata.net
# Enter the password you set at signup
```

### Step 3: Clone & Setup

```bash
# Clone repo
cd ~/www
git clone https://github.com/technicalboy2023/telegram-auto-forwarding-bot.git bot
cd ~/www/bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (1-2 minutes)
pip install --upgrade pip
pip install telethon python-telegram-bot
```

### Step 4: Create config.json

```bash
nano ~/www/bot/config.json
```

Paste this with YOUR real values:

```json
{
  "api_id": 12345678,
  "api_hash": "your_api_hash_here",
  "phone": "+91XXXXXXXXXX",
  "bot_token": "your_bot_token_here",
  "admin_id": 123456789
}
```

> `Ctrl+O` → Enter (save) → `Ctrl+X` (exit)

### Step 5: First Run (Phone OTP)

```bash
cd ~/www/bot
source venv/bin/activate
python3 bot.py
```

1. Phone number confirm hoga
2. **Telegram se OTP aayega apke phone pe**
3. OTP enter karo
4. `Logged in successfully` dikhega
5. **Ctrl+C** se stop karo

> ✅ Session file save ho jayegi — agli baar direct login hoga!

### Step 6: Create 24/7 Service

1. Browser: https://admin.alwaysdata.com/ → Login
2. Left menu → **Advanced** → **Services**
3. **Add a service**:

| Field | Value |
|-------|-------|
| **SSH user** | `amna` (your Alwaysdata username) |
| **Command** | `/home/amna/www/bot/venv/bin/python3 /home/amna/www/bot/bot.py` |
| **Monitoring command** | `/bin/true` |
| **Environment** | `LOW_RAM=true` |
| **Working directory** | `www/bot` |
| **Paused** | Unchecked |

> ⚠️ **Important**: 
> - Replace `amna` with YOUR username!
> - Working directory: just `www/bot` (NOT full path — Alwaysdata auto-prepends /home/user/)
> - Monitoring command `/bin/true` is REQUIRED — without it, Alwaysdata kills the bot after 4 seconds!

4. **Submit** → **▶️ Start**

### Step 7: Verify

```bash
# Check logs
cat ~/www/bot/logs/bot.log | tail -10

# Or via Telegram
# Open your control bot → /status
```

---

## 🚀 Start Forwarding — Telegram Setup

> **After deploying**, open your Control Bot in Telegram and run these commands to configure forwarding.

### Step 1: Add Source Channels

```
/add_source @DealsChannel
/add_source @OffersChannel
/add_source @TechNews
```

Add as many channels as you want. Your user account must be a **member** of each channel.

| Command | Example |
|---------|---------|
| `/add_source @channel` | `/add_source @DealsChannel` |
| `/remove_source @channel` | `/remove_source @DealsChannel` |
| `/list_sources` | Shows all channels |

### Step 2: Set Destination Bot

```
/set_dest @CueLinksBot
```

This is where all forwarded posts will go. Any bot works — CueLinks, your own bot, etc.

| Command | Example |
|---------|---------|
| `/set_dest @bot` | `/set_dest @CueLinksBot` |
| `/show_dest` | Shows current destination |

### Step 3: Customize Posts (Optional)

**Replace words/channel names:**
```
/add_replace @OldChannel➜@MyChannel
/add_replace Amazon➜MyStore
```

**Block unwanted posts:**
```
/add_block Join @Competitor
/add_block SpamWord
```

**Add header/footer to every post:**
```
/set_header 📢 Best Deals by @MyChannel
/set_footer 🔔 Join @MyChannel for more!
```

### Step 4: Set Forward Delay

```
/set_delay 3
```

Default is 3 seconds. Increase to 5-10 if you have many source channels to avoid Telegram rate limits.

### Step 5: Verify Everything

```
/status
```

Output should look like:
```
🤖 Bot Status: ▶️ RUNNING
📡 Sources: 3
🎯 Destination: @CueLinksBot
⏱️ Forward Delay: 3.0s
✅ Forwarded: 0
⛔ Skipped: 0
```

### Step 6: Watch It Work

That's it! The bot will now:
1. Monitor all source channels for new posts
2. Apply your customization rules (replace, block, header/footer)
3. Forward to your destination bot automatically

Check stats anytime:
```
/stats
```

### 🎯 Complete Example Flow

```
# 1. Add sources (one by one)
/add_source @FlipkartDeals
/add_source @AmazonOffers
/add_source @TechDealsIndia

# 2. Set destination
/set_dest @CueLinksBot

# 3. Customize
/add_replace @FlipkartDeals➜@MyStore
/add_replace @AmazonOffers➜@MyStore
/add_block Join @Competitor
/set_header 📢 Today's Best Deals 🛍️
/set_footer 🔔 For more deals, join @MyStore

# 4. Set delay
/set_delay 4

# 5. Check
/status

# 6. Start!
/pause   (if paused)
/resume  (to start forwarding)
```

**That's it! Now whenever @FlipkartDeals or @AmazonOffers post something, your bot will customize it and forward to @CueLinksBot!** 🎉

---

## ✂️ Customization Examples

> **The customization commands are the most powerful feature** — they let you transform raw source posts into your branded, monetizable content. Below is a real-world walkthrough with everything you need.

### Example Source Post (Raw)

```
Nilkamal 4 Tier Engineered WoodBook Shelf Cabinet @₹4250.

https://www.amazon.in/dp/B0F3CVFBQ2?th=1&tag=indamz01-21

@b-tricks join
```

Notice the issues with this raw post:
- `@₹4250` — `@` typo before rupee sign
- `WoodBook` — typo, should be `Wood Book`
- `indamz01-21` — source's affiliate tag (replace with YOURS to earn commission)
- `@b-tricks join` — source channel's CTA (replace with YOUR channel)

### Step-by-Step Transformation

| # | Telegram Command | Effect |
|---|------------------|--------|
| 1 | `/add_replace @₹→₹` | `@₹4250` → `₹4250` |
| 2 | `/add_replace 4250→4,250` | `₹4250` → `₹4,250` (Indian-style comma) |
| 3 | `/add_replace WoodBook→Wood Book` | Fix typo |
| 4 | `/add_replace indamz01-21 → yourtag-21` | Replace affiliate tag (earn YOUR commission!) |
| 5 | `/add_replace @b-tricks→@YourDealsChannel` | Replace source CTA with your channel |
| 6 | `/add_block Sponsored` | Skip posts containing "Sponsored" |
| 7 | `/add_block #ad` | Skip `#ad` tagged posts |
| 8 | `/add_block giveaway` | Skip giveaway posts |
| 9 | `/set_header 🔥 BEST DEALS TODAY 🔥` | Prepend to every post |
| 10 | `/set_footer 👉 Join @YourDealsChannel!` | Append to every post |

### Final Customized Post

After all rules are applied, this is what your destination bot receives:

```
🔥 BEST DEALS TODAY 🔥

Nilkamal 4 Tier Engineered Wood Book Shelf Cabinet ₹4,250.

https://www.amazon.in/dp/B0F3CVFBQ2?th=1&tag=yourtag-21

@YourDealsChannel join

👉 Join @YourDealsChannel!
```

### Post Processing Pipeline

When a new post arrives from any source channel, bot does this in order:

```
1. BLOCK CHECK  ─── matched? → SKIP ❌ (counted as Skipped in /stats)
2. WORD REPLACE ─── replace all matching words (literal text replacement)
3. ADD HEADER  ─── prepend header text (line 1)
4. ADD FOOTER  ─── append footer text (last line)
5. FORWARD ✅    ─── to destination bot (@CueLinksBot or whatever you set)
```

### Pro Tips

- **Both formats work**: `/add_replace @₹→₹` (with arrow) OR `/add_replace @₹ ₹` (space-separated)
- **Case matters for replacement**: `@₹` will NOT match `@₹` if you typed them differently — make rules for each variant
- **Affiliate tag = monetization**: Always replace source's `?tag=indamz01-21` with your own tag to earn commission
- **Common starting replaces**: `@₹→₹`, `@Rs.→Rs.`, common typos, original affiliate tag → your tag
- **Block rules are case-insensitive**: `Sponsored`, `SPONSORED`, and `sponsored` all match
- **Header/Footer stay short** (1-2 lines) — Telegram charges lines against message length

### Recommended Setup For Deal Channels

```
/add_replace @₹→₹
/add_replace indamz01-21 → yourtag-21
/add_replace @b-tricks→@YourDealsChannel
/add_replace WoodBook→Wood Book

/add_block Sponsored
/add_block #ad
/add_block giveaway

/set_header 🔥 DEAL ALERT 🔥
/set_footer 👉 Join @YourDealsChannel for daily loot!

/list_replaces
/list_blocks
/status
```

---

## 💻 Local Setup

```bash
# Clone
git clone https://github.com/technicalboy2023/telegram-auto-forwarding-bot.git
cd telegram-auto-forwarding-bot

# Install
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create config.json (see Step 4 above)
nano config.json

# Run
python3 bot.py
```

---

## 🎮 All Commands

### Source Management

| Command | What It Does |
|---------|-------------|
| `/add_source @channel` | Add source channel to monitor |
| `/remove_source @channel` | Stop monitoring a channel |
| `/list_sources` | Show all monitored channels |

### Destination

| Command | What It Does |
|---------|-------------|
| `/set_dest @BotUsername` | Set where posts get forwarded |
| `/show_dest` | Show current destination bot |

### Word Replacement

| Command | What It Does |
|---------|-------------|
| `/add_replace OldWord➜NewWord` | Replace word/phrase in posts |
| `/remove_replace OldWord` | Remove a replacement rule |
| `/list_replaces` | Show all replacement rules |

### Word Blocking

| Command | What It Does |
|---------|-------------|
| `/add_block BadWord` | Skip posts containing this word |
| `/remove_block BadWord` | Remove a block rule |
| `/list_blocks` | Show all blocked words |

### Header / Footer

| Command | What It Does |
|---------|-------------|
| `/set_header Text` | Add text at TOP of every post |
| `/set_footer Text` | Add text at BOTTOM of every post |
| `/clear_header` | Remove header |
| `/clear_footer` | Remove footer |

### Control

| Command | What It Does |
|---------|-------------|
| `/status` | Bot status, sources, forwarded count |
| `/pause` | Temporarily stop forwarding |
| `/resume` | Resume forwarding |
| `/stats` | Statistics + recent activity |
| `/set_delay 5` | Set delay between forwards (seconds) |

---

## 📂 Project Structure

```
telegram-auto-forwarding-bot/
│
├── bot.py                    # 🔥 Main entry — runs both components
├── config.json               # ⚙️ Your credentials (NOT in git)
│
├── userbot/
│   ├── __init__.py
│   ├── engine.py             # 📡 Telethon userbot — monitor & forward
│   └── customizer.py         # ✂️ Post customization pipeline
│
├── controlbot/
│   ├── __init__.py
│   ├── bot.py                # 🤖 Control bot setup (PTB)
│   └── handlers.py           # 📋 All 21 command handlers
│
├── database/
│   ├── __init__.py
│   └── db.py                 # 💾 SQLite — 6 tables, thread-safe
│
├── utils/
│   ├── __init__.py
│   └── logger.py             # 📊 Rotating file + console logger
│
├── requirements.txt          # 📦 Dependencies
├── .gitignore                # 🙈 Excludes sensitive files
├── .env.example              # 📋 Environment template
├── README.md                 # 📖 You're reading it!
├── setup_guide.md            # 📚 Hindi + English detailed guide
├── ALL_IN_ONE.sh             # 🔧 Server fix & diagnostic tool
└── SETUP_COMMANDS.txt        # 📋 Quick reference commands
```

---

## ⚙️ How It Works

### Post Processing Pipeline

```
Raw Post
  │
  ├─ 1. BLOCK CHECK ────── Blocked word found? → SKIP ❌
  │
  ├─ 2. WORD REPLACE ──── Replace all matching words (case-insensitive)
  │
  ├─ 3. ADD HEADER ────── Prepend header text
  │
  ├─ 4. ADD FOOTER ────── Append footer text
  │
  └─ 5. CLEANUP ───────── Trim extra blank lines → FORWARD ✅
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `source_channels` | Monitored channels (username, channel_id) |
| `destination` | Current destination bot |
| `replace_rules` | Word → replacement mappings |
| `block_rules` | Words that cause post rejection |
| `settings` | Header, footer, pause, delay, stats |
| `forward_history` | SHA256 dedup log + forward history |

### 256MB RAM Optimizations

For free Alwaysdata hosting, the bot includes:

| Optimization | Detail |
|-------------|--------|
| `LOW_RAM=true` | Reduces logging to WARNING level |
| `gc.collect()` | Garbage collection every 5 forwards |
| Entity cache clear | Telethon's cache cleared periodically |
| `catch_up=False` | Skips replay of missed messages |
| Auto-restart | Exits cleanly every 6h → service manager restarts |
| Config reload | 120s interval (vs 30s) to reduce DB load |

---

## 🧹 24h Auto-Cleanup

The bot self-cleans on a 24-hour schedule to keep disk usage low and
prevent unbounded growth of history tables. Cleanup runs **automatically**
— no action required from you.

### What Gets Cleaned Every 24h

| Target | Action | Default Retention |
|--------|--------|-------------------|
| `forward_history` rows older than 30 days | DELETE + VACUUM | `HISTORY_RETENTION_DAYS=30` |
| `__pycache__/` directories | Remove with `shutil.rmtree` | Always |
| Stray `*.pyc` files | Remove with `os.unlink` | Always |
| Orphaned log files in `logs/` | Remove if older than 7 days | `LOG_RETENTION_DAYS=7` |
| Temp files (*.tmp, *~, .DS_Store, *.bak, *.swp) | Remove from project | Always |

Each cleanup stage runs in a separate try/except block, so a single failure
won't stop the others — errors are logged per-stage and one bad stage
does NOT abort the rest.

### Safety Guarantees

A hard-coded exclusion list **prohibits deletion of**:

- `bot_data.db` and SQLite WAL/SHM files
- `userbot_session.session` and Telethon session journal
- `config.json`, `.env`, `.env.example`
- The active `bot.log` and its `RotatingFileHandler` backups
- `venv/`, `.venv/`, `.git/`, `site-packages/` directories

Even if a cleanup pass runs concurrently with bot operation, none of these
critical files can ever be deleted by accident. Each path is checked
against `PROTECTED_FILE_NAMES` / `PROTECTED_DIR_NAMES` before deletion.

### How Often It Actually Runs

The bot has built-in `RESTART_HOURS = 6` auto-restart (every 6 hours, to
clear memory leaks). On every restart, **synchronous startup cleanup runs
BEFORE the asyncio loop starts** — so you get cleanup runs:

- **Every 6 hours** (via auto-restart + startup cleanup), OR
- **Every 24 hours** (via the asyncio-scheduled task if `NO_RESTART=1`)

Either way: at least once per day. Backup of safety.

### Verify Cleanup Is Working

SSH into your server and run:

```bash
cd ~/www/bot
grep -E "(Startup cleanup|Auto-cleanup)" logs/bot.log | tail -20
```

You should see lines like:

```
INFO  telegram_bot  Startup cleanup: pycache=2d/0f
INFO  telegram_bot  Auto-cleanup: history=8, vacuumed, pycache=3d/2f
INFO  telegram_bot  Auto-cleanup: (nothing to clean)
```

If a line contains `errors=[...]`, paste it back to the developer — the
bot logs error details per-stage and continues with other stages.

### Force an Immediate Cleanup

```bash
cd ~/www/bot
source venv/bin/activate
python3 -c "from utils.cleanup import CleanupScheduler; from database.db import Database; db=Database(); r=CleanupScheduler(db).run_full_cleanup(); print(r.summary()); print('errors:', r.errors)"
```

Output:

```
pycache=2d/0f
errors: []
```

### Configuration (Env Vars — Optional)

Set these on your Alwaysdata Service's Environment field
(Admin Panel → Services → Edit → Environment, one per line):

| Variable | Default | Purpose |
|----------|---------|---------|
| `HISTORY_RETENTION_DAYS` | `30` | How long to keep forward history |
| `LOG_RETENTION_DAYS` | `7` | How long to keep orphan log files |
| `CLEANUP_INTERVAL_HOURS` | `24` | Interval between scheduled cleanups |
| `NO_CLEANUP` | (unset) | Set `=1` to disable all cleanup |
| `LOW_RAM` | `true` | Already set — controls log verbosity |

Save the service → Restart. New values take effect on next startup.

---

## 🔄 Updating

When you make code changes and push to GitHub:

```bash
# On Alwaysdata server
cd ~/www/bot
git pull origin main

# Then restart the service:
# Admin Panel → Services → telegram-forwarder → Restart
```

Or via SSH:
```bash
# Find and kill the process (Alwaysdata will auto-restart it)
pkill -9 -f "bot.py"
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| **Bot not forwarding** | Check `/status` — source + destination set? `/pause` off? |
| **Service dies after 4 sec** | Monitoring command must be `/bin/true` in Service settings |
| **Session expired** | Delete `userbot_session.session` and re-run `python3 bot.py` |
| **OOM killed (256MB)** | Reduce number of source channels, increase delay via `/set_delay 5` |
| **Control bot ignoring me** | Check `admin_id` in config.json matches YOUR Telegram ID |
| **Source posts not detected** | Your account must be a MEMBER of the source channel |
| **FloodWaitError** | Auto-handled — bot waits then retries |
| **2FA enabled** | Bot will ask for password on first login |
| **"/home/user/www/bot doesnt exist"** | Working directory should be `www/bot` not full path |
| **Conflict: terminated by other getUpdates** | Two bot instances running — kill one with `pkill -9 -f bot.py` |

### Check Logs

```bash
# Real-time
tail -f ~/www/bot/logs/bot.log

# Last 50 lines
tail -50 ~/www/bot/logs/bot.log

# Errors only
grep -i error ~/www/bot/logs/bot.log
```

---

## 🛡️ Security Notes

- `config.json` is **not committed** to git (in `.gitignore`)
- Session file is **not committed** to git
- Database (`bot_data.db`) is **not committed** to git
- Only your `admin_id` can use the Control Bot
- Alwaysdata SSH uses password or key auth

---

## 🌐 Free Hosting Options

| Option | Card Needed? | 24/7? | RAM |
|--------|-------------|-------|-----|
| **Alwaysdata** ✅ | ❌ No | ✅ Yes | 256MB |
| Termux (Android) | ❌ No | ✅ Yes | Phone RAM |
| Personal PC | ❌ No | ✅ Yes | PC RAM |
| Oracle Cloud | ⚠️ Yes | ✅ Yes | 24GB |

---

## 📄 License

MIT — use it, modify it, share it. Attribution appreciated!

---

**Made with ❤️ | Hindi + English Support | Alwaysdata 24/7 Ready**
