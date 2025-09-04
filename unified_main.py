"""
Unified CryptoBot - Binance Futures (USDT-M)
Ejecución real o sandbox según configuración.
Scalping EMA/RSI con gestión de riesgo estricta y OCO.
"""
import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta

from config import (
    API_KEY, API_SECRET, USE_TESTNET, POSITION_SIZE_PERCENT, MAX_OPEN_TRADES, DAILY_PROFIT_TARGET_USD,
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
OBJETIVO_PROFIT_DIARIO = DAILY_PROFIT_TARGET_USD
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
        """Actualiza la watchlist dinámica cada hora."""
        all_symbols = await self.exchange.fetch_all_symbols()
        filtered = []
        for sym in all_symbols:
            ticker = await self.exchange.fetch_ticker(sym)
            if not ticker or ticker['quoteVolume'] < 50_000_000:
                continue
            ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_TENDENCIA, limit=50)
            if not ohlcv:
                continue
            df = pd.DataFrame(ohlcv, columns=["timestamp","open","high","low","close","volume"])
            atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().iloc[-1]
            atr_rel = atr / df['close'].iloc[-1]
            if atr_rel < 0.005:
                continue
            filtered.append((sym, ticker['quoteVolume']))
        filtered.sort(key=lambda x: x[1], reverse=True)
        global WATCHLIST_DINAMICA
        WATCHLIST_DINAMICA = [x[0] for x in filtered[:MAX_ACTIVE_SYMBOLS]]
        await self.telegram.send_message(f"📊 Watchlist actualizada: {WATCHLIST_DINAMICA}")

    async def analizar_signal(self, sym: str):
        """Calcula indicadores EMA y RSI para generar señal LONG/SHORT."""
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
        price = df_1m["close"].iloc[-1]

        # LONG
        if price > ema50_15m and ema9 > ema21 and rsi14 < 65:
            return "long"
        # SHORT
        if price < ema50_15m and ema9 < ema21 and rsi14 > 35:
            return "short"
        return None

    async def ejecutar_trade(self, sym: str, signal: str):
        """Calcula tamaño, SL, TP y abre posición OCO."""
        if sym in self.state.open_positions:
            return
        size_usdt = CAPITAL_TOTAL * POSITION_SIZE_PERCENT
        ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_SIGNAL, limit=1)
        price = ohlcv[-1][4]
        if signal == "long":
            entry = price
            sl = entry * (1 - STOP_LOSS_PORCENTAJE)
            tp = entry + (entry - sl) * RISK_REWARD_RATIO
        elif signal == "short":
            entry = price
            sl = entry * (1 + STOP_LOSS_PORCENTAJE)
            tp = entry - (sl - entry) * RISK_REWARD_RATIO
        else:
            return
        # Crear OCO (Stop + Take Profit)
        await self.exchange.create_oco_order(
            symbol=sym,
            side="BUY" if signal=="long" else "SELL",
            quantity=size_usdt,
            stop_price=sl,
            take_profit_price=tp
        )
        self.state.register_open_position(sym, signal, entry, size_usdt, sl, tp)
        await self.telegram.send_message(f"{sym} {signal.upper()} abierto @ {entry:.2f} USDT, SL {sl:.2f}, TP {tp:.2f}")

    async def run_trading_loop(self):
        while not self._stop_event.is_set():
            self.state.reset_daily_if_needed()
            if not self.state.can_open_new_trade() or len(self.state.open_positions) >= MAX_OPERATIONS_SIMULTANEAS:
                await asyncio.sleep(60)
                continue
            tasks = [self.procesar_par(sym) for sym in WATCHLIST_DINAMICA]
            await asyncio.gather(*tasks)
            await asyncio.sleep(1)

    async def procesar_par(self, sym: str):
        signal = await self.analizar_signal(sym)
        if signal:
            await self.ejecutar_trade(sym, signal)

async def periodic_watchlist(bot):
    while True:
        await asyncio.sleep(3600)
        await bot.actualizar_watchlist()
        # resumen de estado
        open_syms = list(bot.state.open_positions.keys())
        pnl = bot.state.realized_pnl_today
        await bot.telegram.send_message(f"📈 Estado horario: {len(open_syms)} operaciones abiertas, PnL diario: {pnl:.2f} USDT")

async def main():
    bot = CryptoBot()
    await bot.telegram.send_message("🚀 CryptoBot iniciado en TESTNET")
    await bot.actualizar_watchlist()
    asyncio.create_task(periodic_watchlist(bot))
    await bot.run_trading_loop()

if __name__ == "__main__":
    asyncio.run(main())
