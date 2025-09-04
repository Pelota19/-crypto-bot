import asyncio
import logging
from src.config import API_KEY, API_SECRET, USE_TESTNET, POSITION_SIZE_PERCENT, MAX_OPEN_TRADES, CAPITAL_MAX_USDT, TRADING_PAIRS
from src.exchange.binance_client import BinanceClient
from src.executor import Executor
from src.pair_selector import PairSelector
from src.state import bot_state
from src.telegram.console import TelegramConsole
from src.risk.manager import cap_equity

logger = logging.getLogger(__name__)

class CryptoBot:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.exchange = BinanceClient(API_KEY, API_SECRET, use_testnet=USE_TESTNET)
        self.executor = Executor(self.exchange)
        self.pair_selector = PairSelector(self.exchange, POSITION_SIZE_PERCENT)
        self.telegram = TelegramConsole()
        self._stop_event = asyncio.Event()
        self.pairs = TRADING_PAIRS

    async def start(self):
        logger.info("Starting CryptoBot")
        await self.executor.start()
        await self.telegram.send_message("🚀 CryptoBot started on TESTNET")

    async def stop(self):
        logger.info("Stopping CryptoBot")
        await self.executor.stop()
        await self.exchange.close()
        self._stop_event.set()
        await self.telegram.send_message("⛔ CryptoBot stopped")

    async def _get_usable_equity(self) -> float:
        try:
            bal = await self.exchange.get_balance_usdt()
            return min(cap_equity(bal), CAPITAL_MAX_USDT)
        except Exception:
            logger.exception("Error fetching balance, defaulting to CAPITAL_MAX_USDT")
            return CAPITAL_MAX_USDT

    async def run_trading_loop(self):
        logger.info("Entering trading loop")
        try:
            while not self._stop_event.is_set():
                if bot_state.is_paused:
                    logger.info("Bot paused, sleeping 60s")
                    await asyncio.sleep(60)
                    continue

                equity = await self._get_usable_equity()
                top_candidates = self.pair_selector.select_top_symbols(self.pairs)

                for candidate in top_candidates:
                    sym = candidate.symbol
                    if len(bot_state.open_positions) >= MAX_OPEN_TRADES:
                        break
                    df = await self.exchange.fetch_ohlcv_df(sym, "1m", 200)
                    if df.empty:
                        continue
                    # scoring simplificado
                    mom = df["close"].iloc[-1] - df["close"].iloc[-2]
                    score = 1.0 if mom > 0 else 0.0
                    if score >= 1.0:
                        side = "buy" if mom > 0 else "sell"
                        size_usd = equity * POSITION_SIZE_PERCENT
                        price = float(df["close"].iloc[-1])
                        await self.executor.open_position(sym, side, size_usd, price)
                        await self.telegram.send_message(f"{sym} {side.upper()} opened @ {price:.2f}")
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Trading loop cancelled")
        finally:
            await self.stop()
