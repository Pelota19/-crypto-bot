# src/trading/scalping_order_manager.py
"""
ScalpingOrderManager

Gestiona la colocación de entradas LIMIT, creación de SL (STOP_MARKET con MARK_PRICE)
y TP (TAKE_PROFIT_LIMIT con fallback a TAKE_PROFIT_MARKET pasado TP_TIMEOUT_SEC).

Interfaz principal:
  - ScalpingOrderManager(binance_client, state_manager, notifier, config)
  - await place_scalping_trade(symbol, side, entry_price, amount, stop_loss_pct, rr_ratio)
"""

import asyncio
import logging
from typing import Optional, Tuple, Dict, Any
import time
import math
import os

logger = logging.getLogger(__name__)

# Valores por defecto (pueden ser overrideados por config pasado al constructor)
DEFAULT_ENTRY_FILL_TIMEOUT = int(os.getenv("ENTRY_FILL_TIMEOUT_SEC", "60"))
DEFAULT_TP_TIMEOUT = int(os.getenv("TP_TIMEOUT_SEC", "10"))
USE_MARK_PRICE_FOR_SL = os.getenv("USE_MARK_PRICE_FOR_SL", "True").lower() in ("1", "true", "yes")

class ScalpingOrderManager:
    def __init__(self, exchange_client, state_manager, notifier=None, *,
                 tp_timeout: int = DEFAULT_TP_TIMEOUT,
                 entry_fill_timeout: int = DEFAULT_ENTRY_FILL_TIMEOUT,
                 hedge_mode: bool = True):
        """
        exchange_client: instancia de BinanceClient (wrapper ccxt)
        state_manager: StateManager
        notifier: TelegramNotifier (opcional) - se usará para informar sobre fallbacks / errores
        """
        self.exchange = exchange_client
        self.state = state_manager
        self.notifier = notifier
        self.tp_timeout = int(tp_timeout)
        self.entry_fill_timeout = int(entry_fill_timeout)
        self.hedge_mode = bool(hedge_mode)
        # Locks por símbolo para evitar race conditions
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, symbol: str) -> asyncio.Lock:
        if symbol not in self._locks:
            self._locks[symbol] = asyncio.Lock()
        return self._locks[symbol]

    @staticmethod
    def calculate_sl_tp_prices(entry: float, side: str, stop_loss_pct: float, rr: float) -> Tuple[float, float]:
        """
        Calcula sl y tp según la especificación:
        LONG:
            sl = entry * (1 - STOP_LOSS_PCT)
            distancia = entry - sl
            tp = entry + distancia * RISK_REWARD_RATIO
        SHORT: invertido
        """
        if side.lower() == "long":
            sl = entry * (1 - stop_loss_pct)
            distance = entry - sl
            tp = entry + distance * rr
        else:
            sl = entry * (1 + stop_loss_pct)
            distance = sl - entry
            tp = entry - distance * rr
        return float(sl), float(tp)

    async def _wait_order_filled(self, order_id: str, symbol: str, target_qty: float, timeout: int) -> Tuple[bool, float, Optional[float]]:
        """
        Espera a que la orden order_id en symbol se llene por completo (filled == target_qty).
        Retorna (filled_fully_bool, filled_qty, avg_price_or_None)
        - Si se llena parcialmente pero no llega a target antes del timeout, devuelve False y la cantidad/fill existente.
        """
        start = time.time()
        last_filled = 0.0
        last_avg = None
        while True:
            try:
                order = await self.exchange.fetch_order(order_id, symbol)
                if not order:
                    await asyncio.sleep(0.5)
                else:
                    filled = float(order.get("filled") or order.get("info", {}).get("executedQty", 0.0))
                    avg = order.get("average") or order.get("info", {}).get("avgPrice")
                    try:
                        avg = float(avg) if avg is not None else None
                    except Exception:
                        avg = None
                    last_filled = filled
                    last_avg = avg
                    if math.isclose(filled, target_qty, rel_tol=1e-9) or filled >= target_qty:
                        return True, filled, avg
                if time.time() - start > timeout:
                    # timeout
                    return False, last_filled, last_avg
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.exception("Error waiting order fill %s %s: %s", order_id, symbol, e)
                await asyncio.sleep(1)
                if time.time() - start > timeout:
                    return False, last_filled, last_avg

    async def place_scalping_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        amount: float,
        stop_loss_pct: float,
        rr_ratio: float,
        *,
        tp_timeout: Optional[int] = None,
        entry_fill_timeout: Optional[int] = None,
        position_side_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Flujo:
         - Coloca LIMIT entry (maker)
         - Espera fill completo (entry_fill_timeout)
         - Calcula SL/TP
         - Coloca SL como STOP_MARKET (workingType=MARK_PRICE si configurado), reduceOnly True
         - Coloca TP como TAKE_PROFIT_LIMIT (reduceOnly True)
         - Lanza tarea background que espera tp_timeout y si TP no ejecuta, lo cancela y coloca TAKE_PROFIT_MARKET
        Devuelve dict con metadata sobre orders creadas y estados.
        """
        lock = self._get_lock(symbol)
        async with lock:
            tp_timeout = int(tp_timeout or self.tp_timeout)
            entry_fill_timeout = int(entry_fill_timeout or self.entry_fill_timeout)
            position_side = position_side_override
            if self.hedge_mode and not position_side:
                position_side = "LONG" if side.lower() == "long" else "SHORT"

            meta: Dict[str, Any] = {
                "symbol": symbol,
                "side": side,
                "entry_price": entry_price,
                "requested_amount": amount,
                "entry_order_id": None,
                "entry_filled": 0.0,
                "entry_avg": None,
                "sl": None,
                "tp": None,
                "sl_order_id": None,
                "tp_order_id": None,
                "sl_type": None,
                "tp_type": None,
                "tp_fallback_to_market": False,
                "errors": [],
            }

            # 1) Place LIMIT entry
            try:
                params_entry = {"timeInForce": "GTC"}
                if self.hedge_mode:
                    params_entry["positionSide"] = position_side
                entry_order = await self.exchange.create_order(symbol, "limit", "buy" if side.lower() == "long" else "sell", amount, entry_price, params_entry)
                entry_id = entry_order.get("id") or entry_order.get("info", {}).get("orderId")
                meta["entry_order_id"] = entry_id
                logger.info("Placed LIMIT entry for %s: %s", symbol, entry_order)
            except Exception as e:
                logger.exception("Failed to place LIMIT entry for %s: %s", symbol, e)
                meta["errors"].append(f"entry_create_failed:{e}")
                if self.notifier:
                    try:
                        await self.notifier.send_message(f"❌ ENTRY create failed for {symbol}: {e}")
                    except Exception:
                        pass
                return meta

            # 2) Wait until filled
            try:
                filled_ok, filled_qty, avg_price = await self._wait_order_filled(meta["entry_order_id"], symbol, amount, entry_fill_timeout)
                meta["entry_filled"] = float(filled_qty)
                meta["entry_avg"] = float(avg_price) if avg_price is not None else None
                # update state
                self.state.register_open_position(symbol, side, entry_price, amount, 0.0, 0.0, entry_order_id=meta["entry_order_id"], entry_avg=meta["entry_avg"], entry_filled=meta["entry_filled"])  # sl/tp placeholders updated later
                if not filled_ok:
                    msg = f"⚠️ Entry for {symbol} not fully filled within timeout: filled={filled_qty}, requested={amount}"
                    logger.warning(msg)
                    meta["errors"].append("entry_not_filled_within_timeout")
                    if self.notifier:
                        try:
                            await self.notifier.send_message(msg)
                        except Exception:
                            pass
                    # we continue using whatever was filled (optionally you can cancel remainder)
                else:
                    logger.info("Entry filled for %s qty=%s avg=%s", symbol, filled_qty, avg_price)
            except Exception as e:
                logger.exception("Error waiting entry fill for %s: %s", symbol, e)
                meta["errors"].append(f"wait_entry_error:{e}")
                return meta

            # compute real qty to consider (the filled amount)
            real_qty = float(meta["entry_filled"] or 0.0)
            if real_qty <= 0:
                # nothing executed; nothing to do
                msg = f"Entry for {symbol} had no fills; aborting SL/TP placement."
                logger.warning(msg)
                meta["errors"].append("entry_no_fills")
                if self.notifier:
                    try:
                        await self.notifier.send_message(msg)
                    except Exception:
                        pass
                return meta

            # 3) Calculate SL and TP from executed average price (prefer avg)
            use_entry_price_for_calc = float(meta["entry_avg"] or entry_price)
            sl_price, tp_price = self.calculate_sl_tp_prices(use_entry_price_for_calc, side, stop_loss_pct, rr_ratio)
            meta["sl"] = sl_price
            meta["tp"] = tp_price

            # 4) Place SL as STOP_MARKET with workingType=MARK_PRICE and reduceOnly=True
            try:
                sl_params = {"stopPrice": sl_price, "reduceOnly": True}
                if USE_MARK_PRICE_FOR_SL:
                    sl_params["workingType"] = "MARK_PRICE"
                if self.hedge_mode:
                    sl_params["positionSide"] = position_side
                # place STOP_MARKET (we enforce stop_market for SL per requirement)
                sl_order = await self.exchange.create_order(symbol, "stop_market", "sell" if side.lower() == "long" else "buy", real_qty, None, sl_params)
                sl_id = sl_order.get("id") or sl_order.get("info", {}).get("orderId")
                sl_type = (sl_order.get("type") or sl_order.get("info", {}).get("origType") or "stop_market").lower()
                meta["sl_order_id"] = sl_id
                meta["sl_type"] = sl_type
                self.state.set_sl_order(symbol, sl_id, sl_type, fallback_used=False)
                logger.info("SL placed for %s: id=%s type=%s", symbol, sl_id, sl_type)
            except Exception as e:
                # On failure, try fallback: remove reduceOnly, retry with stop_market if another type was requested
                logger.exception("SL placement failed for %s: %s", symbol, e)
                meta["errors"].append(f"sl_create_failed:{e}")
                try:
                    params_retry = {"stopPrice": sl_price}
                    if USE_MARK_PRICE_FOR_SL:
                        params_retry["workingType"] = "MARK_PRICE"
                    if self.hedge_mode:
                        params_retry["positionSide"] = position_side
                    sl_order = await self.exchange.create_order(symbol, "stop_market", "sell" if side.lower() == "long" else "buy", real_qty, None, params_retry)
                    sl_id = sl_order.get("id") or sl_order.get("info", {}).get("orderId")
                    sl_type = (sl_order.get("type") or sl_order.get("info", {}).get("origType") or "stop_market").lower()
                    meta["sl_order_id"] = sl_id
                    meta["sl_type"] = sl_type
                    self.state.set_sl_order(symbol, sl_id, sl_type, fallback_used=True)
                    logger.info("SL placed after retry for %s: id=%s type=%s", symbol, sl_id, sl_type)
                    if self.notifier:
                        try:
                            await self.notifier.send_message(f"⚠️ SL fallback used for {symbol}: {sl_type}")
                        except Exception:
                            pass
                except Exception as e2:
                    logger.exception("SL fallback also failed for %s: %s", symbol, e2)
                    meta["errors"].append(f"sl_fallback_failed:{e2}")
                    if self.notifier:
                        try:
                            await self.notifier.send_message(f"❌ SL placement failed for {symbol}: {e2}")
                        except Exception:
                            pass

            # 5) Place TP as TAKE_PROFIT_LIMIT (reduceOnly True). If fails, fallback handling by client may convert to market type.
            try:
                tp_params = {"stopPrice": tp_price, "reduceOnly": True, "timeInForce": "GTC"}
                if self.hedge_mode:
                    tp_params["positionSide"] = position_side
                tp_order = await self.exchange.create_order(symbol, "take_profit_limit", "sell" if side.lower() == "long" else "buy", real_qty, tp_price, tp_params)
                tp_id = tp_order.get("id") or tp_order.get("info", {}).get("orderId")
                tp_type = (tp_order.get("type") or tp_order.get("info", {}).get("origType") or "take_profit_limit").lower()
                meta["tp_order_id"] = tp_id
                meta["tp_type"] = tp_type
                self.state.set_tp_order(symbol, tp_id, tp_type, fallback_used=False)
                logger.info("TP placed for %s: id=%s type=%s", symbol, tp_id, tp_type)
            except Exception as e:
                logger.exception("TP placement failed for %s: %s", symbol, e)
                meta["errors"].append(f"tp_create_failed:{e}")
                # attempt to retry without reduceOnly (client may still fallback)
                try:
                    params_retry = {"stopPrice": tp_price, "timeInForce": "GTC"}
                    if self.hedge_mode:
                        params_retry["positionSide"] = position_side
                    tp_order = await self.exchange.create_order(symbol, "take_profit_limit", "sell" if side.lower() == "long" else "buy", real_qty, tp_price, params_retry)
                    tp_id = tp_order.get("id") or tp_order.get("info", {}).get("orderId")
                    tp_type = (tp_order.get("type") or tp_order.get("info", {}).get("origType") or "take_profit_limit").lower()
                    meta["tp_order_id"] = tp_id
                    meta["tp_type"] = tp_type
                    self.state.set_tp_order(symbol, tp_id, tp_type, fallback_used=True)
                    meta["tp_fallback_to_market"] = (tp_type != "take_profit_limit")
                    logger.info("TP placed after retry for %s: id=%s type=%s", symbol, tp_id, tp_type)
                    if meta["tp_fallback_to_market"] and self.notifier:
                        try:
                            await self.notifier.send_message(f"⚠️ TP fallback used for {symbol}: {tp_type}")
                        except Exception:
                            pass
                except Exception as e2:
                    logger.exception("TP fallback also failed for %s: %s", symbol, e2)
                    meta["errors"].append(f"tp_fallback_failed:{e2}")
                    if self.notifier:
                        try:
                            await self.notifier.send_message(f"❌ TP placement failed for {symbol}: {e2}")
                        except Exception:
                            pass

            # 6) Launch background watcher for TP timeout -> fallback to TAKE_PROFIT_MARKET
            if meta.get("tp_order_id"):
                asyncio.create_task(self._monitor_tp_timeout(symbol, meta["tp_order_id"], tp_price, tp_timeout, real_qty, position_side))

            return meta

    async def _monitor_tp_timeout(self, symbol: str, tp_order_id: str, tp_price: float, tp_timeout: int, qty: float, position_side: Optional[str]):
        """
        Espera tp_timeout segundos; si la TP sigue abierta -> cancela y coloca TAKE_PROFIT_MARKET.
        Maneja race conditions y estados intermedios.
        """
        try:
            await asyncio.sleep(int(tp_timeout))
            # re-check order status
            order = await self.exchange.fetch_order(tp_order_id, symbol)
            if not order:
                logger.info("TP order %s not found (maybe executed) for %s", tp_order_id, symbol)
                return
            filled = float(order.get("filled") or order.get("info", {}).get("executedQty") or 0.0)
            if filled > 0:
                logger.info("TP order %s for %s already partially/fully filled (filled=%s); nothing to do", tp_order_id, symbol, filled)
                return
            status = (order.get("status") or "").lower()
            if status in ("closed", "canceled", "filled", "cancelled"):
                logger.info("TP order %s for %s in status %s; no fallback needed", tp_order_id, symbol, status)
                return

            # attempt to cancel TP_LIMIT
            try:
                await self.exchange.cancel_order(tp_order_id, symbol)
                logger.info("Cancelled TP_LIMIT %s for %s after timeout; placing TP_MARKET", tp_order_id, symbol)
            except Exception as e:
                logger.warning("Cancel TP failed for %s (%s): %s", tp_order_id, symbol, e)
                # re-fetch to see if it executed meanwhile
                order2 = await self.exchange.fetch_order(tp_order_id, symbol)
                if order2 and float(order2.get("filled") or order2.get("info", {}).get("executedQty") or 0.0) > 0:
                    logger.info("TP executed during cancel retry for %s", symbol)
                    return
                # if still cannot cancel, report and attempt placing TP_MARKET anyway
            # place TAKE_PROFIT_MARKET with same stopPrice (tp_price)
            try:
                params_market_tp = {"stopPrice": tp_price, "reduceOnly": True}
                if self.hedge_mode and position_side:
                    params_market_tp["positionSide"] = position_side
                tp_market = await self.exchange.create_order(symbol, "take_profit_market", "sell" if position_side == "LONG" else "buy", qty, None, params_market_tp)
                tp_market_id = tp_market.get("id") or tp_market.get("info", {}).get("orderId")
                logger.info("Placed TAKE_PROFIT_MARKET %s for %s (fallback after timeout)", tp_market_id, symbol)
                # record fallback in state
                self.state.set_tp_order(symbol, tp_market_id, (tp_market.get("type") or tp_market.get("info", {}).get("origType")), fallback_used=True)
                if self.notifier:
                    try:
                        await self.notifier.send_message(f"⚠️ TP degraded to MARKET for {symbol} after timeout (tp={tp_price})")
                    except Exception:
                        pass
            except Exception as e:
                logger.exception("Failed to place TP_MARKET for %s after timeout: %s", symbol, e)
                if self.notifier:
                    try:
                        await self.notifier.send_message(f"❌ Failed to place TP_MARKET for {symbol} after timeout: {e}")
                    except Exception:
                        pass

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.exception("Error in TP timeout monitor for %s: %s", symbol, e)
