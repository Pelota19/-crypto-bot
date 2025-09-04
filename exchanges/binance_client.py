"""
Async wrapper for Binance Futures via ccxt.async_support.
Soporta sandbox/testnet y DRY_RUN.
Provee create_bracket_order para emular OCO en Futures.
Incluye manejo robusto de símbolos inválidos y errores comunes.
"""
import time
import logging
from typing import Optional, List, Tuple
import asyncio
import ccxt.async_support as ccxt

from config.settings import API_KEY, API_SECRET, USE_TESTNET, DRY_RUN, LEVERAGE, MARGIN_MODE

logger = logging.getLogger(__name__)

class BinanceClient:
    def __init__(self, api_key=API_KEY, api_secret=API_SECRET, use_testnet=USE_TESTNET, dry_run=DRY_RUN):
        self.dry_run = dry_run
        opts = {"defaultType": "future"}
        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": opts,
        })
        if use_testnet:
            try:
                self.exchange.set_sandbox_mode(True)
                logger.info("Binance sandbox mode enabled")
            except Exception:
                logger.warning("Sandbox/testnet mode no disponible en esta build de ccxt")
        self.markets_cache = {}

    async def load_markets(self):
        if not self.markets_cache:
            try:
                self.markets_cache = await self.exchange.load_markets()
            except Exception as e:
                logger.exception("Error cargando mercados: %s", e)
        return self.markets_cache

    async def set_leverage(self, symbol: str):
        if self.dry_run:
            return
        try:
            await self.exchange.fapiPrivate_post_leverage({
                "symbol": symbol.replace("/", ""),
                "leverage": int(LEVERAGE)
            })
            await self.exchange.fapiPrivate_post_marginType({
                "symbol": symbol.replace("/", ""),
                "marginType": MARGIN_MODE
            })
            logger.info("Leverage %dx y margin mode %s aplicado a %s", LEVERAGE, MARGIN_MODE, symbol)
        except Exception as e:
            logger.exception("No se pudo aplicar leverage/margin para %s: %s", symbol, e)

    # ---------- Market Data ----------
    async def fetch_ohlcv(self, symbol: str, timeframe="1m", limit=200) -> List:
        try:
            markets = await self.load_markets()
            if symbol not in markets:
                logger.warning("fetch_ohlcv: símbolo inválido %s", symbol)
                return []
            return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=None, limit=limit)
        except Exception as e:
            logger.debug("fetch_ohlcv error for %s: %s", symbol, e)
            return []

    async def fetch_ticker(self, symbol: str) -> Optional[dict]:
        try:
            markets = await self.load_markets()
            if symbol not in markets:
                logger.warning("fetch_ticker: símbolo inválido %s", symbol)
                return None
            return await self.exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.debug("fetch_ticker error for %s: %s", symbol, e)
            return None

    async def fetch_all_symbols(self) -> List[str]:
        try:
            markets = await self.load_markets()
            # Solo pares USDT activos y perpetuos
            return [
                sym for sym, m in markets.items()
                if sym.endswith("/USDT") and m.get("active", False) and m.get("contractType") == "PERPETUAL"
            ]
        except Exception as e:
            logger.exception("fetch_all_symbols failed: %s", e)
            return []

    # ---------- Orders ----------
    async def create_bracket_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
        wait_timeout: int = 30
    ) -> Tuple[Optional[dict], Optional[dict], Optional[dict]]:
        await self.set_leverage(symbol)
        logger.info("=== CREATE_BRACKET_ORDER START === %s %s", symbol, side)

        try:
            markets = await self.load_markets()
            if symbol not in markets or not markets[symbol].get("active", False):
                logger.warning("Símbolo %s inválido o inactivo", symbol)
                return None, None, None
            market = markets[symbol]
            min_qty = float(market.get("limits", {}).get("amount", {}).get("min", 0))
            step_size = float(market.get("limits", {}).get("amount", {}).get("step", 1))
        except Exception as e:
            logger.warning("No se pudo obtener market info %s: %s", symbol, e)
            min_qty, step_size = 0, 1

        # Excepción SOL/USDT
        if symbol == "SOL/USDT" and quantity < min_qty:
            min_qty = quantity

        # Ajustar quantity
        quantity *= LEVERAGE
        if step_size > 0:
            quantity = (quantity // step_size) * step_size
        if quantity < min_qty:
            logger.warning("Cantidad %s menor al mínimo %s para %s. Orden ignorada.", quantity, min_qty, symbol)
            return None, None, None

        if self.dry_run:
            oid = f"sim-bracket-{int(time.time()*1000)}"
            logger.info("DRY_RUN bracket simulated: %s %s %f entry=%f stop=%f tp=%f", symbol, side, quantity, entry_price, stop_price, take_profit_price)
            return ({"id": f"{oid}-entry"}, {"id": f"{oid}-stop"}, {"id": f"{oid}-tp"})

        try:
            params_entry = {"timeInForce": "GTX"}
            entry_order = await self.exchange.create_order(symbol, "LIMIT", side, quantity, entry_price, params_entry)

            # Esperar fill
            start = time.time()
            entry_id = entry_order.get("id") or entry_order.get("orderId")
            entry_filled = False
            while time.time() - start < wait_timeout:
                ordinfo = await self.exchange.fetch_order(entry_id, symbol)
                if ordinfo and ordinfo.get("status") in ("closed", "filled"):
                    entry_filled = True
                    break
                await asyncio.sleep(0.5)
            if not entry_filled:
                await self.exchange.cancel_order(entry_id, symbol)
                return None, None, None

            # Stop Market
            stop_side = "SELL" if side.upper() == "BUY" else "BUY"
            stop_order = await self.exchange.create_order(symbol, "STOP_MARKET", stop_side, quantity, None, {"stopPrice": stop_price})

            # Take Profit LIMIT
            tp_side = "SELL" if side.upper() == "BUY" else "BUY"
            tp_order = await self.exchange.create_order(symbol, "LIMIT", tp_side, quantity, take_profit_price, {"timeInForce": "GTX"})

            logger.info("=== CREATE_BRACKET_ORDER END ===")
            return entry_order, stop_order, tp_order

        except Exception as e:
            logger.exception("Error creando bracket order %s: %s", symbol, e)
            return None, None, None

    async def fetch_balance(self) -> dict:
        if self.dry_run:
            return {"USDT": {"free": 10000.0, "used": 0.0, "total": 10000.0}}
        try:
            return await self.exchange.fetch_balance(params={"type":"future"})
        except Exception as e:
            logger.exception("fetch_balance error: %s", e)
            return {}

    async def get_balance_usdt(self) -> float:
        bal = await self.fetch_balance()
        try:
            return float(bal.get("USDT", {}).get("free", 0.0))
        except Exception:
            return 0.0

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass
