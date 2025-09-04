# unified_main.py
import asyncio
import logging
import pandas as pd
from src.state import bot_state
from src.state_manager import StateManager
from src.notifier.telegram_notifier import TelegramNotifier
from src.exchange.binance_client import BinanceClient
from src.pair_selector import PairSelector
from src.executor import Executor
from src.strategy.strategy import build_features

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar
state_manager = StateManager(daily_profit_target=50.0)
telegram = TelegramNotifier()
exchange = BinanceClient()  # Conectar a Binance real o sandbox según tu configuración
executor = Executor(exchange)
pair_selector = PairSelector(exchange)

# Parámetros
CAPITAL_TOTAL = 2000.0
RISK_PERCENT = 1.0
MAX_SIMULTANEOUS_TRADES = 5
WATCHLIST_DINAMICA = []

async def actualizar_watchlist():
    global WATCHLIST_DINAMICA
    # 1. Obtener todos los símbolos USDT-M
    symbols = await exchange.get_all_symbols()
    filtered = []

    for s in symbols:
        try:
            ticker = await exchange.fetch_ticker(s)
            vol = ticker['quoteVolume']
            if vol < 50_000_000:
                continue
            raw = await exchange.fetch_ohlcv(s, '15m', 100)
            df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
            df["atr"] = df["high"].rolling(14).max() - df["low"].rolling(14).min()
            atr_last = df["atr"].iloc[-1]
            price_last = df["close"].iloc[-1]
            if atr_last / price_last < 0.005:
                continue
            filtered.append((s, vol))
        except Exception:
            continue

    filtered.sort(key=lambda x: x[1], reverse=True)
    WATCHLIST_DINAMICA = [s for s, _ in filtered[:15]]
    await telegram.send_message(f"🔎 Watchlist actualizada: {WATCHLIST_DINAMICA}")

async def run_trading_loop():
    await actualizar_watchlist()
    logger.info("Entering trading loop")

    while True:
        if not state_manager.can_open_new_trade():
            await asyncio.sleep(60)
            continue

        for symbol in WATCHLIST_DINAMICA:
            if symbol in state_manager.open_positions:
                continue

            raw = await exchange.fetch_ohlcv(symbol, '1m', 200)
            if raw is None or len(raw) == 0:
                continue

            df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit='ms')

            try:
                features = build_features(df)
            except Exception:
                continue

            mom = features.get("mom", 0)
            rsi_centered = features.get("rsi_centered", 0)
            score = 1.0 if mom > 0 and rsi_centered > 0 else 0.0

            if score >= 1.0:
                side = "buy" if mom > 0 else "sell"
                size_usd = CAPITAL_TOTAL * RISK_PERCENT / 100
                current_price = df["close"].iloc[-1]
                await executor.open_position(symbol, side, size_usd, current_price)
                state_manager.register_open_position(symbol, side, current_price, size_usd, current_price*0.998, current_price*1.015)
                await telegram.send_message(f"{symbol} {side.upper()} abierto @ {current_price:.2f}")

        await asyncio.sleep(60)

async def main():
    await telegram.send_message("🚀 CryptoBot iniciado en TESTNET")
    await run_trading_loop()

if __name__ == "__main__":
    asyncio.run(main())
