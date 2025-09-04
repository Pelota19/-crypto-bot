"""
Async wrapper for Binance Futures (USDT-M) testnet real via ccxt.async_support.
"""

import time
import logging
from typing import Optional, List, Dict, Any
import ccxt.async_support as ccxt

from src.config import API_KEY, API_SECRET, USE_TESTNET, DRY_RUN

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(self, api_key: str = API_KEY, api_secret: str = API_SECRET,
                 use_testnet: bool = USE_TESTNET, dry_run: bool = DRY_RUN):
        self.dry_run = dry_run

        opts = {"defaultType": "future"}
        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": opts,
        })

        if use_testnet:
            # URL específica para TESTNET real de Binance Futures (USDT-M)
            self.exchange.urls["api"] = {
                "public": "https://testnet.binancefuture.com/fapi/v1",
                "private": "https://testnet.binancefuture.com/fapi/v1",
            }
            logger.info("✅ Binance TESTNET real habilitado (USDT-M).")
        else:
            logger.info("✅ Binance MAINNET habilitado (USDT-M).")

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200) -> List:
        try:
            return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as e:
            logger.exception("fetch_ohlcv error for %s: %s", symbol, e)
            return []

    async def fetch_ticker(self, symbol: str) -> Optional[dict]:
        try:
            return await self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.exception("fetch_ticker error for %s: %s", symbol, e)
            return None

    async def create_market_order(self, symbol: str, side: str, amount: float) -> Dict[str, Any]:
        """Create a market order (real, no simulation)."""
        if self.dry_run:
            oid = f"sim-market-{int(time.time()*1000)}"
            logger.info("DRY_RUN market order simulated: %s %s %f (%s)", symbol, side, amount, oid)
            return {"id": oid, "status": "closed", "filled": amount, "average": None}

        try:
            order = await self.exchange.create_order(symbol, "market", side, amount)
            logger.info("✅ Market order sent: %s %s %f", symbol, side, amount)
            return order
        except Exception as e:
            logger.exception("create_market_order failed: %s", e)
            raise

    async def fetch_balance(self) -> dict:
        """Fetch real futures balance."""
        if self.dry_run:
            return {"USDT": {"free": 10000.0, "used": 0.0, "total": 10000.0}}
        try:
            bal = await self.exchange.fetch_balance(params={"type": "future"})
            return bal
        except Exception as e:
            logger.exception("fetch_balance error: %s", e)
            return {}

    async def get_balance_usdt(self) -> float:
        """Helper: get available USDT balance."""
        bal = await self.fetch_balance()
        if "USDT" in bal:
            return bal["USDT"].get("free", 0.0)
        return 0.0

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass
