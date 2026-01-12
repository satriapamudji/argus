#!/usr/bin/env python3
"""Direct test of Telegram publish with detailed error output."""

import os
from pathlib import Path
from dotenv import load_dotenv
import httpx

load_dotenv()

# Read the escaped message
content = Path("test_message_escaped.txt").read_text(encoding="utf-8")

# Get config from env
token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

print(f"Token (first 10 chars): {token[:10] if token else 'NOT SET'}...")
print(f"Chat ID: {chat_id}")
print(f"Content length: {len(content)} chars")
print()

# Build payload
payload = {
    "chat_id": chat_id,
    "text": content,
    "parse_mode": "MarkdownV2",
    "disable_web_page_preview": True,
}

# Send request
url = f"https://api.telegram.org/bot{token}/sendMessage"

try:
    response = httpx.post(url, json=payload, timeout=30.0)
    print(f"Status code: {response.status_code}")
    print(f"Response body:")
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
