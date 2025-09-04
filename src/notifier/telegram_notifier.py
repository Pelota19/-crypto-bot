import logging
import requests
import datetime

logger = logging.getLogger(__name__)

class Notifier:
    def __init__(self, telegram_token, chat_id):
        self.telegram_token = telegram_token
        self.chat_id = chat_id

    def send(self, message: str):
        """Enviar mensaje a Telegram + log local"""
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"[{timestamp} UTC]\n{message}"
        logger.info(f"[Telegram] {full_message}")

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        try:
            requests.post(url, data={"chat_id": self.chat_id, "text": full_message})
        except Exception as e:
            logger.error(f"Error enviando a Telegram: {e}")
