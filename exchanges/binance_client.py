"""
src/exchange/binance_client.py

Async wrapper for Binance Futures via ccxt.async_support.
Soporta sandbox/testnet y DRY_RUN.
Provee create_bracket_order para emular OCO en Futures (entrada LIMIT post-only,
espera fill, luego STOP_MARKET + TAKE_PROFIT_MARKET).
"""
import time
import logging
from typing import Optional, List, Dict, Tuple
import asyncio
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
        """
        try:
            markets: Dict[str, dict] = await self.exchange.load_markets()
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
        """
        Emula un bracket (entrada LIMIT post-only -> espera fill -> STOP_MARKET + TAKE_PROFIT_MARKET).
        - symbol: "BTC/USDT"
        - side: "BUY" o "SELL" (para abrir la posición)
        - quantity: cantidad en unidades del activo (base asset)
        - entry_price: precio LIMIT para la entrada
        - stop_price: precio para stop market
        - take_profit_price: precio para take profit trigger
        - wait_timeout: segundos máximo a esperar por el fill de la entrada
        Retorna (entry_order, stop_order, tp_order) (pueden ser dicts o None en DRY_RUN).
        """
        # DRY_RUN: simula
        if self.dry_run:
            oid = f"sim-bracket-{int(time.time()*1000)}"
            logger.info("DRY_RUN bracket simulated: %s %s %f entry=%f stop=%f tp=%f (%s)",
                        symbol, side, quantity, entry_price, stop_price, take_profit_price, oid)
            return ({"id": f"{oid}-entry", "status": "closed"},
                    {"id": f"{oid}-stop", "status": "open"},
                    {"id": f"{oid}-tp", "status": "open"})

        # 1) Colocar orden de entrada LIMIT como post-only (timeInForce GTX / POST_ONLY)
        try:
            params_entry = {"timeInForce": "GTX"}  # GTX es post-only compatible en ccxt/binance
            logger.info("Placing LIMIT post-only entry %s %s qty=%s price=%s", symbol, side, quantity, entry_price)
            entry_order = await self.exchange.create_order(symbol, "LIMIT", side, quantity, entry_price, params_entry)
        except Exception as e:
            logger.exception("create_bracket_entry failed: %s", e)
            raise

        # 2) Esperar a que la orden de entrada se ejecute (polling)
        entry_filled = False
        entry_fetch_id = entry_order.get("id") if isinstance(entry_order, dict) else None
        start = time.time()
        try:
            while time.time() - start < wait_timeout:
                if not entry_fetch_id:
                    break
                ordinfo = await self.fetch_order(entry_fetch_id, symbol)
                if not ordinfo:
                    await asyncio.sleep(0.5)
                    continue
                status = ordinfo.get("status") or ordinfo.get("state") or ""
                # ccxt puede devolver 'closed' o filled amount
                if status.lower() in ("closed", "filled", "canceled"):
                    # check filled
                    filled = float(ordinfo.get("filled") or ordinfo.get("amount") or 0.0)
                    if filled and filled > 0:
                        entry_filled = True
                        logger.info("Entry filled for %s: %s", symbol, ordinfo)
                        break
                    # if canceled, stop waiting
                    if status.lower() == "canceled":
                        logger.warning("Entry order canceled for %s: %s", symbol, ordinfo)
                        break
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.exception("Error while polling entry order: %s", e)

        # Si no se filled en el timeout: intentar cancelar y abortar
        if not entry_filled:
            try:
                if entry_fetch_id:
                    await self.cancel_order(entry_fetch_id, symbol)
                    logger.info("Entry order not filled in timeout, canceled: %s", entry_fetch_id)
            except Exception:
                pass
            raise RuntimeError("Entry limit order not filled within timeout")

        # 3) Una vez ejecutada la entrada, crear STOP_MARKET (SL) y TAKE_PROFIT_MARKET (TP)
        stop_order = None
        tp_order = None
        try:
            # STOP_MARKET: para protección (side invertido para cerrar la posición)
            stop_side = "SELL" if side.upper() == "BUY" else "BUY"
            params_stop = {"stopPrice": stop_price}
            logger.info("Placing STOP_MARKET %s %s qty=%s stopPrice=%s", symbol, stop_side, quantity, stop_price)
            stop_order = await self.exchange.create_order(symbol, "STOP_MARKET", stop_side, quantity, None, params_stop)
        except Exception as e:
            logger.exception("create_bracket_stop failed: %s", e)
            # no re-raise todavía: intentamos still place tp

        try:
            # TAKE_PROFIT_MARKET: colocamos market tp (trigger at take_profit_price)
            tp_side = "SELL" if side.upper() == "BUY" else "BUY"
            params_tp = {"stopPrice": take_profit_price}
            logger.info("Placing TAKE_PROFIT_MARKET %s %s qty=%s stopPrice=%s", symbol, tp_side, quantity, take_profit_price)
            tp_order = await self.exchange.create_order(symbol, "TAKE_PROFIT_MARKET", tp_side, quantity, None, params_tp)
        except Exception as e:
            logger.exception("create_bracket_tp failed: %s", e)

        return (entry_order, stop_order, tp_order)

    # legacy alias para compatibilidad: antes create_oco_order
    async def create_oco_order(self, *args, **kwargs):
        logger.warning("create_oco_order is deprecated for Futures. Using create_bracket_order instead.")
        return await self.create_bracket_order(*args, **kwargs)

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
            return float(bal.get("USDT", {}).get("free", 0.0) if isinstance(bal, dict) else 0.0)
        except Exception:
            return 0.0

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass
