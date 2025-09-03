# Implementación del bot principal, orquestador simple.
import asyncio
import logging
import signal
from typing import Optional
from utils.logger import setup_logging, get_logger
from config.settings import TRADING_PAIRS, DRY_RUN, USE_TESTNET, MAX_OPEN_TRADES
from src.exchange.binance_client import BinanceClient
from src.executor import Executor
from src.risk.manager import RiskManager
from src.strategy.strategy import build_features
from src.state import bot_state

logger = get_logger(__name__)

try:
    # Intentamos importar un scorer de IA si existe
    from src.ai.scorer import scorer as ai_scorer
except Exception:
    ai_scorer = None

class CryptoBot:
    def __init__(self):
        setup_logging()
        self.logger = get_logger(__name__)
        self.client = BinanceClient(dry_run=DRY_RUN, use_testnet=USE_TESTNET)
        self.risk_manager = RiskManager()
        self.executor = Executor(self.client, self.risk_manager, dry_run=DRY_RUN)
        self._tasks = []
        self._stop_event = asyncio.Event()
        self.pairs = TRADING_PAIRS

    async def start(self):
        self.logger.info("Starting CryptoBot")
        await self.executor.start()

    async def stop(self):
        self.logger.info("Stopping CryptoBot")
        await self.executor.stop()
        await self.client.close()
        self._stop_event.set()

    async def run_trading_loop(self):
        self.logger.info("Entering trading loop")
        try:
            while not self._stop_event.is_set():
                if bot_state.is_paused:
                    self.logger.info("Bot is paused (daily target or manual). Sleeping until next day or resume.")
                    await asyncio.sleep(60)
                    continue

                # Loop through pairs (simple sequential approach)
                for sym in self.pairs:
                    if bot_state.is_paused:
                        break
                    # Limit concurrent open trades
                    if len(bot_state.open_positions) >= MAX_OPEN_TRADES:
                        self.logger.debug("Reached MAX_OPEN_TRADES, skipping new openings")
                        break

                    raw = await self.client.fetch_ohlcv(sym, timeframe="1m", limit=200)
                    if not raw:
                        continue

                    # Convert raw ohlcv to dict-like structure expected por build_features
                    import pandas as pd
                    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                    features = build_features(df)

                    score = None
                    if ai_scorer:
                        try:
                            score = ai_scorer.score(features)
                        except Exception:
                            logger.exception("AI scorer failed, falling back to heuristic")
                            score = None

                    # Simple fallback rule: mom > 0 and rsi_centered > 0 -> buy signal
                    if score is None:
                        s = features.get("mom", 0)
                        r = features.get("rsi_centered", 0)
                        score = 1.0 if (s > 0 and r > 0) else 0.0

                    # If score triggers, open position (very simple threshold)
                    if score and score >= 1.0:
                        # Determine side and size
                        side = "buy" if features.get("mom", 0) > 0 else "sell"
                        # For size, we use MAX_RISK_PER_TRADE * MAX_INVESTMENT in risk manager or settings
                        from config.settings import MAX_INVESTMENT, MAX_RISK_PER_TRADE
                        size_usd = MAX_INVESTMENT * (MAX_RISK_PER_TRADE / 100.0)
                        current_price = float(df["close"].iloc[-1])
                        await self.executor.open_position(sym, side, size_usd, current_price)

                    await asyncio.sleep(0.5)  # small delay per pair

                await asyncio.sleep(1)  # loop delay
        except asyncio.CancelledError:
            self.logger.info("Trading loop cancelled")
        except Exception:
            self.logger.exception("Unhandled exception in trading loop")
        finally:
            await self.stop()
