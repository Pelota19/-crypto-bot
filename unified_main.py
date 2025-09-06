# unified_main.py
"""
Unified CryptoBot - archivo completo y autónomo.

Incluye:
- soporte POSITION_SIZE_MODE ("risk" o "percent")
- cálculo qty por riesgo (RISK_USDT) o por porcentaje
- ajuste de qty a stepSize con BinanceClient.adjust_amount_to_step
- integración con ScalpingOrderManager
- monitor de fills (único emisor de notificaciones) que calcula PnL por trades y notifica
- lógica para crear SL/TP cuando la entry se llena después del timeout
- tareas auxiliares: symbols_refresher, periodic_report, watchdog
"""

import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any, Dict
from os import getenv
import os
import math

# Load .env early so getenv reads values from .env (optional: wrapped in try/except)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- Añadir esto lo antes posible en unified_main.py (después de load_dotenv) ---
from logger_config import setup_logging
# Ruta relativa dentro del repo: se creará la carpeta logs y el archivo
setup_logging(logfile="logs/unified_main.log.txt", level=logging.INFO)
# ------------------------------------------------------------------------------

from src.config import (
    API_KEY, API_SECRET, USE_TESTNET, DRY_RUN, DAILY_PROFIT_TARGET,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, HEDGE_MODE
)
from src.exchange.binance_client import BinanceClient
from src.notifier.telegram_notifier import TelegramNotifier
from src.state_manager import StateManager
from src.trading.scalping_order_manager import ScalpingOrderManager
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

# Obtener logger para este módulo (root logger ya configurado por setup_logging)
logger = logging.getLogger(__name__)

# ===== Parámetros (desde env con valores por defecto) =====
CAPITAL_TOTAL = float(getenv("CAPITAL_TOTAL", "2000.0"))
POSITION_SIZE_PERCENT = float(getenv("POSITION_SIZE_PERCENT", "0.025"))
POSITION_SIZE_MODE = getenv("POSITION_SIZE_MODE", "risk")  # "risk" or "percent"
RISK_USDT = float(getenv("RISK_USDT", "5.0"))
MAX_TRADE_USDT = float(getenv("MAX_TRADE_USDT", "50"))
MIN_NOTIONAL_USD = float(getenv("MIN_NOTIONAL_USD", "1.0"))
LEVERAGE = float(getenv("LEVERAGE", "1"))
STOP_LOSS_PCT = float(getenv("STOP_LOSS_PCT", "0.003"))
RISK_REWARD_RATIO = float(getenv("RISK_REWARD_RATIO", "2.0"))
TP_TIMEOUT_SEC = int(getenv("TP_TIMEOUT_SEC", "10"))
ENTRY_FILL_TIMEOUT_SEC = int(getenv("ENTRY_FILL_TIMEOUT_SEC", "60"))
USE_MARK_PRICE_FOR_SL = getenv("USE_MARK_PRICE_FOR_SL", "True").lower() in ("1", "true", "yes")
MIN_TP_DISTANCE_PCT = float(getenv("MIN_TP_DISTANCE_PCT", "0.0002"))
# THRESHOLD para filtrar pares por cambio 24h (configurable en .env)
PCT_CHANGE_24H = float(getenv("PCT_CHANGE_24H", "10.0"))

TELEGRAM_RATE_PER_MIN = int(getenv("TELEGRAM_RATE_PER_MIN", "30"))
MAX_OPERATIONS_SIMULTANEAS = int(getenv("MAX_OPEN_TRADES", "6"))

TIMEFRAME_SIGNAL = "1m"
TIMEFRAME_TENDENCIA = "15m"
REFRESH_SYMBOLS_MINUTES = int(getenv("REFRESH_SYMBOLS_MINUTES", "15"))
TELEGRAM_MSG_MAX = 4000

