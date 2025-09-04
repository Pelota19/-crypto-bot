"""
Bot principal unificado para Crypto Scalping
Conexión directa a Binance Futures TESTNET (USDT-M)
"""

import asyncio
import logging
import pandas as pd

from src.config import (
    API_KEY, API_SECRET, USE_TESTNET, DRY_RUN,
    POSITION_SIZE_PERCENT, MAX_OPEN_TRADES,
    DAILY_PROFIT_TARGET, CAPITAL_MAX_USDT, TRADING_PAIRS
)
from src.exchange.binance_client import BinanceClient
from src.executor import Executor
from src.strategy.strategy import build_features
from src.state import bot_state
from src.risk.manager import RiskManager, cap_equity
from src.pair_selector import PairSelector
from src.persistence.sqlite_store import save_balance
from src.telegram.console import TelegramConsole

logger = logging.getLogger(__name__)


class CryptoBot:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logger

        self.exchange = BinanceClient(
            api_key=API_KEY,
            api_secret=API_SECRET,
            use_testnet=USE_TESTNET,
            dry_run=DRY_RUN,
        )
        self.risk_manager = RiskManager()
        self.executor = Executor(self.exchange, self.risk_manager, dry_run=DRY_RUN)
        self._stop_event = asyncio.Event()
        self.pair_selector = PairSelector(self.exchange)
        self.telegram = TelegramConsole(order_manager=None)  # conectar luego con executor
        self.pairs = TRADING_PAIRS

    async def start(self):
        self.logger.info("Starting CryptoBot")
        await self.executor.start()
        await self.telegram.send_message("🚀 CryptoBot started on TESTNET")

    async def stop(self):
        self.logger.info("Stopping CryptoBot")
        await self.executor.stop()
        await self.exchange.close()
        self._stop_event.set()
        await self.telegram.send_message("⛔ CryptoBot stopped")

    async def _get_usable_equity(self) -> float:
        """Get usable equity (capped by CAPITAL_MAX_USDT)."""
        try:
            bal = await self.exchange.get_balance_usdt()
            usable = cap_equity(bal)
            return min(usable, CAPITAL_MAX_USDT)
        except Exception:
            self.logger.exception("Error fetching balance, defaulting to CAPITAL_MAX_USDT")
            return CAPITAL_MAX_USDT

    async def run_trading_loop(self):
        self.logger.info("Entering trading loop")
        try:
            while not self._stop_event.is_set():
                if bot_state.is_paused:
                    self.logger.info("Bot paused, sleeping 60s")
                    await asyncio.sleep(60)
                    continue

                equity = await self._get_usable_equity()
                top_candidates = await self.pair_selector.select_top_symbols(
                    self.pairs, POSITION_SIZE_PERCENT
                )

                for sym, score in top_candidates:
                    if len(bot_state.open_positions) >= MAX_OPEN_TRADES:
                        break

                    raw = await self.exchange.fetch_ohlcv(sym, timeframe="1m", limit=200)
                    if not raw:
                        continue

                    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

                    try:
                        features = build_features(df)
                    except Exception:
                        self.logger.exception("Failed to build features for %s", sym)
                        continue

                    mom = features.get("mom", 0)
                    rsi_centered = features.get("rsi_centered", 0)
                    score = 1.0 if (mom > 0 and rsi_centered > 0) else 0.0

                    if score >= 1.0:
                        side = "buy" if mom > 0 else "sell"
                        size_usd = equity * POSITION_SIZE_PERCENT
                        current_price = float(df["close"].iloc[-1])
                        await self.executor.open_position(sym, side, size_usd, current_price)
                        await self.telegram.send_message(
                            f"✅ {sym} {side.upper()} opened @ {current_price:.2f}"
                        )

                    await asyncio.sleep(0.5)

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.logger.info("Trading loop cancelled")
        except Exception:
            self.logger.exception("Unhandled exception in trading loop")
        finally:
            await self.stop()


async def main():
    bot = CryptoBot()
    try:
        await bot.start()
        await bot.run_trading_loop()
    except Exception as e:
        logger.exception("Error iniciando el bot: %s", e)
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
