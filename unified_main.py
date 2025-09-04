# unified_main.py
import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta
from src.state_manager import StateManager
from src.notifier.telegram_notifier import TelegramNotifier
from src.exchange.binance_client import BinanceClient
from src.executor import Executor
from src.strategy.strategy import build_features
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializaciones
state_manager = StateManager(daily_profit_target=50.0)
telegram = TelegramNotifier()
exchange = BinanceClient(use_testnet=True)
executor = Executor(exchange)
CAPITAL_TOTAL = 2000.0
RISK_PERCENT = 1.0
MAX_SIMULTANEOUS_TRADES = 5
WATCHLIST_DINAMICA = []

TF_SIGNAL = '1m'
TF_TREND = '15m'

async def actualizar_watchlist():
    global WATCHLIST_DINAMICA
    try:
        symbols = await exchange.get_all_symbols()
        filtered = []

        for s in symbols:
            ticker = await exchange.fetch_ticker(s)
            vol = ticker['quoteVolume']
            if vol < 50_000_000:
                continue
            raw = await exchange.fetch_ohlcv(s, TF_TREND, 100)
            df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
            df["atr"] = df["high"].rolling(14).max() - df["low"].rolling(14).min()
            atr_last = df["atr"].iloc[-1]
            price_last = df["close"].iloc[-1]
            if atr_last / price_last < 0.005:
                continue
            filtered.append((s, vol))

        filtered.sort(key=lambda x: x[1], reverse=True)
        WATCHLIST_DINAMICA = [s for s, _ in filtered[:15]]
        await telegram.send_message(f"🔎 Watchlist actualizada: {WATCHLIST_DINAMICA}")
        logger.info(f"Watchlist actualizada: {WATCHLIST_DINAMICA}")
    except Exception as e:
        logger.exception("Error actualizando watchlist: %s", e)

async def analizar_señal(symbol):
    try:
        raw_1m = await exchange.fetch_ohlcv(symbol, TF_SIGNAL, 200)
        raw_15m = await exchange.fetch_ohlcv(symbol, TF_TREND, 200)
        df_1m = pd.DataFrame(raw_1m, columns=["timestamp","open","high","low","close","volume"])
        df_15m = pd.DataFrame(raw_15m, columns=["timestamp","open","high","low","close","volume"])
        precio_actual = df_1m["close"].iloc[-1]

        # Indicadores
        ema9 = EMAIndicator(df_1m["close"], 9).ema_indicator() 
        ema21 = EMAIndicator(df_1m["close"], 21).ema_indicator()
        ema50_15m = EMAIndicator(df_15m["close"], 50).ema_indicator()
        rsi14 = RSIIndicator(df_1m["close"], 14).rsi()

        signal_long = (precio_actual > ema50_15m.iloc[-1]) and (ema9.iloc[-2] < ema21.iloc[-2] and ema9.iloc[-1] > ema21.iloc[-1]) and (rsi14.iloc[-1] < 65)
        signal_short = (precio_actual < ema50_15m.iloc[-1]) and (ema9.iloc[-2] > ema21.iloc[-2] and ema9.iloc[-1] < ema21.iloc[-1]) and (rsi14.iloc[-1] > 35)

        if signal_long:
            return "buy", precio_actual
        elif signal_short:
            return "sell", precio_actual
        return None, precio_actual
    except Exception as e:
        logger.exception("Error analizando señal %s: %s", symbol, e)
        return None, None

async def run_trading_loop():
    # Actualizar watchlist al inicio y cada hora
    await actualizar_watchlist()
    last_watchlist_update = datetime.utcnow()

    while True:
        # Actualizar watchlist cada 1 hora
        if datetime.utcnow() - last_watchlist_update > timedelta(hours=1):
            await actualizar_watchlist()
            last_watchlist_update = datetime.utcnow()

        # Revisión de objetivos y concurrencia
        if not state_manager.can_open_new_trade():
            await asyncio.sleep(60)
            continue

        for symbol in WATCHLIST_DINAMICA:
            if len(state_manager.open_positions) >= MAX_SIMULTANEOUS_TRADES:
                break
            if symbol in state_manager.open_positions:
                continue

            side, precio_actual = await analizar_señal(symbol)
            if side is None:
                continue

            # Calcular tamaño y precios
            risk_usdt = CAPITAL_TOTAL * RISK_PERCENT / 100
            stop_loss_price = precio_actual * (0.998 if side=="buy" else 1.002)
            take_profit_price = precio_actual * (1.015 if side=="buy" else 0.985)

            # Ejecutar orden
            await executor.open_position(symbol, side, risk_usdt, precio_actual)
            state_manager.register_open_position(symbol, side, precio_actual, risk_usdt, stop_loss_price, take_profit_price)
            await telegram.send_message(f"{symbol} {side.upper()} abierto @ {precio_actual:.2f} | SL {stop_loss_price:.2f} TP {take_profit_price:.2f}")

        await asyncio.sleep(30)

async def main():
    await telegram.send_message("🚀 CryptoBot iniciado en TESTNET")
    try:
        await run_trading_loop()
    except Exception as e:
        logger.exception("Error en trading loop: %s", e)
    finally:
        await exchange.close()
        logger.info("CryptoBot detenido")

if __name__ == "__main__":
    asyncio.run(main())
