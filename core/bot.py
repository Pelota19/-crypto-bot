# Implementación del bot principal, orquestador simple con balance cap y alertas Telegram.
import asyncio
import logging
import signal
from typing import Optional
from utils.logger import setup_logging, get_logger
from config.settings import TRADING_PAIRS, DRY_RUN, USE_TESTNET, MAX_OPEN_TRADES, DAILY_PROFIT_TARGET, CAPITAL_MAX_USDT
from src.exchange.binance_client import BinanceClient
from src.executor import Executor
from src.risk.manager import RiskManager, cap_equity
from src.strategy.strategy import build_features
from src.state import bot_state
from src.notifications.telegram import send_telegram_message

logger = get_logger(__name__)

try:
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
        self._stop_event = asyncio.Event()
        # allow string config like "BTC/USDT,ETH/USDT"
        self.pairs = TRADING_PAIRS if isinstance(TRADING_PAIRS, (list, tuple)) else [p.strip() for p in TRADING_PAIRS.split(",") if p.strip()]

    async def start(self):
        self.logger.info("Starting CryptoBot")
        await self.executor.start()
        await send_telegram_message("🚀 CryptoBot started (Test/DRY_RUN mode)" if DRY_RUN else "🚀 CryptoBot started (LIVE/Testnet)")

    async def stop(self):
        self.logger.info("Stopping CryptoBot")
        await self.executor.stop()
        await self.client.close()
        self._stop_event.set()
        await send_telegram_message("⛔ CryptoBot stopped")

    async def _get_usable_equity(self) -> float:
        """Get usable equity (cap to CAPITAL_MAX_USDT)."""
        try:
            bal = await self.client.fetch_balance()
            # Try multiple balance shapes
            usdt = 0.0
            if isinstance(bal, dict):
                # ccxt futures: bal['USDT']['free'] or bal['total']
                if 'USDT' in bal and isinstance(bal['USDT'], dict):
                    usdt = float(bal['USDT'].get('free') or bal['USDT'].get('total') or 0.0)
                elif 'total' in bal:
                    # some payloads have nested data; fallback
                    usdt = float(bal.get('total', {}).get('USDT', 0.0) or 0.0)
            usable = cap_equity(usdt)
            # Ensure we never use more than CAPITAL_MAX_USDT
            return min(usable, float(CAPITAL_MAX_USDT))
        except Exception:
            logger.exception("Error fetching balance, defaulting usable equity to CAPITAL_MAX_USDT")
            return float(CAPITAL_MAX_USDT)

    async def run_trading_loop(self):
        self.logger.info("Entering trading loop")
        try:
            while not self._stop_event.is_set():
                if bot_state.is_paused:
                    self.logger.info("Bot is paused (daily target or manual). Sleeping...")
                    await asyncio.sleep(60)
                    continue

                # Fetch usable equity once per loop
                equity = await self._get_usable_equity()

                for sym in self.pairs:
                    if bot_state.is_paused:
                        break
                    if len(bot_state.open_positions) >= MAX_OPEN_TRADES:
                        self.logger.debug("Reached MAX_OPEN_TRADES, skipping new openings")
                        break

                    raw = await self.client.fetch_ohlcv(sym, timeframe="1m", limit=200)
                    if not raw:
                        await asyncio.sleep(0.2)
                        continue

                    import pandas as pd
                    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

                    try:
                        features = build_features(df)
                    except Exception:
                        logger.exception("Failed to build features for %s", sym)
                        continue

                    score = None
                    if ai_scorer:
                        try:
                            score = ai_scorer.score(features)
                        except Exception:
                            logger.exception("AI scorer failed, falling back to heuristic")
                            score = None

                    # fallback simple heuristic
                    if score is None:
                        mom = features.get("mom", 0.0)
                        rsi_centered = features.get("rsi_centered", 0.0)
                        score = 1.0 if (mom > 0 and rsi_centered > 0) else 0.0

                    # Threshold to open trade (simple)
                    if score and score >= 1.0:
                        side = "buy" if features.get("mom", 0) > 0 else "sell"
                        # size based on configured MAX_RISK_PER_TRADE applied to capped equity
                        from config.settings import MAX_RISK_PER_TRADE, MAX_INVESTMENT
                        # Use the lesser of actual equity and MAX_INVESTMENT (but both are capped by CAPITAL_MAX_USDT)
                        effective_equity = min(equity, float(MAX_INVESTMENT))
                        size_usd = effective_equity * (float(MAX_RISK_PER_TRADE) / 100.0)
                        current_price = float(df["close"].iloc[-1])
                        await self.executor.open_position(sym, side, size_usd, current_price)

                    await asyncio.sleep(0.5)

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.logger.info("Trading loop cancelled")
        except Exception:
            self.logger.exception("Unhandled exception in trading loop")
        finally:
            await self.stop()
