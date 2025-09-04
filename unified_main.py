"""
Unified CryptoBot para Binance Futures (USDT-M)
Trading en Testnet o Real según configuración
"""
import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta

from src.config import (
    API_KEY,
    API_SECRET,
    USE_TESTNET,
    CAPITAL_MAX_USDT,
    POSITION_SIZE_PERCENT,
    MAX_OPEN_TRADES,
    DAILY_PROFIT_TARGET,
    TRADING_PAIRS,
)
from src.exchange.binance_client import BinanceClient
from src.executor import Executor
from src.strategy.strategy import build_features
from src.state import bot_state
from src.risk.manager import RiskManager, cap_equity
from src.pair_selector import PairSelector
from src.notifier.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class CryptoBot:
    def __init__(self):
        self.exchange = BinanceClient(api_key=API_KEY, api_secret=API_SECRET, use_testnet=USE_TESTNET)
        self.executor = Executor(self.exchange)
        self.risk_manager = RiskManager()
        self.pair_selector = PairSelector()
        self.telegram = TelegramNotifier()
        self._stop_event = asyncio.Event()
        self.pairs = TRADING_PAIRS
        self.watchlist_dinamica = []

        # Estado de PnL diario
        self.pnl_diario = 0.0
        self.last_watchlist_update = datetime.utcnow() - timedelta(hours=1)

    async def actualizar_watchlist(self):
        """Actualizar watchlist dinámica cada hora."""
        logger.info("Actualizando watchlist dinámica...")
        all_symbols = await self.exchange.get_all_symbols()
        candidates = []

        for sym in all_symbols:
            ticker = await self.exchange.fetch_ticker(sym)
            if ticker is None:
                continue
            vol24h = float(ticker.get("quoteVolume", 0))
            if vol24h < 50_000_000:  # filtro volumen
                continue

            # Obtener OHLCV 15m para ATR
            ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe="15m", limit=15)
            if not ohlcv:
                continue
            df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "vol"])
            df["atr"] = df["high"] - df["low"]
            atr = df["atr"].mean()
            price_close = df["close"].iloc[-1]
            if (atr / price_close) < 0.005:  # filtro volatilidad
                continue
            candidates.append((sym, vol24h))

        # Ordenar por volumen y tomar top 15
        candidates.sort(key=lambda x: x[1], reverse=True)
        self.watchlist_dinamica
