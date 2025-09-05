import asyncio
import logging
from typing import Optional
import aiohttp
import time

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """
    Async Telegram notifier with rate limiting and Retry-After handling.

    Usage:
      n = TelegramNotifier(token, chat_id, rate_limit_per_min=30)
      await n.send_message("hola")
      await n.close()
    """

    def __init__(
        self,
        token: str,
        chat_id: str,
        rate_limit_per_min: int = 30,
        max_consecutive_failures: int = 5,
        reenable_after: int = 60,  # seconds to wait before trying to re-enable after disable
    ):
        self.token = token
        self.chat_id = chat_id
        self.rate_limit_per_min = max(1, rate_limit_per_min)
        self._delay = 60.0 / self.rate_limit_per_min  # seconds between messages
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._session: Optional[aiohttp.ClientSession] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._closed = False
        self._consecutive_failures = 0
        self._max_consecutive_failures = max_consecutive_failures
        self._disabled_until: Optional[float] = None
        self._reenable_after = reenable_after
        self._start_worker()

    def _start_worker(self):
        if self._worker_task is None:
            self._session = aiohttp.ClientSession()
            self._worker_task = asyncio.create_task(self._worker())

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def send_message(self, text: str):
        """
        Public: enqueue a telegram message. Returns immediately.
        """
        if self._closed:
            logger.warning("TelegramNotifier is closed; skipping message.")
            return
        await self._queue.put(text)

    async def _do_send(self, text: str) -> bool:
        """
        Try to send a message; return True on success, False on permanent failure.
        On 429 it will raise an exception to be handled by worker (which will sleep).
        """
        await self._ensure_session()
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        headers = {"Content-Type": "application/json"}
        try:
            async with self._session.post(url, json=payload, headers=headers, timeout=15) as resp:
                text_body = await resp.text()
                if resp.status == 200:
                    self._consecutive_failures = 0
                    return True
                elif resp.status == 429:
                    # read retry-after header if present
                    retry_after = None
                    try:
                        retry_after_header = resp.headers.get("Retry-After")
                        if retry_after_header:
                            retry_after = int(retry_after_header)
                    except Exception:
                        retry_after = None
                    # Try to parse JSON for retry_after parameter
                    try:
                        j = await resp.json()
                        params = j.get("parameters", {}) or {}
                        retry_after = retry_after or int(params.get("retry_after", retry_after or 5))
                    except Exception:
                        retry_after = retry_after or 5
                    logger.warning("Telegram API 429, retry after %s seconds. body=%s", retry_after, text_body)
                    # raise to signal worker to wait and retry this message
                    raise RuntimeError(f"telegram_429:{retry_after}")
                else:
                    logger.warning("Telegram API error (status=%s): %s", resp.status, text_body)
                    self._consecutive_failures += 1
                    return False
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Telegram send exception: %s", e)
            self._consecutive_failures += 1
            return False

    async def _worker(self):
        """
        Worker loop:
         - takes messages from queue,
         - sends them spaced by self._delay,
         - if 429 encountered, sleeps retry_after and retries the same message.
         - disables the notifier temporarily after many consecutive failures, then re-enables after cooldown.
        """
        while not self._closed:
            try:
                # check disabled_until
                if self._disabled_until:
                    if time.time() < self._disabled_until:
                        await asyncio.sleep(min(1.0, self._disabled_until - time.time()))
                        continue
                    else:
                        logger.info("TelegramNotifier re-enabling after cooldown.")
                        self._disabled_until = None
                        self._consecutive_failures = 0

                text = await self._queue.get()
                # send with retry behavior for 429
                while True:
                    try:
                        ok = await self._do_send(text)
                        if ok:
                            # rate limit spacing
                            await asyncio.sleep(self._delay)
                            break
                        else:
                            # non-429 failure: check consecutive counter
                            if self._consecutive_failures >= self._max_consecutive_failures:
                                logger.error("TelegramNotifier disabling after %d consecutive failures", self._consecutive_failures)
                                self._disabled_until = time.time() + self._reenable_after
                                break
                            # short backoff then retry
                            await asyncio.sleep(min(5, max(1, self._consecutive_failures)))
                            # retry same message
                            continue
                    except RuntimeError as rte:
                        msg = str(rte)
                        if msg.startswith("telegram_429:"):
                            try:
                                retry_after = int(msg.split(":", 1)[1])
                            except Exception:
                                retry_after = 5
                            # wait retry_after seconds and then try again (do not pop the message from queue)
                            logger.warning("Sleeping %s seconds due to Telegram 429", retry_after)
                            # Respect the retry-after but also apply a little jitter
                            await asyncio.sleep(retry_after + 0.5)
                            # on waking, retry sending the same message
                            continue
                        else:
                            # unknown runtime error: break and treat as failure
                            logger.exception("Runtime error sending telegram: %s", rte)
                            self._consecutive_failures += 1
                            if self._consecutive_failures >= self._max_consecutive_failures:
                                logger.error("TelegramNotifier disabling after %d consecutive failures", self._consecutive_failures)
                                self._disabled_until = time.time() + self._reenable_after
                            break
                # done with this message
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unhandled exception in TelegramNotifier worker; sleeping 1s")
                await asyncio.sleep(1)

    async def close(self):
        self._closed = True
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
