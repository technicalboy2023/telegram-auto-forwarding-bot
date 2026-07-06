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
- [Local Setup](#-local-setup)
- [All Commands](#-all-commands)
- [Project Structure](#-project-structure)
- [How It Works](#-how-it-works)
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
