# src/notifier/telegram_notifier.py
"""
Telegram Notifier module.
Envía notificaciones al canal/grupo de Telegram configurado.
"""

import logging
import aiohttp
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            raise ValueError("Telegram token o chat_id no configurados en el .env")
        self.token = TELEGRAM_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.session = aiohttp.ClientSession()

    async def send_message(self, text: str, parse_mode: str = "Markdown"):
        """Envía un mensaje de texto a Telegram."""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        try:
            async with self.session.post(self.api_url, json=payload) as resp:
                if resp.status != 200:
                    logger.warning(f"Telegram message failed: {resp.status}")
                else:
                    logger.info("Mensaje enviado a Telegram")
        except Exception as e:
            logger.exception(f"Error enviando mensaje a Telegram: {e}")

    async def close(self):
        """Cierra la sesión de aiohttp."""
        await self.session.close()
