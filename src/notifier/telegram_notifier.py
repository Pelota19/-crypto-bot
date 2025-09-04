# src/notifier/telegram_notifier.py
import logging
import aiohttp
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, telegram_token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.token = telegram_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.session = aiohttp.ClientSession()

    async def send_message(self, message: str):
        """Envía un mensaje de Telegram al chat configurado."""
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        try:
            async with self.session.post(self.api_url, data=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"Telegram send_message failed: {resp.status} - {text}")
        except Exception as e:
            logger.exception(f"Error enviando mensaje a Telegram: {e}")

    async def close(self):
        await self.session.close()
