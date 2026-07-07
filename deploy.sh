#!/bin/bash
# Telegram Auto-Forwarding Bot — Deploy Script
# Run this on your Alwaysdata server via SSH
# Usage: bash deploy.sh

set -e

echo "=== Pulling latest code from GitHub ==="
cd ~/www/bot
git pull origin main

echo ""
echo "=== Killing old bot process ==="
pkill -9 -f bot.py || echo "(No old process found — OK)"

echo ""
echo "=== Waiting 2 seconds for port cleanup ==="
sleep 2

echo ""
echo "=== Starting bot in background ==="
nohup python3 bot.py > bot_output.log 2>&1 &

echo ""
echo "=== Checking if bot started ==="
sleep 3
if pgrep -f "python3 bot.py" > /dev/null; then
    echo "✅ Bot is running! PID: $(pgrep -f 'python3 bot.py')"
    echo ""
    echo "📋 View live logs:  tail -f ~/www/bot/logs/bot.log"
    echo "📋 Check output:    tail -f ~/www/bot/bot_output.log"
    echo "🛑 Stop bot:        pkill -9 -f bot.py"
else
    echo "❌ Bot failed to start. Check logs:"
    echo "   cat ~/www/bot/bot_output.log"
    echo "   cat ~/www/bot/logs/bot.log"
fi
