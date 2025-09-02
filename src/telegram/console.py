from __future__ import annotations
import asyncio
import aiohttp
import logging
from src.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else ""

async def send_message(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    async with aiohttp.ClientSession() as sess:
        async with sess.post(f"{API_BASE}/sendMessage", json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}) as resp:
            if resp.status != 200:
                log.warning(f"Telegram send failed: {resp.status} {await resp.text()}")

async def poll_commands(handle_command):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    offset = 0
    while True:
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(f"{API_BASE}/getUpdates", params={"timeout": 30, "offset": offset}) as r:
                    data = await r.json()
                    for upd in data.get("result", []):
                        offset = max(offset, upd["update_id"] + 1)
                        msg = upd.get("message") or {}
                        chat_id = str(msg.get("chat", {}).get("id"))
                        if chat_id != str(TELEGRAM_CHAT_ID):
                            continue
                        text = (msg.get("text") or "").strip()
                        if text.startswith("/"):
                            await handle_command(text)
        except Exception as e:
            log.warning(f"Telegram poll error: {e}")
            await asyncio.sleep(2)
