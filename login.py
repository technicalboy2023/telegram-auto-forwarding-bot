#!/usr/bin/env python3
"""
Interactive Login Script for Telethon Userbot.

Run this script in a terminal (locally or via SSH) to authenticate
your Telegram account and generate the `userbot_session.session` file.

Once generated, the main `bot.py` will use this session file
to run silently in the background on your VPS (Alwaysdata).
"""

import json
import sys
from pathlib import Path
from telethon.sync import TelegramClient
from telethon.errors import SessionPasswordNeededError

CONFIG_PATH = Path(__file__).parent / "config.json"
SESSION_PATH = Path(__file__).parent / "userbot_session"

def main():
    if not CONFIG_PATH.exists():
        print("❌ config.json not found! Please create it from config.example.json first.")
        sys.exit(1)

    with open(CONFIG_PATH, "r") as f:
        cfg = json.load(f)

    api_id = cfg.get("api_id")
    api_hash = cfg.get("api_hash")
    phone = cfg.get("phone")

    if not api_id or not api_hash or str(api_id) == "YOUR_API_ID":
        print("❌ Invalid API ID / Hash in config.json. Please update them.")
        sys.exit(1)
        
    if not phone or phone == "+1234567890":
        phone = input("📱 Enter your phone number (with country code, e.g., +91...): ").strip()

    print("\n🚀 Starting Telegram Login Process...")
    print(f"Session will be saved as: {SESSION_PATH}.session\n")

    client = TelegramClient(
        str(SESSION_PATH),
        api_id,
        api_hash,
        device_model="AutoForwarder",
        system_version="1.0",
        app_version="2.0"
    )

    client.connect()

    if not client.is_user_authorized():
        print("📲 Sending OTP code to your Telegram app...")
        client.send_code_request(phone)
        
        # Telegram often blocks messages containing just the code,
        # but since this is local terminal input, it's fine.
        code = input("💬 Enter the code you received on Telegram: ").strip()
        
        try:
            client.sign_in(phone, code)
        except SessionPasswordNeededError:
            print("\n🔒 Two-Step Verification (2FA) is enabled on your account.")
            password = input("🔑 Enter your 2FA password: ").strip()
            client.sign_in(password=password)
            
    print("\n✅ Login Successful!")
    print("The 'userbot_session.session' file has been generated/updated.")
    print("You can now safely run 'python3 bot.py' on your server.\n")
    
    # Just to verify who we logged in as
    me = client.get_me()
    print(f"👤 Logged in as: {me.first_name} (ID: {me.id})")
    
    client.disconnect()

if __name__ == "__main__":
    main()
