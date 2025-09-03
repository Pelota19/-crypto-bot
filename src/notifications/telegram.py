"""Simple async Telegram notifier for important events."""
import logging
import aiohttp
from typing import Optional
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

async def send_telegram_message(text: str, parse_mode: str = "HTML") -> Optional[dict]:
    """Send a message to configured Telegram chat. Returns API response dict or None on failure."""
    token = TELEGRAM_BOT_TOKEN
    chat_id = TELEGRAM_CHAT_ID
    if not token or not chat_id:
        # No telegram configured; avoid raising
        logger.debug("Telegram not configured, skipping message: %s", text)
        return None

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    logger.error("Telegram API error: %s", data)
                return data
    except Exception as e:
        logger.exception("Failed to send telegram message: %s", e)
        return None
