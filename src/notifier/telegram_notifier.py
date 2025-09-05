import aiohttp
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Notificador simple y robusto para Telegram usando HTTP (aiohttp).
    - Maneja errores 400/timeout y registra la descripción exacta devuelta por la API.
    - Mantiene contador de fallos y se desactiva temporalmente tras N fallos consecutivos
      para evitar inundar logs y saturar el bot.
    """

    def __init__(self, token: str, chat_id: str, session: Optional[aiohttp.ClientSession] = None):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self._session = session or aiohttp.ClientSession()
        self._fail_count = 0
        self._fail_threshold = 5
        self._disabled = False

    async def send_message(self, text: str, parse_mode: Optional[str] = None) -> dict:
        """
        Envía un mensaje al chat configurado.
        Lanza excepciones en caso de error (también registra y aumenta el contador de fallos).
        Si el notificador está deshabilitado por fallos repetidos, no hace nada.
        """
        if self._disabled:
            logger.warning("TelegramNotifier is disabled due to repeated failures; skipping send_message")
            return {"ok": False, "reason": "disabled"}

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            async with self._session.post(url, json=payload, timeout=10) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    data = {"ok": False, "description": f"invalid json response, status={resp.status}"}
                if resp.status != 200 or not data.get("ok", False):
                    desc = data.get("description") or data
                    logger.warning("Telegram API error (status=%s): %s", resp.status, desc)
                    self._fail_count += 1
                    if self._fail_count >= self._fail_threshold:
                        logger.error("TelegramNotifier disabling after %d consecutive failures", self._fail_count)
                        self._disabled = True
                    raise Exception(f"Telegram API error {resp.status}: {desc}")
                self._fail_count = 0
                return data

        except asyncio.TimeoutError:
            logger.warning("Telegram send_message timeout")
            self._fail_count += 1
            if self._fail_count >= self._fail_threshold:
                logger.error("TelegramNotifier disabling after %d consecutive timeouts", self._fail_count)
                self._disabled = True
            raise
        except Exception as e:
            logger.warning("Telegram send_message failed: %s", e)
            self._fail_count += 1
            if self._fail_count >= self._fail_threshold:
                logger.error("TelegramNotifier disabling after %d consecutive failures", self._fail_count)
                self._disabled = True
            raise

    async def close(self):
        """Cerrar sesión aiohttp"""
        try:
            if self._session and not self._session.closed:
                await self._session.close()
        except Exception:
            logger.debug("Error closing TelegramNotifier session", exc_info=True)
