"""
Async wrapper for Binance Futures via ccxt.async_support.
Supports sandbox/testnet mode (when supported by ccxt) and DRY_RUN simulation.
"""
import time
import logging
from typing import Optional, Any, List
import ccxt.async_support as ccxt

from config.settings import API_KEY, API_SECRET, USE_TESTNET, DRY_RUN

logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(self, api_key: str = API_KEY, api_secret: str = API_SECRET, use_testnet: bool = USE_TESTNET, dry_run: bool = DRY_RUN):
        self.dry_run = dry_run
        opts = {'defaultType': 'future'}
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': opts,
        })
        # Try to enable sandbox if requested (ccxt supports set_sandbox_mode for many exchanges)
        if use_testnet:
            try:
                self.exchange.set_sandbox_mode(True)
                logger.info("Binance sandbox mode enabled in ccxt client")
            except Exception:
                logger.warning("Unable to enable sandbox mode on ccxt client (may not be available in this ccxt build)")

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200) -> List:
        try:
            return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=None, limit=limit)
        except Exception as e:
            logger.exception("fetch_ohlcv error for %s: %s", symbol, e)
            return []

    async def fetch_ticker(self, symbol: str) -> Optional[dict]:
        try:
            return await self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.exception("fetch_ticker error for %s: %s", symbol, e)
            return None

    async def create_market_order(self, symbol: str, side: str, amount: float) -> dict:
        """Create a market order. amount is base asset units (e.g., BTC)."""
        if self.dry_run:
            oid = f"sim-market-{int(time.time()*1000)}"
            logger.info("DRY_RUN market order simulated: %s %s %f (%s)", symbol, side, amount, oid)
            return {"id": oid, "status": "closed", "filled": amount, "average": None}
        try:
            # For futures, sometimes 'positionSide' etc are required. Keep simple first.
            order = await self.exchange.create_order(symbol, "market", side, amount)
            return order
        except Exception as e:
            logger.exception("create_market_order failed: %s", e)
            raise

    async def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: dict = None) -> dict:
        """Create a limit order (used for TP/SL where exchange supports it)."""
        params = params or {}
        if self.dry_run:
            oid = f"sim-limit-{int(time.time()*1000)}"
            logger.info("DRY_RUN limit order simulated: %s %s %f @ %f (%s)", symbol, side, amount, price, oid)
            return {"id": oid, "status": "open", "price": price, "amount": amount}
        try:
            order = await self.exchange.create_order(symbol, "limit", side, amount, price, params)
            return order
        except Exception as e:
            logger.exception("create_limit_order failed: %s", e)
            raise

    async def fetch_order(self, order_id: str, symbol: str = None) -> Optional[dict]:
        if self.dry_run and order_id.startswith("sim"):
            # Simulated orders: keep 'open' for limit sim, 'closed' for market sim
            if order_id.startswith("sim-market"):
                return {"id": order_id, "status": "closed", "filled": None}
            return {"id": order_id, "status": "open"}
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.exception("fetch_order error: %s", e)
            return None

    async def cancel_order(self, order_id: str, symbol: str):
        if self.dry_run:
            logger.info("DRY_RUN cancel order %s %s", order_id, symbol)
            return {"id": order_id, "status": "canceled"}
        try:
            return await self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            logger.exception("cancel_order error: %s", e)
            raise

    async def fetch_balance(self) -> dict:
        """Fetch futures balance. In DRY_RUN returns a fake USDT balance for testing."""
        if self.dry_run:
            # Simulate a balance larger than cap
            return {"USDT": {"free": 10000.0, "used": 0.0, "total": 10000.0}}
        try:
            bal = await self.exchange.fetch_balance(params={"type": "future"})
            return bal
        except Exception as e:
            logger.exception("fetch_balance error: %s", e)
            return {}

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass
