#!/bin/bash
# ======================================================================
# ALL-IN-ONE FIX SCRIPT — Telegram Auto-Forwarding Bot
# Run this ON the Alwaysdata server: bash ALL_IN_ONE.sh
# ======================================================================

set -e
echo "================================================="
echo " 🔧 ALL-IN-ONE FIX — Starting..."
echo "================================================="

# ── Step 1: Kill any running bot processes ──
echo ""
echo "📛 STEP 1: Killing old bot processes..."
pkill -f "bot.py" 2>/dev/null && echo "  Killed old bot.py processes" || echo "  No running bot found"
sleep 1

# ── Step 2: Pull latest code from GitHub ──
echo ""
echo "📥 STEP 2: Pulling latest code..."
cd ~/www/bot
git stash 2>/dev/null || true
git pull origin main
echo "  Code updated!"

# ── Step 3: Update dependencies ──
echo ""
echo "📦 STEP 3: Checking dependencies..."
source venv/bin/activate
pip install --upgrade telethon python-telegram-bot --quiet 2>&1 | tail -1
echo "  Dependencies OK"

# ── Step 4: Verify all files ──
echo ""
echo "🔍 STEP 4: Verifying files..."

echo -n "  config.json: "
if [ -f config.json ]; then
    python3 -c "
import json
c=json.load(open('config.json'))
for k in ['api_id','api_hash','phone','bot_token','admin_id']:
    v=c.get(k,'')
    if str(v) in ('YOUR_API_ID','YOUR_API_HASH','YOUR_CONTROL_BOT_TOKEN','123456789'):
        print('BAD - has placeholder values! FIX IT!')
        exit(1)
print('OK')
" || { echo "  ❌ Fix config.json first!"; exit 1; }
else
    echo "  ❌ config.json MISSING! Create it first."
    exit 1
fi

echo -n "  session file: "
if [ -f userbot_session.session ]; then
    echo "OK"
else
    echo "NOT FOUND (will create on first run)"
fi

echo -n "  Python version: "
python3 --version

# ── Step 5: Quick manual test ──
echo ""
echo "🧪 STEP 5: Testing bot (5 second test)..."
timeout 8 python3 bot.py 2>&1 | head -10 &
TEST_PID=$!
sleep 5
if kill -0 $TEST_PID 2>/dev/null; then
    echo "  ✅ Bot starts OK!"
    kill $TEST_PID 2>/dev/null
else
    echo "  ⚠️  Bot exited quickly - check logs:"
    cat logs/bot.log 2>/dev/null | tail -5
fi
sleep 2

# ── Step 6: Fix log directory permissions ──
echo ""
echo "📁 STEP 6: Fixing permissions..."
mkdir -p ~/www/bot/logs
chmod 755 ~/www/bot/logs
echo "  Logs directory ready"

# ── Step 7: Summary ──
echo ""
echo "================================================="
echo " ✅ ALL-IN-ONE FIX COMPLETE!"
echo "================================================="
echo ""
echo " 📊 Quick diagnostic:"
echo "    Bot log: $(cat logs/bot.log 2>/dev/null | wc -l) lines"
echo "    DB size: $(ls -lh bot_data.db 2>/dev/null | awk '{print $5}')"
echo "    Session: $(ls -lh userbot_session.session 2>/dev/null | awk '{print $5}')"
echo ""
echo " 🔧 NOW DO THIS — Service Setup:"
echo "================================================="
echo ""
echo " 1. Go to: https://admin.alwaysdata.com/"
echo " 2. Services → telegram-forwarder → Edit (pencil icon)"
echo ""
echo " 3. Fill these EXACT values:"
echo "    ┌──────────────────────────────────────────────┐"
echo "    │ SSH user:            amna                    │"
echo "    │ Command:             $HOME/www/bot/venv/bin/python3 $HOME/www/bot/bot.py"
echo "    │ Monitoring command:  /bin/true               │"
echo "    │ Environment:         LOW_RAM=true            │"
echo "    │ Working directory:   www/bot                 │"
echo "    │ Paused:              UNCHECKED               │"
echo "    └──────────────────────────────────────────────┘"
echo ""
echo " 4. Save → Start (▶️)"
echo ""
echo " 5. Check status: cat ~/www/bot/logs/bot.log | tail -10"
echo ""
echo " 6. Telegram: send /start to your control bot"
echo "================================================="
