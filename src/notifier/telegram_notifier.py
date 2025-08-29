import logging
import requests
import asyncio
from typing import Optional
from src.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def _send_sync(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured, skipping message: %s", text)
        return
    try:
        requests.post(f"{BASE_URL}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": text})
    except Exception as e:
        logger.exception("Failed to send telegram message: %s", e)

async def send_message(text: str):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_sync, text)
