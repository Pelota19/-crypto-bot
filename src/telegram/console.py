import asyncio
import aiohttp
from src.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

class TelegramConsole:
    def __init__(self, order_manager=None):
        self.order_manager = order_manager
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID

    async def send_message(self, message: str):
        if not self.bot_token or not self.chat_id:
            print("[Telegram] " + message)
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        print("Failed to send Telegram message:", await resp.text())
            except Exception as e:
                print("Telegram send error:", e)
