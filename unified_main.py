"""
Unified CryptoBot - Binance Futures (USDT-M)
Scalping EMA/RSI con gestión de riesgo estricta y Bracket orders.
Telegram actúa como consola de alertas y reportes.
Excepción SOL/USDT para abrir orden mínima si cumple estrategia.
Incluye monitor de cierres de posiciones y watchdog para alertas de fallas.
"""
import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta

from config import (
    API_KEY, API_SECRET, USE_TESTNET, POSITION_SIZE_PERCENT, MAX_OPEN_TRADES, DAILY_PROFIT_TARGET,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MAX_ACTIVE_SYMBOLS, MIN_NOTIONAL_USD, LEVERAGE
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
MAX_OPERATIONS_SIMULTANEAS = MAX_OPEN_TRADES
OBJETIVO_PROFIT_DIARIO = DAILY_PROFIT_TARGET
STOP_LOSS_PORCENTAJE = 0.2 / 100
RISK_REWARD_RATIO = 1.5

TIMEFRAME_SIGNAL = '1m'
TIMEFRAME_TENDENCIA = '15m'
WATCHLIST_DINAMICA = []

MAX_PRICE_PER_UNIT = 1000
MAX_TRADE_USDT = 50

class CryptoBot:
    def __init__(self):
        self.exchange = BinanceClient(
            api_key=API_KEY, api_secret=API_SECRET,
            use_testnet=USE_TESTNET, dry_run=False
        )
        self.telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        self.state = StateManager(daily_profit_target=OBJETIVO_PROFIT_DIARIO)
        self._stop_event = asyncio.Event()
        self.last_loop_heartbeat = datetime.utcnow()

    async def actualizar_watchlist(self):
        try:
            all_symbols = await self.exchange.fetch_all_symbols()
            filtered = []
            for sym in all_symbols:
                try:
                    ticker = await self.exchange.fetch_ticker(sym)
                    if not ticker:
                        continue
                    vol = float(ticker.get("quoteVolume") or ticker.get("info", {}).get("quoteVolume") or 0)
                    ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_TENDENCIA, limit=50)
                    if not ohlcv:
                        continue
                    df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                    price = float(df["close"].iloc[-1])
                    if price > MAX_PRICE_PER_UNIT:
                        continue
                    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().iloc[-1]
                    atr_rel = atr / price
                    if vol < 50_000_000 or price <= 0 or atr_rel < 0.005:
                        continue
                    filtered.append((sym, vol))
                except Exception:
                    continue
            filtered.sort(key=lambda x: x[1], reverse=True)
            global WATCHLIST_DINAMICA
            WATCHLIST_DINAMICA = [x[0] for x in filtered[:MAX_ACTIVE_SYMBOLS]]
            await self.telegram.send_message(f"📊 Watchlist actualizada: {WATCHLIST_DINAMICA}")
        except Exception as e:
            await self.telegram.send_message(f"❌ Error actualizando watchlist: {e}")

    async def analizar_signal(self, sym: str):
        try:
            ohlcv_1m = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_SIGNAL, limit=50)
            ohlcv_15m = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_TENDENCIA, limit=50)
            if not ohlcv_1m or not ohlcv_15m:
                return None
            df_1m = pd.DataFrame(ohlcv_1m, columns=["timestamp","open","high","low","close","volume"])
            df_15m = pd.DataFrame(ohlcv_15m, columns=["timestamp","open","high","low","close","volume"])
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
            await self.telegram.send_message(f"❌ Error analizando {sym}: {e}")
            return None
        return None

    async def ejecutar_trade(self, sym: str, signal: str):
        if sym in self.state.open_positions:
            return
        size_usdt = CAPITAL_TOTAL * POSITION_SIZE_PERCENT
        try:
            ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_SIGNAL, limit=1)
            if not ohlcv:
                await self.telegram.send_message(f"⚠️ No se pudo obtener precio para {sym}")
                return
            price = float(ohlcv[-1][4])
        except Exception as e:
            await self.telegram.send_message(f"❌ Error obteniendo precio para {sym}: {e}")
            return

        # Excepción SOL/USDT para abrir orden mínima
        min_notional = MIN_NOTIONAL_USD
        if sym == "SOL/USDT":
            min_notional = min(MIN_NOTIONAL_USD, 5)

        quantity = (size_usdt / price) * LEVERAGE
        notional = price * quantity
        if notional > MAX_TRADE_USDT:
            quantity = MAX_TRADE_USDT / price  # ajustar cantidad máxima
        if notional < min_notional:
            if sym != "SOL/USDT":
                await self.telegram.send_message(f"⚠️ Orden ignorada para {sym}: Notional {notional:.2f} < mínimo {min_notional}")
                return
            else:
                quantity = min_notional / price  # abrir mínima para SOL

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
            entry_order, stop_order, tp_order = await self.exchange.create_bracket_order(
                symbol=sym,
                side=side,
                quantity=quantity,
                entry_price=entry,
                stop_price=sl,
                take_profit_price=tp,
                wait_timeout=30
            )
            if entry_order:
                self.state.register_open_position(sym, signal, entry, quantity*price/LEVERAGE, sl, tp)
                await self.telegram.send_message(
                    f"✅ {sym} {signal.upper()} abierto @ {entry:.2f} USDT\nSL {sl:.2f} | TP {tp:.2f} | Cant {quantity:.6f}"
                )
            else:
                await self.telegram.send_message(f"❌ No se pudo abrir orden para {sym}")
        except Exception as e:
            await self.telegram.send_message(f"❌ Error al abrir {sym}: {e}")

    async def procesar_par(self, sym: str):
        signal = await self.analizar_signal(sym)
        if signal:
            await self.ejecutar_trade(sym, signal)

    async def run_trading_loop(self):
        while not self._stop_event.is_set():
            self.last_loop_heartbeat = datetime.utcnow()  # actualizamos heartbeat
            self.state.reset_daily_if_needed()
            if not self.state.can_open_new_trade() or len(self.state.open_positions) >= MAX_OPERATIONS_SIMULTANEAS:
                await asyncio.sleep(60)
                continue
            tasks = [self.procesar_par(sym) for sym in WATCHLIST_DINAMICA]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(1)

async def periodic_report(bot):
    while True:
        try:
            await asyncio.sleep(3600)  # cada 1 hora
            open_syms = list(bot.state.open_positions.keys())
            pnl = getattr(bot.state, "realized_pnl_today", 0.0)
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            await bot.telegram.send_message(
                f"🕒 Reporte horario {timestamp}\n"
                f"📌 Operaciones abiertas: {len(open_syms)}\n"
                f"📌 PnL diario: {pnl:.2f} USDT\n"
                f"📌 Watchlist: {WATCHLIST_DINAMICA}"
            )
        except Exception as e:
            await bot.telegram.send_message(f"❌ Error en reporte horario: {e}")

async def monitor_positions(bot):
    """Monitorea cierres de posiciones y envía mensajes a Telegram"""
    while True:
        try:
            closed_positions = bot.state.check_positions_closed()
            for pos in closed_positions:
                sym = pos["symbol"]
                pnl = pos["pnl"]
                reason = pos["reason"]  # 'SL' o 'TP'
                await bot.telegram.send_message(f"📉 {sym} cerrada por {reason}. PnL: {pnl:.2f} USDT")
        except Exception as e:
            await bot.telegram.send_message(f"❌ Error en monitor_positions: {e}")
        await asyncio.sleep(5)

async def watchdog_loop(bot):
    """Detecta si el bot se traba o se detiene"""
    while True:
        try:
            await asyncio.sleep(60)
            if (datetime.utcnow() - bot.last_loop_heartbeat) > timedelta(seconds=120):
                await bot.telegram.send_message("⚠️ Alert: posible bloqueo del bot")
        except Exception as e:
            await bot.telegram.send_message(f"❌ Error en watchdog: {e}")

async def main():
    bot = CryptoBot()
    tasks = []
    try:
        await bot.telegram.send_message("🚀 CryptoBot iniciado en TESTNET")
        await bot.actualizar_watchlist()
        tasks.append(asyncio.create_task(periodic_report(bot)))
        tasks.append(asyncio.create_task(monitor_positions(bot)))
        tasks.append(asyncio.create_task(watchdog_loop(bot)))
        await bot.run_trading_loop()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado recibida")
        await bot.telegram.send_message("⏹️ CryptoBot detenido manualmente")
    except Exception as e:
        logger.exception("Error crítico en main: %s", e)
        await bot.telegram.send_message(f"❌ Error crítico en main: {e}")
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
