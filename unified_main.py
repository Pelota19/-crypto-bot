# Reemplaza tu unified_main.py por este (o integra las funciones añadidas).
# He mantenido la mayoría de tu código original y añadí confirmaciones y monitor de fills.

import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Any
from os import getenv

from src.config import (
    API_KEY, API_SECRET, USE_TESTNET, DRY_RUN, POSITION_SIZE_PERCENT, MAX_OPEN_TRADES,
    DAILY_PROFIT_TARGET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MIN_NOTIONAL_USD, LEVERAGE,
    HEDGE_MODE
)

from src.exchange.binance_client import BinanceClient
from src.notifier.telegram_notifier import TelegramNotifier
from src.state_manager import StateManager
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== Parámetros de riesgo/estrategia =====
CAPITAL_TOTAL = 2000.0
STOP_LOSS_PORCENTAJE = 0.2 / 100      # 0.20%
RISK_REWARD_RATIO = 1.5
TIMEFRAME_SIGNAL = "1m"
TIMEFRAME_TENDENCIA = "15m"
MAX_OPERATIONS_SIMULTANEAS = MAX_OPEN_TRADES
MAX_TRADE_USDT = 50                   # tope por trade
REFRESH_SYMBOLS_MINUTES = 15          # refresh cada 15 min
TELEGRAM_MSG_MAX = 4000
PCT_CHANGE_24H = float(getenv("PCT_CHANGE_24H", "10.0"))  # 10% por defecto, configurable en .env

class CryptoBot:
    def __init__(self):
        self.exchange = BinanceClient(
            api_key=API_KEY, api_secret=API_SECRET,
            use_testnet=USE_TESTNET, dry_run=DRY_RUN, hedge_mode=HEDGE_MODE
        )
        self.telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        self.state = StateManager(daily_profit_target=DAILY_PROFIT_TARGET)
        self._stop_event = asyncio.Event()
        self.last_loop_heartbeat = datetime.now(timezone.utc)
        self.symbols: List[str] = []
        self._telegram_fail_count = 0
        self._telegram_fail_threshold = 5
        self._recent_telegram_disabled = False

    async def safe_send_telegram(self, msg: str):
        try:
            if getattr(self, "_recent_telegram_disabled", False):
                logger.warning("Telegram disabled due to repeated failures; skipping message")
                return
            if len(msg) > TELEGRAM_MSG_MAX:
                for i in range(0, len(msg), TELEGRAM_MSG_MAX):
                    await self.telegram.send_message(msg[i:i+TELEGRAM_MSG_MAX])
            else:
                await self.telegram.send_message(msg)
            self._telegram_fail_count = 0
        except Exception as e:
            logger.warning("Telegram message failed: %s", e)
            self._telegram_fail_count += 1
            if self._telegram_fail_count >= self._telegram_fail_threshold:
                logger.error("Telegram failing %d times, disabling temporarily", self._telegram_fail_count)
                self._recent_telegram_disabled = True

    async def refresh_symbols(self):
        try:
            syms = await self.exchange.fetch_all_symbols()
            filtered_syms = []
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

    async def _create_bracket_order(self, symbol: str, side: str, quantity: float,
                                    entry_price: float, stop_price: float, take_profit_price: float,
                                    wait_timeout: int = 30) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
        entry_order = stop_order = tp_order = None
        close_side = "SELL" if side.upper() == "BUY" else "BUY"
        position_side = "LONG" if side.upper() == "BUY" else "SHORT"

        # Create entry
        try:
            params_entry = {"timeInForce": "GTC", "positionSide": position_side}
            entry_order = await self.exchange.create_order(symbol, "limit", side, quantity, entry_price, params_entry)
            logger.info("LIMIT entry creada %s: %s", symbol, entry_order)
        except Exception as e:
            raise Exception(f"No se pudo crear orden LIMIT de entrada para {symbol}: {e}") from e

        # Create SL
        try:
            params_sl = {
                "stopPrice": stop_price,
                "reduceOnly": True,
                "timeInForce": "GTC",
                "positionSide": position_side
            }
            stop_order = await self.exchange.create_order(symbol, "stop_limit", close_side, quantity, stop_price, params_sl)
            logger.info("SL stop-limit creado %s: %s", symbol, stop_order)
        except Exception as e:
            logger.warning("Crear SL falló para %s: %s", symbol, e)
            stop_order = None

        # Create TP
        try:
            params_tp = {
                "stopPrice": take_profit_price,
                "reduceOnly": True,
                "timeInForce": "GTC",
                "positionSide": position_side
            }
            tp_order = await self.exchange.create_order(symbol, "take_profit_limit", close_side, quantity, take_profit_price, params_tp)
            logger.info("TP take-profit-limit creado %s: %s", symbol, tp_order)
        except Exception as e:
            logger.warning("Crear TP falló para %s: %s", symbol, e)
            tp_order = None

        # --- Enviar confirmación a Telegram: qué órdenes se pudieron crear ---
        try:
            created_msgs = []
            if entry_order:
                created_msgs.append("Entry ✅")
            else:
                created_msgs.append("Entry ❌")
            created_msgs.append("SL ✅" if stop_order else "SL ❌")
            created_msgs.append("TP ✅" if tp_order else "TP ❌")
            msg = f"📥 {symbol} {position_side} LIMIT @ {entry_price:.6f}\n" \
                  f"{' | '.join(created_msgs)}\nQty {quantity:.6f}"
            await self.safe_send_telegram(msg)
        except Exception:
            logger.exception("Error enviando confirmación de creación de órdenes a Telegram")

        return entry_order, stop_order, tp_order

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

    async def ejecutar_trade(self, sym: str, signal: str):
        if sym in getattr(self.state, "open_positions", {}):
            return
        size_usdt = CAPITAL_TOTAL * POSITION_SIZE_PERCENT
        try:
            ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_SIGNAL, limit=1)
            if not ohlcv:
                await self.safe_send_telegram(f"⚠️ No se pudo obtener precio para {sym}")
                return
            price = float(ohlcv[-1][4])
        except Exception as e:
            await self.safe_send_telegram(f"❌ Error obteniendo precio para {sym}: {e}")
            return

        quantity = min(MAX_TRADE_USDT / price, size_usdt / price) * LEVERAGE
        notional = quantity * price
        if notional < MIN_NOTIONAL_USD:
            await self.safe_send_telegram(f"⚠️ Orden ignorada {sym}: Notional {notional:.2f} < min {MIN_NOTIONAL_USD}")
            return

        if signal == "long":
            entry = price
            sl = entry * (1 - STOP_LOSS_PORCENTAJE)
            tp = entry + (entry - sl) * RISK_REWARD_RATIO
            side = "BUY"
        elif signal == "short":
            entry = price
            sl = entry * (1 + STOP_LOSS_PORCENTAJE)
            tp = entry - (sl - entry) * RISK_REWARD_RATIO
            side = "SELL"
        else:
            return

        try:
            entry_order, stop_order, tp_order = await self._create_bracket_order(sym, side, quantity, entry, sl, tp)
            # extraer order ids si existen
            entry_id = None
            sl_id = None
            tp_id = None
            try:
                if entry_order and isinstance(entry_order, dict):
                    entry_id = entry_order.get("id") or entry_order.get("info", {}).get("orderId")
                if stop_order and isinstance(stop_order, dict):
                    sl_id = stop_order.get("id") or stop_order.get("info", {}).get("orderId")
                if tp_order and isinstance(tp_order, dict):
                    tp_id = tp_order.get("id") or tp_order.get("info", {}).get("orderId")
            except Exception:
                pass

            # registrar posición con quantity y order ids
            self.state.register_open_position(sym, signal, entry, quantity, sl, tp, entry_order_id=entry_id, sl_order_id=sl_id, tp_order_id=tp_id)

            if entry_order:
                await self.safe_send_telegram(
                    f"✅ {sym} {signal.upper()} LIMIT @ {entry:.6f}\nSL {sl:.6f} | TP {tp:.6f} | Qty {quantity:.6f}"
                )
            else:
                await self.safe_send_telegram(f"❌ No se pudo crear orden LIMIT para {sym}")
        except Exception as e:
            await self.safe_send_telegram(f"❌ Error al abrir {sym}: {e}")

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

    # --------------------
    # Monitor para detectar ejecución de SL/TP y notificar con PnL
    # --------------------
    async def monitor_order_fills(self, poll_interval: float = 2.0):
        while True:
            try:
                open_positions = self.state.get_open_positions().copy()
                for sym, pos in open_positions.items():
                    sl_id = pos.get("sl_order_id")
                    tp_id = pos.get("tp_order_id")
                    entry_price = pos.get("entry")
                    side = pos.get("side")
                    quantity = float(pos.get("quantity", 0.0))

                    # comprobar SL
                    if sl_id:
                        order = await self.exchange.fetch_order(sl_id, sym)
                        if order:
                            status = (order.get("status") or "").lower()
                            filled = float(order.get("filled") or 0.0)
                            avg = order.get("average") or order.get("info", {}).get("avgPrice")
                            try:
                                avg = float(avg) if avg is not None else None
                            except Exception:
                                avg = None
                            if filled > 0 and status in ("closed", "canceled") or status == "closed" or (order.get("info", {}).get("status", "").upper() == "FILLED"):
                                # asumimos cierre por SL
                                close_price = avg or order.get("price") or pos.get("sl")
                                pnl = 0.0
                                try:
                                    if close_price is not None:
                                        if side == "long":
                                            pnl = (float(close_price) - float(entry_price)) * filled
                                        else:
                                            pnl = (float(entry_price) - float(close_price)) * filled
                                except Exception:
                                    pnl = 0.0
                                # registrar y notificar
                                self.state.register_closed_position(sym, pnl, "SL", close_price, sl_id)
                                await self.safe_send_telegram(f"🔒 {sym} cerrada por SL. PnL: {pnl:.2f} USDT | Qty: {filled:.6f} | Entry {entry_price:.6f} -> Close {close_price}")
                                # intentar cancelar TP si existe
                                if tp_id:
                                    await self.exchange.cancel_order(tp_id, sym)
                                continue

                    # comprobar TP
                    if tp_id:
                        order = await self.exchange.fetch_order(tp_id, sym)
                        if order:
                            status = (order.get("status") or "").lower()
                            filled = float(order.get("filled") or 0.0)
                            avg = order.get("average") or order.get("info", {}).get("avgPrice")
                            try:
                                avg = float(avg) if avg is not None else None
                            except Exception:
                                avg = None
                            if filled > 0 and status in ("closed", "canceled") or status == "closed" or (order.get("info", {}).get("status", "").upper() == "FILLED"):
                                close_price = avg or order.get("price") or pos.get("tp")
                                pnl = 0.0
                                try:
                                    if close_price is not None:
                                        if side == "long":
                                            pnl = (float(close_price) - float(entry_price)) * filled
                                        else:
                                            pnl = (float(entry_price) - float(close_price)) * filled
                                except Exception:
                                    pnl = 0.0
                                self.state.register_closed_position(sym, pnl, "TP", close_price, tp_id)
                                await self.safe_send_telegram(f"🏁 {sym} cerrada por TP. PnL: {pnl:.2f} USDT | Qty: {filled:.6f} | Entry {entry_price:.6f} -> Close {close_price}")
                                # intentar cancelar SL si existe
                                if sl_id:
                                    await self.exchange.cancel_order(sl_id, sym)
                                continue
                await asyncio.sleep(poll_interval)
            except Exception as e:
                logger.exception("Error en monitor_order_fills: %s", e)
                await asyncio.sleep(5)

# ===== Loop auxiliares =====
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

async def monitor_positions(bot: CryptoBot):
    while True:
        closed_positions = getattr(bot.state, "closed_positions_history", [])
        for pos in closed_positions or []:
            try:
                sym = pos.get("symbol")
                pnl = pos.get("pnl", 0.0)
                reason = pos.get("reason", "unknown")
                await bot.safe_send_telegram(f"📉 {sym} cerrada por {reason}. PnL: {pnl:.2f} USDT")
            except Exception:
                continue
        await asyncio.sleep(5)

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
        await bot.safe_send_telegram("🚀 CryptoBot iniciado en TESTNET (limit-only orders, full-scan PERPETUAL USDT-M)")
        tasks.append(asyncio.create_task(symbols_refresher(bot)))
        tasks.append(asyncio.create_task(periodic_report(bot)))
        tasks.append(asyncio.create_task(monitor_positions(bot)))
        tasks.append(asyncio.create_task(watchdog_loop(bot)))
        # nuevo: monitor de fills
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
            logger.debug("Error cerrando exchange")
        try:
            await bot.telegram.close()
        except Exception:
            logger.debug("Error cerrando telegram session")

if __name__ == "__main__":
    asyncio.run(main())
