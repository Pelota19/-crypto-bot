"""
Unified CryptoBot - Binance Futures (USDT-M)
Ejecución real o sandbox según configuración.
Scalping EMA/RSI con gestión de riesgo estricta y Bracket orders (entrada LIMIT post-only, SL + TP).
"""
import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta

from config import (
    API_KEY, API_SECRET, USE_TESTNET, POSITION_SIZE_PERCENT, MAX_OPEN_TRADES, DAILY_PROFIT_TARGET,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MAX_ACTIVE_SYMBOLS, MIN_NOTIONAL_USD
)

from src.exchange.binance_client import BinanceClient
from src.notifier.telegram_notifier import TelegramNotifier
from src.state import StateManager
from ta.volatility import AverageTrueRange
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

# Logging básico
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

class CryptoBot:
    def __init__(self):
        self.exchange = BinanceClient(
            api_key=API_KEY, api_secret=API_SECRET,
            use_testnet=USE_TESTNET, dry_run=False
        )
        self.telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        self.state = StateManager(daily_profit_target=OBJETIVO_PROFIT_DIARIO)
        self._stop_event = asyncio.Event()

    async def actualizar_watchlist(self):
        """Actualiza la watchlist dinámica cada hora con manejo robusto de símbolos inválidos."""
        logger.info("Iniciando scan de mercado para actualizar watchlist...")
        all_symbols = await self.exchange.fetch_all_symbols()
        filtered = []
        for sym in all_symbols:
            try:
                ticker = await self.exchange.fetch_ticker(sym)
                if not ticker:
                    continue
                vol = ticker.get("quoteVolume") or ticker.get("info", {}).get("quoteVolume") or 0
                try:
                    vol = float(vol)
                except Exception:
                    vol = 0.0
                if vol < 50_000_000:
                    continue
                ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_TENDENCIA, limit=50)
                if not ohlcv:
                    continue
                df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
                try:
                    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().iloc[-1]
                except Exception:
                    continue
                price = float(df['close'].iloc[-1])
                if price <= 0:
                    continue
                atr_rel = atr / price
                if atr_rel < 0.005:
                    continue
                filtered.append((sym, vol))
            except Exception as e:
                logger.debug("Skip symbol %s due to error: %s", sym, e)
                continue

        filtered.sort(key=lambda x: x[1], reverse=True)
        global WATCHLIST_DINAMICA
        WATCHLIST_DINAMICA = [x[0] for x in filtered[:MAX_ACTIVE_SYMBOLS]]
        logger.info("Watchlist actualizada (%d): %s", len(WATCHLIST_DINAMICA), WATCHLIST_DINAMICA)
        await self.telegram.send_message(f"📊 Watchlist actualizada: {WATCHLIST_DINAMICA}")

    async def analizar_signal(self, sym: str):
        """Calcula indicadores EMA y RSI para generar señal LONG/SHORT."""
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

            # LONG
            if price > ema50_15m and ema9 > ema21 and rsi14 < 65:
                return "long"
            # SHORT
            if price < ema50_15m and ema9 < ema21 and rsi14 > 35:
                return "short"
        except Exception as e:
            logger.debug("analizar_signal error for %s: %s", sym, e)
            return None
        return None

    async def ejecutar_trade(self, sym: str, signal: str):
        """Calcula tamaño, SL, TP y abre posición usando create_bracket_order."""
        if sym in self.state.open_positions:
            logger.debug("Ya existe posición en %s, saltando", sym)
            return
        # Calculo del tamaño en USDT arriesgando POSITION_SIZE_PERCENT del capital
        size_usdt = CAPITAL_TOTAL * POSITION_SIZE_PERCENT
        try:
            ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_SIGNAL, limit=1)
            if not ohlcv:
                return
            price = float(ohlcv[-1][4])
        except Exception as e:
            logger.debug("No se pudo obtener precio para %s: %s", sym, e)
            return

        # convertir size_usdt a cantidad en base asset (quantity)
        try:
            quantity = size_usdt / price
            # opcional: ajustar por min_notional o step size según exchange (a futuro)
        except Exception as e:
            logger.debug("Error calculando quantity para %s: %s", sym, e)
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

        # Asegurarse que la posición no sea demasiado pequeña por notional
        notional = entry * quantity
        if notional < MIN_NOTIONAL_USD:
            logger.info("Notional demasiado pequeño para %s: %f USDT (min %f)", sym, notional, MIN_NOTIONAL_USD)
            return

        # Intentar crear bracket (entrada LIMIT post-only, esperar fill, colocar SL+TP)
        try:
            entry_order, stop_order, tp_order = await self.exchange.create_bracket_order(
                symbol=sym,
                side=side,
                quantity=quantity,
                entry_price=entry,
                stop_price=sl,
                take_profit_price=tp,
                wait_timeout=30  # segundos para esperar fill (ajustable)
            )
            # Registrar en estado si la entrada fue colocada/ejecutada
            self.state.register_open_position(sym, signal, entry, size_usdt, sl, tp)
            await self.telegram.send_message(f"{sym} {signal.upper()} abierto @ {entry:.2f} USDT, SL {sl:.2f}, TP {tp:.2f}")
        except Exception as e:
            logger.exception("Failed to place bracket for %s: %s", sym, e)
            await self.telegram.send_message(f"❌ Error al abrir {sym}: {e}")

    async def run_trading_loop(self):
        while not self._stop_event.is_set():
            self.state.reset_daily_if_needed()
            if not self.state.can_open_new_trade() or len(self.state.open_positions) >= MAX_OPERATIONS_SIMULTANEAS:
                await asyncio.sleep(60)
                continue
            tasks = [self.procesar_par(sym) for sym in WATCHLIST_DINAMICA]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(1)

    async def procesar_par(self, sym: str):
        signal = await self.analizar_signal(sym)
        if signal:
            await self.ejecutar_trade(sym, signal)


async def periodic_watchlist(bot):
    while True:
        await asyncio.sleep(3600)
        await bot.actualizar_watchlist()
        open_syms = list(bot.state.open_positions.keys())
        pnl = getattr(bot.state, "realized_pnl_today", 0.0)
        await bot.telegram.send_message(f"📈 Estado horario: {len(open_syms)} operaciones abiertas, PnL diario: {pnl:.2f} USDT")


async def main():
    bot = CryptoBot()
    periodic_task = None
    try:
        await bot.telegram.send_message("🚀 CryptoBot iniciado en TESTNET")
        await bot.actualizar_watchlist()
        periodic_task = asyncio.create_task(periodic_watchlist(bot))
        await bot.run_trading_loop()
    except KeyboardInterrupt:
        logger.info("Interrupción por teclado recibida")
    except Exception as e:
        logger.exception("Error crítico en main: %s", e)
    finally:
        if periodic_task:
            periodic_task.cancel()
            try:
                await periodic_task
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
