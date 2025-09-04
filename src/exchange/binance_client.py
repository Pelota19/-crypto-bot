"""
src/exchange/binance_client.py

Async wrapper for Binance Futures via ccxt.async_support.
Soporta sandbox/testnet y modo DRY_RUN.
Mejor manejo de símbolos y errores para evitar que un símbolo inválido rompa el scanner.
"""
import time
import logging
from typing import Optional, List, Dict
import ccxt.async_support as ccxt

from config.settings import API_KEY, API_SECRET, USE_TESTNET, DRY_RUN

logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(
        self,
        api_key: str = API_KEY,
        api_secret: str = API_SECRET,
        use_testnet: bool = USE_TESTNET,
        dry_run: bool = DRY_RUN
    ):
        self.dry_run = dry_run
        opts = {"defaultType": "future"}
        # create exchange instance
        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": opts,
        })
        if use_testnet:
            try:
                # intenta activar sandbox/testnet (puede no estar disponible en algunas builds)
                self.exchange.set_sandbox_mode(True)
                logger.info("Binance sandbox mode enabled")
            except Exception:
                logger.warning("Sandbox/testnet mode no disponible en esta build de ccxt")

    # ---------- Market Data ----------
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
            # no romper todo si un símbolo no existe o hay error puntual
            logger.debug("fetch_ticker error for %s: %s", symbol, e)
            return None

    async def fetch_all_symbols(self) -> List[str]:
        """
        Retorna una lista de símbolos candidatos.
        Filtra por '/USDT' para concentrarnos en pares cotizados en USDT.
        No asume que todos esos símbolos estén disponibles en Futuros — la verificación
        final se hace con fetch_ticker/ohlcv (con manejo de errores).
        """
        try:
            markets: Dict[str, dict] = await self.exchange.load_markets()
            # markets keys son símbolos como "BTC/USDT", "TUSD/USDT", etc.
            candidates = [sym for sym in markets.keys() if sym.endswith("/USDT")]
            return candidates
        except Exception as e:
            logger.exception("fetch_all_symbols failed: %s", e)
            return []

    # ---------- Orders ----------
    async def create_market_order(self, symbol: str, side: str, amount: float) -> dict:
        if self.dry_run:
            oid = f"sim-market-{int(time.time()*1000)}"
            logger.info("DRY_RUN market order simulated: %s %s %f (%s)", symbol, side, amount, oid)
            return {"id": oid, "status": "closed", "filled": amount, "average": None}
        try:
            return await self.exchange.create_order(symbol, "market", side, amount)
        except Exception as e:
            logger.exception("create_market_order failed: %s", e)
            raise

    async def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: dict = None) -> dict:
        params = params or {}
        if self.dry_run:
            oid = f"sim-limit-{int(time.time()*1000)}"
            logger.info("DRY_RUN limit order simulated: %s %s %f @ %f (%s)", symbol, side, amount, price, oid)
            return {"id": oid, "status": "open", "price": price, "amount": amount}
        try:
            return await self.exchange.create_order(symbol, "limit", side, amount, price, params)
        except Exception as e:
            logger.exception("create_limit_order failed: %s", e)
            raise

    async def create_oco_order(self, symbol: str, side: str, quantity: float, stop_price: float, take_profit_price: float):
        """
        Crea OCO en Binance Futures usando STOP_MARKET + TAKE_PROFIT_LIMIT.
        Nota: Binance Futures no implementa OCO nativo vía API, por eso se crean 2 órdenes.
        La implementación es simple: crear TP (limit) y luego StopMarket.
        """
        if self.dry_run:
            oid = f"sim-oco-{int(time.time()*1000)}"
            logger.info("DRY_RUN OCO simulated: %s %s %f, stop %f, tp %f (%s)",
                        symbol, side, quantity, stop_price, take_profit_price, oid)
            return {"id": oid, "status": "open"}
        try:
            # Take profit limit (side = same as open side)
            await self.exchange.create_order(symbol, "LIMIT", side, quantity, take_profit_price)
            # Stop market (side opposite for triggering on adverse movement)
            stop_side = "SELL" if side == "BUY" else "BUY"
            await self.exchange.create_order(symbol, "STOP_MARKET", stop_side, quantity, None, {"stopPrice": stop_price})
            return {"status": "open"}
        except Exception as e:
            logger.exception("create_oco_order failed: %s", e)
            raise

    async def fetch_order(self, order_id: str, symbol: str = None) -> Optional[dict]:
        if self.dry_run and order_id.startswith("sim"):
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
        if self.dry_run:
            return {"USDT": {"free": 10000.0, "used": 0.0, "total": 10000.0}}
        try:
            return await self.exchange.fetch_balance(params={"type": "future"})
        except Exception as e:
            logger.exception("fetch_balance error: %s", e)
            return {}

    async def get_balance_usdt(self) -> float:
        bal = await self.fetch_balance()
        try:
            # ccxt futures balance shape suele tener 'USDT' key
            return float(bal.get("USDT", {}).get("free", 0.0) if isinstance(bal, dict) else 0.0)
        except Exception:
            return 0.0

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass
