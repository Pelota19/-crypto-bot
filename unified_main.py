"""
Unified CryptoBot - Binance Futures (USDT-M)
Scalping EMA/RSI con gestión de riesgo estricta y Bracket orders.
Telegram actúa como consola de alertas y reportes.
Modificación: entrada SOLO con órdenes LIMIT y SL/TP configuradas como stop-limit / take-profit-limit.
Versión optimizada para analizar todos los pares simultáneamente (async tasks) con throttling.
"""

import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Any

from config import (
    API_KEY, API_SECRET, USE_TESTNET, POSITION_SIZE_PERCENT, MAX_OPEN_TRADES, DAILY_PROFIT_TARGET,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MIN_NOTIONAL_USD, LEVERAGE
)

from src.exchange.binance_client import BinanceClient
from src.notifier.telegram_notifier import TelegramNotifier
from src.state import StateManager
from ta.volatility import AverageTrueRange
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CAPITAL_TOTAL = 2000.0
OBJETIVO_PROFIT_DIARIO = DAILY_PROFIT_TARGET
STOP_LOSS_PORCENTAJE = 0.2 / 100
RISK_REWARD_RATIO = 1.5

TIMEFRAME_SIGNAL = '1m'
TIMEFRAME_TENDENCIA = '15m'
TELEGRAM_MSG_MAX = 4000  # límite seguro Telegram

# Throttling básico para no saturar la API
API_CONCURRENCY_LIMIT = 5


class CryptoBot:
    def __init__(self):
        self.exchange = BinanceClient(
            api_key=API_KEY, api_secret=API_SECRET,
            use_testnet=USE_TESTNET, dry_run=False
        )
        self.telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        self.state = StateManager(daily_profit_target=OBJETIVO_PROFIT_DIARIO)
        self._stop_event = asyncio.Event()
        self.last_loop_heartbeat = datetime.now(timezone.utc)
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
            self._telegram_fail_count = getattr(self, "_telegram_fail_count", 0) + 1
            if self._telegram_fail_count >= getattr(self, "_telegram_fail_threshold", 5):
                logger.error(
                    "Telegram failing %d times consecutivas, desactivando envíos temporalmente",
                    self._telegram_fail_count
                )
                self._recent_telegram_disabled = True

    async def fetch_all_usdt_symbols(self) -> List[str]:
        """Obtiene todos los símbolos USDT disponibles en Binance Futures."""
        all_symbols = await self.exchange.fetch_all_symbols()
        return [s for s in all_symbols if isinstance(s, str) and s.upper().endswith("/USDT")]

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

            if price > ema50_15m and ema9 > ema21 and rsi14 < 65:
                return "long"
            if price < ema50_15m and ema9 < ema21 and rsi14 > 35:
                return "short"

        except Exception as e:
            msg = str(e)
            if "Invalid symbol status" in msg or "Invalid symbol" in msg:
                logger.info("Símbolo %s inválido, será ignorado", sym)
            else:
                await self.safe_send_telegram(f"❌ Error analizando {sym}: {e}")
        return None

    async def _create_bracket_order(self, symbol: str, side: str, quantity: float,
                                    entry_price: float, stop_price: float, take_profit_price: float) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:

        entry_order = stop_order = tp_order = None
        close_side = "SELL" if side.upper() == "BUY" else "BUY"

        try:
            entry_order = await self.exchange.create_order(symbol, 'limit', side, quantity, entry_price, {"timeInForce": "GTC"})
        except Exception as e:
            logger.error("No se pudo crear la orden LIMIT para %s: %s", symbol, e)
            return None, None, None

        try:
            params_sl = {"stopPrice": stop_price, "reduceOnly": True, "timeInForce": "GTC"}
            stop_order = await self.exchange.create_order(symbol, 'stop_limit', close_side, quantity, stop_price, params_sl)
        except Exception as e:
            logger.warning("SL stop-limit falló para %s: %s", symbol, e)
            stop_order = None

        try:
            params_tp = {"stopPrice": take_profit_price, "reduceOnly": True, "timeInForce": "GTC"}
            tp_order = await self.exchange.create_order(symbol, 'take_profit_limit', close_side, quantity, take_profit_price, params_tp)
        except Exception as e:
            logger.warning("TP take-profit falló para %s: %s", symbol, e)
            tp_order = None

        return entry_order, stop_order, tp_order

    async def ejecutar_trade(self, sym: str, signal: str):
        if sym in self.state.open_positions:
            return

        size_usdt = CAPITAL_TOTAL * POSITION_SIZE_PERCENT
        try:
            ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_SIGNAL, limit=1)
            price = float(ohlcv[-1][4])
        except Exception as e:
            await self.safe_send_telegram(f"❌ Error obteniendo precio para {sym}: {e}")
            return

        min_notional = MIN_NOTIONAL_USD
        if sym == "SOL/USDT":
            min_notional = min(MIN_NOTIONAL_USD, 5)

        quantity = (size_usdt / price)
        notional = price * quantity
        if notional < min_notional:
            if sym != "SOL/USDT":
                return
            else:
                quantity = min_notional / price
                notional = min_notional
        if notional > 50:
            quantity = 50 / price
            notional = 50

        quantity *= LEVERAGE

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

        entry_order, stop_order, tp_order = await self._create_bracket_order(sym, side, quantity, entry, sl, tp)
        if entry_order:
            self.state.register_open_position(sym, signal, entry, quantity * price / LEVERAGE, sl, tp)
            await self.safe_send_telegram(
                f"✅ {sym} {signal.upper()} LIMIT creado @ {entry:.2f} USDT\nSL {sl:.2f} | TP {tp:.2f} | Qty {quantity:.6f}"
            )

    async def procesar_par(self, sym: str):
        signal = await self.analizar_signal(sym)
        if signal:
            await self.ejecutar_trade(sym, signal)

    async def run_trading_loop(self):
        symbols = await self.fetch_all_usdt_symbols()
        logger.info("Símbolos a monitorear: %s", symbols)
        semaphore = asyncio.Semaphore(API_CONCURRENCY_LIMIT)

        async def sem_task(sym):
            async with semaphore:
                await self.procesar_par(sym)

        while not self._stop_event.is_set():
            self.last_loop_heartbeat = datetime.now(timezone.utc)
            try:
                self.state.reset_daily_if_needed()
            except Exception:
                logger.debug("StateManager.reset_daily_if_needed falló o no existe")

            if not getattr(self.state, "can_open_new_trade", lambda: True)() or len(getattr(self.state, "open_positions", {})) >= MAX_OPEN_TRADES:
                await asyncio.sleep(1)
                continue

            tasks = [asyncio.create_task(sem_task(sym)) for sym in symbols]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(0.5)  # loop rápido para scalping

# =========================== LOOP PRINCIPAL Y MONITORES ===========================

async def periodic_report(bot):
    while True:
        try:
            await asyncio.sleep(3600)
            open_syms = list(getattr(bot.state, "open_positions", {}).keys())
            pnl = getattr(bot.state, "realized_pnl_today", 0.0)
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            await bot.safe_send_telegram(
                f"🕒 Reporte horario {timestamp}\n"
                f"📌 Operaciones abiertas: {len(open_syms)}\n"
                f"📌 PnL diario: {pnl:.2f} USDT\n"
                f"📌 Símbolos monitoreados"
            )
        except Exception as e:
            await bot.safe_send_telegram(f"❌ Error en reporte horario: {e}")


async def monitor_positions(bot):
    while True:
        try:
            closed_positions = getattr(bot.state, "closed_positions_history", [])
            for pos in closed_positions:
                sym = pos.get("symbol")
                pnl = pos.get("pnl", 0.0)
                reason = pos.get("reason", "unknown")
                await bot.safe_send_telegram(f"📉 {sym} cerrada por {reason}. PnL: {pnl:.2f} USDT")
        except Exception as e:
            await bot.safe_send_telegram(f"❌ Error monitor_positions: {e}")
        await asyncio.sleep(5)


async def watchdog_loop(bot):
    while True:
        try:
            await asyncio.sleep(60)
            if (datetime.now(timezone.utc) - bot.last_loop_heartbeat) > timedelta(seconds=120):
                await bot.safe_send_telegram("⚠️ Alert: posible bloqueo del bot")
        except Exception as e:
            await bot.safe_send_telegram(f"❌ Error watchdog: {e}")


async def main():
    bot = CryptoBot()
    tasks = []
    try:
        await bot.safe_send_telegram("🚀 CryptoBot iniciado en TESTNET (limit-only orders, paralelos)")
        tasks.append(asyncio.create_task(periodic_report(bot)))
        tasks.append(asyncio.create_task(monitor_positions(bot)))
        tasks.append(asyncio.create_task(watchdog_loop(bot)))
        await bot.run_trading_loop()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado recibida")
        await bot.safe_send_telegram("⏹️ CryptoBot detenido manualmente")
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