class CryptoBot:
    def __init__(self):
        self.exchange = BinanceClient(
            api_key=API_KEY, api_secret=API_SECRET,
            use_testnet=USE_TESTNET, dry_run=DRY_RUN, hedge_mode=HEDGE_MODE
        )
        self.telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, rate_limit_per_min=TELEGRAM_RATE_PER_MIN)
        self.state = StateManager(daily_profit_target=DAILY_PROFIT_TARGET)
        self.scalper = ScalpingOrderManager(self.exchange, self.state, notifier=self.telegram, tp_timeout=TP_TIMEOUT_SEC, entry_fill_timeout=ENTRY_FILL_TIMEOUT_SEC, hedge_mode=HEDGE_MODE)
        self._stop_event = asyncio.Event()
        self.last_loop_heartbeat = datetime.now(timezone.utc)
        self.symbols: List[str] = []

    async def safe_send_telegram(self, msg: str):
        try:
            if len(msg) <= TELEGRAM_MSG_MAX:
                await self.telegram.send_message(msg)
            else:
                for i in range(0, len(msg), TELEGRAM_MSG_MAX):
                    await self.telegram.send_message(msg[i:i+TELEGRAM_MSG_MAX])
        except Exception as e:
            logger.warning("Telegram message enqueue failed: %s", e)

    async def refresh_symbols(self):
        try:
            syms = await self.exchange.fetch_all_symbols()
            filtered_syms = []
            # Note: this is still one API call per symbol for 24h change; can be optimized later
            for sym in syms:
                change_pct = await self.exchange.fetch_24h_change(sym)
                if change_pct is not None and change_pct >= PCT_CHANGE_24H:
                    filtered_syms.append(sym)
            self.symbols = filtered_syms
            logger.info("Símbolos filtrados por ±%s%%: %s", PCT_CHANGE_24H, filtered_syms)
            await self.safe_send_telegram(f"🔄 Lista de símbolos refrescada ({len(filtered_syms)}): {filtered_syms}")
        except Exception as e:
            logger.exception("Error refrescando símbolos: %s", e)
            await self.safe_send_telegram(f"❌ Error refrescando símbolos: {e}")

    async def analizar_signal(self, sym: str) -> Optional[str]:
        try:
            ohlcv_1m = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_SIGNAL, limit=50)
            ohlcv_15m = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_TENDENCIA, limit=50)
            if not ohlcv_1m or not ohlcv_15m:
                return None
            df_1m = pd.DataFrame(ohlcv_1m, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df_15m = pd.DataFrame(ohlcv_15m, columns=["timestamp", "open", "high", "low", "close", "volume"])

            ema9 = EMAIndicator(df_1m["close"], window=9).ema_indicator().iloc[-1]
            ema21 = EMAIndicator(df_1m["close"], window=21).ema_indicator().iloc[-1]
            rsi14 = RSIIndicator(df_1m["close"], window=14).rsi().iloc[-1]
            ema50_15m = EMAIndicator(df_15m["close"], window=50).ema_indicator().iloc[-1]
            price = float(df_1m["close"].iloc[-1])

            ohlcv_24h = await self.exchange.fetch_ohlcv(sym, timeframe="1d", limit=2)
            if ohlcv_24h and len(ohlcv_24h) == 2:
                price_prev = float(ohlcv_24h[0][4])
                pct_change = abs((price - price_prev) / price_prev * 100)
                if pct_change < PCT_CHANGE_24H:
                    return None

            if price > ema50_15m and ema9 > ema21 and rsi14 < 65:
                return "long"
            if price < ema50_15m and ema9 < ema21 and rsi14 > 35:
                return "short"
            return None
        except Exception as e:
            msg = str(e)
            if "Invalid symbol" in msg or "Invalid symbol status" in msg:
                logger.info("Símbolo inválido/estado inválido %s: %s", sym, msg)
                return None
            logger.debug("Error analizando %s: %s", sym, e)
            return None

    def _compute_qty_by_percent(self, price: float) -> float:
        size_usdt = CAPITAL_TOTAL * POSITION_SIZE_PERCENT
        qty = min(MAX_TRADE_USDT / price, size_usdt / price) * LEVERAGE
        return qty

    def _compute_qty_by_risk(self, entry_price: float, stop_loss_pct: float, risk_usdt: float) -> float:
        sl = entry_price * (1 - stop_loss_pct)
        distance = abs(entry_price - sl)
        if distance <= 0:
            return 0.0
        qty = risk_usdt / distance
        return qty

    async def ejecutar_trade(self, sym: str, signal: str):
        if sym in getattr(self.state, "open_positions", {}):
            return

        try:
            ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_SIGNAL, limit=1)
            if not ohlcv:
                await self.safe_send_telegram(f"⚠️ No se pudo obtener precio para {sym}")
                return
            price = float(ohlcv[-1][4])
        except Exception as e:
            await self.safe_send_telegram(f"❌ Error obteniendo precio para {sym}: {e}")
            return

        # Calculate qty based on mode
        if POSITION_SIZE_MODE == "risk":
            qty = self._compute_qty_by_risk(price, STOP_LOSS_PCT, RISK_USDT)
        else:
            qty = self._compute_qty_by_percent(price)

        # adjust to step size
        qty = self.exchange.adjust_amount_to_step(sym, qty)
        notional = qty * price
        if qty <= 0 or notional < MIN_NOTIONAL_USD:
            await self.safe_send_telegram(f"⚠️ Orden ignorada {sym}: qty {qty:.6f} notional {notional:.2f} < min {MIN_NOTIONAL_USD}")
            return

        try:
            meta = await self.scalper.place_scalping_trade(
                symbol=sym,
                side=signal,
                entry_price=price,
                amount=qty,
                stop_loss_pct=STOP_LOSS_PCT,
                rr_ratio=RISK_REWARD_RATIO,
                tp_timeout=TP_TIMEOUT_SEC,
                entry_fill_timeout=ENTRY_FILL_TIMEOUT_SEC,
            )
            if meta.get("entry_order_id"):
                await self.safe_send_telegram(f"📥 {sym} {signal.upper()} LIMIT @ {price:.6f}\nQty {qty:.6f}\nEntry order id: {meta.get('entry_order_id')}")
                msgs = []
                if meta.get("sl_order_id"):
                    msgs.append(f"SL id={meta.get('sl_order_id')} type={meta.get('sl_type')}")
                else:
                    msgs.append("SL ❌")
                if meta.get("tp_order_id"):
                    msgs.append(f"TP id={meta.get('tp_order_id')} type={meta.get('tp_type')}")
                else:
                    msgs.append("TP ❌")
                await self.safe_send_telegram(" | ".join(msgs))
            else:
                await self.safe_send_telegram(f"❌ Entry order for {sym} could not be placed.")
        except Exception as e:
            logger.exception("Error placing scalping trade for %s: %s", sym, e)
            await self.safe_send_telegram(f"❌ Error placing scalping trade for {sym}: {e}")

    async def procesar_par(self, sym: str):
        signal = await self.analizar_signal(sym)
        if signal:
            await self.ejecutar_trade(sym, signal)

    async def run_trading_loop(self):
        while not self._stop_event.is_set():
            self.last_loop_heartbeat = datetime.now(timezone.utc)
            self.state.reset_daily_if_needed()

            if not getattr(self.state, "can_open_new_trade", lambda: True)() or \
               len(getattr(self.state, "open_positions", {})) >= MAX_OPERATIONS_SIMULTANEAS:
                await asyncio.sleep(5)
                continue
            if not self.symbols:
                await asyncio.sleep(2)
                continue

            CHUNK = 8
            for i in range(0, len(self.symbols), CHUNK):
                batch = self.symbols[i:i+CHUNK]
                tasks = [self.procesar_par(sym) for sym in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(0.5)
            await asyncio.sleep(1)

    async def monitor_order_fills(self, poll_interval: float = 2.0):
        """
        Monitor que:
         - actualiza entry_filled/entry_avg
         - detecta ejecuciones SL/TP
         - coloca SL/TP post-fill si la entry se llenó después de abortar SL/TP
         - calcula PnL usando trades (fetch_trades_for_order) y notifica
         - cancela orden opuesta y registra cierre
        """
        async def _compute_pnl_from_trades(side: str, entry_order_id: Optional[str], close_order_id: str, sym: str):
            try:
                entry_trades = []
                if entry_order_id:
                    entry_trades = await self.exchange.fetch_trades_for_order(entry_order_id, sym)
                close_trades = await self.exchange.fetch_trades_for_order(close_order_id, sym)
                if not close_trades:
                    return None, None

                def _sum_trades(trades):
                    total_amount = 0.0
                    total_cost = 0.0
                    total_fees = 0.0
                    for t in trades:
                        amt = float(t.get("amount") or t.get("info", {}).get("executedQty") or 0.0)
                        cost = float(t.get("cost") or (float(t.get("price") or 0.0) * amt))
                        fee = 0.0
                        try:
                            fee = float((t.get("fee") or {}).get("cost") or t.get("info", {}).get("commission") or 0.0)
                        except Exception:
                            fee = 0.0
                        total_amount += amt
                        total_cost += cost
                        total_fees += fee
                    return {"amount": total_amount, "cost": total_cost, "fees": total_fees}

                entry_summary = _sum_trades(entry_trades) if entry_trades else {"amount": 0.0, "cost": 0.0, "fees": 0.0}
                close_summary = _sum_trades(close_trades)

                if entry_summary["amount"] > 0:
                    qty_closed = min(entry_summary["amount"], close_summary["amount"])
                    entry_cost_for_qty = (entry_summary["cost"] / entry_summary["amount"]) * qty_closed if entry_summary["amount"] else 0.0
                    close_cost_for_qty = (close_summary["cost"] / close_summary["amount"]) * qty_closed if close_summary["amount"] else 0.0
                    fees_for_qty = (entry_summary["fees"] / entry_summary["amount"]) * qty_closed if entry_summary["amount"] else 0.0
                    fees_for_qty += (close_summary["fees"] / close_summary["amount"]) * qty_closed if close_summary["amount"] else 0.0
                else:
                    qty_closed = close_summary["amount"]
                    entry_cost_for_qty = entry_summary["cost"]
                    close_cost_for_qty = close_summary["cost"]
                    fees_for_qty = entry_summary["fees"] + close_summary["fees"]

                if qty_closed <= 0:
                    return None, None

                if side == "long":
                    pnl = close_cost_for_qty - entry_cost_for_qty - fees_for_qty
                else:
                    pnl = entry_cost_for_qty - close_cost_for_qty - fees_for_qty

                details = {
                    "qty_closed": qty_closed,
                    "entry_cost": entry_cost_for_qty,
                    "close_cost": close_cost_for_qty,
                    "fees": fees_for_qty,
                    "entry_trades": entry_trades,
                    "close_trades": close_trades,
                }
                return pnl, details
            except Exception as e:
                logger.exception("Error computing pnl from trades for %s %s %s: %s", sym, entry_order_id, close_order_id, e)
                return None, None

        while True:
            try:
                open_positions = self.state.get_open_positions().copy()
                for sym, pos in list(open_positions.items()):
                    entry_id = pos.get("entry_order_id")
                    sl_id = pos.get("sl_order_id")
                    tp_id = pos.get("tp_order_id")
                    side = pos.get("side")
                    entry_price = float(pos.get("entry") or 0.0)
                    entry_avg = pos.get("entry_avg")
                    entry_filled = float(pos.get("entry_filled") or 0.0)
                    closed_flag = pos.get("closed", False)
                    if closed_flag:
                        continue

                    # 1) Revisar ejecución de la entry (parciales)
                    if entry_id:
                        order = await self.exchange.fetch_order(entry_id, sym)
                        if order:
                            filled = float(order.get("filled") or order.get("info", {}).get("executedQty") or 0.0)
                            avg = order.get("average") or order.get("info", {}).get("avgPrice")
                            try:
                                avg = float(avg) if avg is not None else None
                            except Exception:
                                avg = None
                            if filled and filled != entry_filled:
                                self.state.update_entry_execution(sym, filled, avg or entry_price)
                                await self.safe_send_telegram(f"✳️ {sym} ENTRY ejecutada {side.upper()} qty={filled:.6f} avg={avg or entry_price:.6f}")

                                # NEW: si la posición no tiene SL o TP registrados, colocarlos ahora
                                pos_after = self.state.get_open_positions().get(sym, {})
                                has_sl = bool(pos_after.get("sl_order_id"))
                                has_tp = bool(pos_after.get("tp_order_id"))
                                # solo si no existe SL/TP intentamos colocarlos (evitar duplicados)
                                if not has_sl or not has_tp:
                                    # use entry_avg if available
                                    entry_used_price = float(pos_after.get("entry_avg") or pos_after.get("entry") or entry_price)
                                    qty_for_protection = float(pos_after.get("entry_filled") or filled)
                                    logger.info("Detected fills for %s; placing missing SL/TP (sl_exists=%s tp_exists=%s) qty=%s avg=%s", sym, has_sl, has_tp, qty_for_protection, entry_used_price)
                                    try:
                                        meta_post = await self.scalper.place_sl_tp_for_existing_position(
                                            symbol=sym,
                                            side=side,
                                            entry_avg=entry_used_price,
                                            filled_qty=qty_for_protection,
                                            stop_loss_pct=STOP_LOSS_PCT,
                                            rr_ratio=RISK_REWARD_RATIO,
                                            position_side_override=pos_after.get("positionSide"),
                                            notify=True,
                                        )
                                        # log outcome
                                        if meta_post.get("errors"):
                                            logger.warning("Post-fill SL/TP placement for %s returned errors: %s", sym, meta_post.get("errors"))
                                        else:
                                            logger.info("Post-fill SL/TP placement for %s succeeded: sl=%s tp=%s", sym, meta_post.get("sl"), meta_post.get("tp"))
                                    except Exception as e:
                                        logger.exception("Error placing SL/TP after fills for %s: %s", sym, e)

                    # Helper para procesar un order id (SL o TP)
                    async def _process_close_order(order_id, reason_label):
                        if not order_id:
                            return False
                        order = await self.exchange.fetch_order(order_id, sym)
                        if not order:
                            return False
                        filled = float(order.get("filled") or order.get("info", {}).get("executedQty") or 0.0)
                        avg = order.get("average") or order.get("info", {}).get("avgPrice")
                        try:
                            avg = float(avg) if avg is not None else None
                        except Exception:
                            avg = None
                        if filled <= 0:
                            return False

                        pnl = None
                        pnl_details = None
                        try:
                            pnl, pnl_details = await _compute_pnl_from_trades(side, entry_id, order_id, sym)
                        except Exception:
                            pnl = None

                        close_price = avg or order.get("price") or pos.get("sl") or pos.get("tp")
                        if pnl is None:
                            try:
                                entry_used = float(pos.get("entry_avg") or pos.get("entry") or 0.0)
                                if side == "long":
                                    pnl = (float(close_price) - entry_used) * filled
                                else:
                                    pnl = (entry_used - float(close_price)) * filled
                            except Exception:
                                pnl = 0.0

                        self.state.register_closed_position(sym, pnl, reason_label, close_price=(avg or order.get("price")), close_order_id=order_id)
                        opp_id = pos.get("tp_order_id") if reason_label == "SL" else pos.get("sl_order_id")
                        if opp_id:
                            try:
                                await self.exchange.cancel_order(opp_id, sym)
                            except Exception:
                                logger.debug("Cancel of opposite order failed for %s: %s", sym, opp_id)
                        pos["closed"] = True
                        self.state.open_positions.pop(sym, None)
                        if pnl_details:
                            await self.safe_send_telegram(
                                f"🏁 {sym} cerrada por {reason_label}. PnL: {pnl:.2f} USDT | Qty: {pnl_details.get('qty_closed', 0.0):.6f} | Entry cost {pnl_details.get('entry_cost', 0.0):.6f} -> Close cost {pnl_details.get('close_cost', 0.0):.6f} | Fees {pnl_details.get('fees', 0.0):.6f}"
                            )
                        else:
                            if reason_label == "TP":
                                await self.safe_send_telegram(f"🏁 {sym} cerrada por TP. PnL: {pnl:.2f} USDT | Qty: {filled:.6f} | Entry {pos.get('entry_avg') or pos.get('entry'):.6f} -> Close {close_price}")
                            else:
                                await self.safe_send_telegram(f"🔒 {sym} cerrada por SL. PnL: {pnl:.2f} USDT | Qty: {filled:.6f} | Entry {pos.get('entry_avg') or pos.get('entry'):.6f} -> Close {close_price}")
                        return True

                    # 2) Procesar SL primero, luego TP
                    if pos.get("sl_order_id"):
                        sl_triggered = await _process_close_order(pos.get("sl_order_id"), "SL")
                        if sl_triggered:
                            continue

                    if pos.get("tp_order_id"):
                        tp_triggered = await _process_close_order(pos.get("tp_order_id"), "TP")
                        if tp_triggered:
                            continue

                await asyncio.sleep(poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error en monitor_order_fills: %s", e)
                await asyncio.sleep(5)


# Aux loops
async def symbols_refresher(bot: CryptoBot):
    await bot.refresh_symbols()
    while True:
        await asyncio.sleep(REFRESH_SYMBOLS_MINUTES * 60)
        await bot.refresh_symbols()

async def periodic_report(bot: CryptoBot):
    while True:
        await asyncio.sleep(3600)
        open_syms = list(getattr(bot.state, "open_positions", {}).keys())
        pnl = getattr(bot.state, "realized_pnl_today", 0.0)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        await bot.safe_send_telegram(
            f"🕒 Reporte horario {ts}\n📌 Operaciones abiertas: {len(open_syms)}\n📌 PnL diario: {pnl:.2f} USDT\n📌 Símbolos escaneados: {len(bot.symbols)}"
        )

async def watchdog_loop(bot: CryptoBot):
    while True:
        await asyncio.sleep(60)
        if (datetime.now(timezone.utc) - bot.last_loop_heartbeat) > timedelta(seconds=120):
            await bot.safe_send_telegram("⚠️ Alert: posible bloqueo del bot")


# ===== Main =====
async def main():
    bot = CryptoBot()
    tasks = []
    try:
        await bot.safe_send_telegram("🚀 CryptoBot iniciado (sizing por risk/percent, SL/TP mejorado)")
        tasks.append(asyncio.create_task(symbols_refresher(bot)))
        tasks.append(asyncio.create_task(periodic_report(bot)))
        tasks.append(asyncio.create_task(watchdog_loop(bot)))
        tasks.append(asyncio.create_task(bot.monitor_order_fills()))
        await bot.run_trading_loop()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado recibida")
        await bot.safe_send_telegram("⏹️ CryptoBot detenido manualmente")
    except Exception as e:
        logger.exception("Error crítico en main: %s", e)
        await bot.safe_send_telegram(f"❌ Error crítico en main: {e}")
    finally:
        for t in tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        try:
            await bot.exchange.close()
        except Exception:
            pass
        try:
            await bot.telegram.close()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
