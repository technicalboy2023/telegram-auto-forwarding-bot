# Telegram Auto-Forwarding Bot — Setup Guide / सेटअप गाइड

## 📋 Prerequisites / जरूरी चीज़ें

| # | Step / स्टेप | How / कैसे करें |
|---|-------------|-----------------|
| 1 | **Telegram API Credentials** | Visit [my.telegram.org](https://my.telegram.org) → Login → API Development Tools → Create application → Get `API ID` + `API Hash` |
| 2 | **Control Bot बनाओ** | Telegram पर `@BotFather` को `/newbot` भेजो → Bot name + username डालो → Bot Token कॉपी करो |
| 3 | **अपनी Telegram ID लो** | `@userinfobot` को message करो → अपनी numeric ID कॉपी करो |
| 4 | **Source Channels join करो** | जिन channels से posts लेनी हैं, उनमें member बनो (user account से) |
| 5 | **Python 3.10+** install करो | `python3 --version` से check करो |
| 6 | **Destination Bot सेटअप (Optional)** | CueLinks या कोई भी bot — `/start` करो और ready रखो |

---

## 🔧 Installation / इंस्टॉलेशन

### Step 1: Clone / Download Project

```bash
cd telegram-autoforwarding
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```
या:
```bash
pip3 install -r requirements.txt
```

### Step 3: Configure `config.json`

`config.json` file में अपनी credentials भरो:

```json
{
  "api_id": "YOUR_API_ID",
  "api_hash": "YOUR_API_HASH",
  "phone": "+91XXXXXXXXXX",
  "bot_token": "YOUR_CONTROL_BOT_TOKEN",
  "admin_id": 123456789
}
```

| Field | Value / मान |
|-------|-------------|
| `api_id` | my.telegram.org से मिला API ID |
| `api_hash` | my.telegram.org से मिला API Hash |
| `phone` | आपका phone number (international format: +91...) |
| `bot_token` | @BotFather से मिला bot token |
| `admin_id` | @userinfobot से मिली आपकी numeric Telegram ID |

> ⚠️ **सिर्फ ये 5 fields manually fill करने हैं**, बाकी सब bot commands से manage होगा।

### Step 4: First Run

```bash
python bot.py
```

पहली बार run करने पर:
- Userbot (Telethon) आपके phone पर OTP/code भेजेगा — वो डालना होगा
- Session file (`userbot_session.session`) create होगी
- Database (`bot_data.db`) automatically create होगी
- अगली बार से direct login हो जाएगा

### Step 5: Setup via Control Bot

अपने Control Bot को Telegram पर open करो और ये commands भेजो:

```
/add_source @DealsChannel
/set_dest @CueLinksBot
/status
```

---

## 🎮 Commands / कमांड्स

### Source Management / सोर्स मैनेजमेंट

| Command | काम |
|---------|-----|
| `/add_source @channel` | Source channel add करो |
| `/remove_source @channel` | Source channel हटाओ |
| `/list_sources` | सभी source channels देखो |

### Destination / डेस्टिनेशन

| Command | काम |
|---------|-----|
| `/set_dest @BotUsername` | Destination bot set करो |
| `/show_dest` | Current destination देखो |

### Customization / कस्टमाइज़ेशन

| Command | काम |
|---------|-----|
| `/add_replace OldWord➜NewWord` | Word replacement add करो |
| `/remove_replace OldWord` | Replacement rule हटाओ |
| `/list_replaces` | सभी replacement rules देखो |
| `/add_block BadWord` | Blocked word add करो |
| `/remove_block BadWord` | Block rule हटाओ |
| `/list_blocks` | सभी blocked words देखो |
| `/set_header Text` | हर post के ऊपर text add करो |
| `/set_footer Text` | हर post के नीचे text add करो |
| `/clear_header` | Header हटाओ |
| `/clear_footer` | Footer हटाओ |

### Control / कंट्रोल

| Command | काम |
|---------|-----|
| `/status` | Bot status, source count, forwarded count |
| `/pause` | Forwarding temporarily pause |
| `/resume` | Forwarding resume |
| `/stats` | Statistics — forwarded & skipped counts |
| `/set_delay 5` | Set delay between forwards (seconds, minimum 1) |

---

## 🖥️ 24/7 Deployment (systemd)

### Step 1: Edit the service file

```bash
nano deploy/telegram-bot.service
```

`USER` को अपने Linux username से replace करो (2 जगहों पर)।

### Step 2: Install service

```bash
sudo cp deploy/telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

### Step 3: Check status

```bash
sudo systemctl status telegram-bot
journalctl -u telegram-bot -f
```

---

## 📂 File Structure / फाइल स्ट्रक्चर

```
telegram-autoforwarding/
├── config.json                    # Base config (API keys, admin ID)
├── bot.py                         # Main entry — runs both components
├── userbot/
│   ├── __init__.py
│   ├── engine.py                  # Telethon userbot — monitor & forward
│   └── customizer.py              # Post customization engine
├── controlbot/
│   ├── __init__.py
│   ├── bot.py                     # Control panel bot setup
│   └── handlers.py                # All command handlers
├── database/
│   ├── __init__.py
│   └── db.py                      # SQLite — sources, rules, stats, history
├── utils/
│   ├── __init__.py
│   └── logger.py                  # Logging setup
├── requirements.txt               # Dependencies
├── .env.example                   # Environment variables template
├── setup_guide.md                 # This guide
└── deploy/
    └── telegram-bot.service       # systemd service file
```

---

## ⚠️ Important Notes / जरूरी नोट्स

1. **Account Ban Risk:** Userbot personal account use करता है। बहुत तेज़ forward करने से Telegram account ban हो सकता है। Default 3-second delay है।
2. **Secondary Phone Recommended:** Main account के बजाय secondary number use करो।
3. **CueLinks Auto-Posting:** अगर CueLinks use कर रहे हो, तो CueLinks bot का auto-posting feature ON होना चाहिए।
4. **Source Channel Membership:** तुम्हारा user account source channels का member होना चाहिए, नहीं तो posts नहीं दिखेंगी।
5. **2FA (Two-Factor Auth):** अगर तुम्हारे account पर 2FA है, तो पहली बार login पर password भी पूछेगा।

---

## 🐛 Troubleshooting / समस्या निवारण

| Problem | Solution |
|---------|----------|
| `FloodWaitError` | Telegram rate limit — auto-handled, wait करेगा |
| `ChatWriteForbiddenError` | Destination bot ने block किया या restricted |
| Session expired | `userbot_session.session` delete करो और re-run करो |
| Control bot ignore कर रहा | Check `admin_id` in config.json — सही numeric ID होनी चाहिए |
| Source channel posts नहीं आ रही | Check करो कि source channel का member हो और username सही है |

---

## 🔗 Useful Links / उपयोगी लिंक

- [Telegram API (my.telegram.org)](https://my.telegram.org)
- [@BotFather](https://t.me/BotFather)
- [@userinfobot](https://t.me/userinfobot)
- [Telethon Documentation](https://docs.telethon.dev/)
- [python-telegram-bot Documentation](https://docs.python-telegram-bot.org/)
