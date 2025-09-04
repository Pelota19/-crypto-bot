"""
Unified CryptoBot para Binance Futures (USDT-M) - versión funcional
Incluye watchlist dinámica, scalping EMA+RSI y gestión de riesgo.
"""
import asyncio
import logging
from datetime import datetime, timedelta

import pandas as pd
import ccxt.async_support as ccxt
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator

from src.config import (
    API_KEY, API_SECRET, USE_TESTNET, POSITION_SIZE_PERCENT, MAX_OPEN_TRADES,
    DAILY_PROFIT_TARGET, CAPITAL_MAX_USDT, TIMEFRAME, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
from src.state import StateManager
from src.notifier.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ----- Instancias globales -----
state_manager = StateManager(daily_profit_target=DAILY_PROFIT_TARGET)
telegram = TelegramNotifier(telegram_token=TELEGRAM_BOT_TOKEN, chat_id=TELEGRAM_CHAT_ID)

# ----- Cliente Binance -----
class BinanceClient:
    def __init__(self, api_key, api_secret, testnet=False):
        opts = {'defaultType': 'future'}
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': opts,
        })
        if testnet:
            try:
                self.exchange.set_sandbox_mode(True)
                logger.info("Binance sandbox mode enabled")
            except Exception:
                logger.warning("No se pudo activar sandbox mode en ccxt")

    async def fetch_ohlcv(self, symbol, timeframe='1m', limit=200):
        try:
            return await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as e:
            logger.exception("fetch_ohlcv error: %s", e)
            return []

    async def fetch_balance(self):
        try:
            bal = await self.exchange.fetch_balance(params={"type": "future"})
            return bal
        except Exception as e:
            logger.exception("fetch_balance error: %s", e)
            return {}

    async def create_order(self, symbol, side, amount, price=None, order_type="market"):
        try:
            if order_type == "market":
                return await self.exchange.create_order(symbol, "market", side, amount)
            elif order_type == "limit":
                return await self.exchange.create_order(symbol, "limit", side, amount, price)
        except Exception as e:
            logger.exception("create_order failed: %s", e)
            return None

    async def close(self):
        try:
            await self.exchange.close()
        except Exception:
            pass

# ----- CryptoBot -----
class CryptoBot:
    def __init__(self):
        self.exchange = BinanceClient(API_KEY, API_SECRET, testnet=USE_TESTNET)
        self.watchlist = []
        self.max_active = MAX_OPEN_TRADES
        self.position_pct = POSITION_SIZE_PERCENT

    async def actualizar_watchlist(self):
        """Genera watchlist dinámica cada hora"""
        logger.info("Actualizando watchlist dinámica")
        markets = await self.exchange.exchange.fetch_markets()
        symbols = [m['symbol'] for m in markets if '/USDT' in m['symbol']]
        vol_filtered = []
        for sym in symbols:
            try:
                ticker = await self.exchange.exchange.fetch_ticker(sym)
                if ticker['quoteVolume'] >= 50_000_000:
                    vol_filtered.append(sym)
            except Exception:
                continue

        atr_filtered = []
        for sym in vol_filtered:
            raw = await self.exchange.fetch_ohlcv(sym, timeframe='15m', limit=15)
            if not raw:
                continue
            df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "vol"])
            df["atr"] = df["high"] - df["low"]
            atr = df["atr"].mean()
            close_price = df["close"].iloc[-1]
            if (atr / close_price) > 0.005:
                atr_filtered.append((sym, ticker['quoteVolume']))

        atr_filtered.sort(key=lambda x: x[1], reverse=True)
        self.watchlist = [s[0] for s in atr_filtered[:15]]
        await telegram.send_message(f"🔹 Watchlist actualizada: {self.watchlist}")

    async def calcular_señales(self, symbol):
        """Calcula EMA y RSI para el par"""
        raw_1m = await self.exchange.fetch_ohlcv(symbol, timeframe='1m', limit=50)
        raw_15m = await self.exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
        if not raw_1m or not raw_15m:
            return None
        df_1m = pd.DataFrame(raw_1m, columns=["ts","open","high","low","close","vol"])
        df_15m = pd.DataFrame(raw_15m, columns=["ts","open","high","low","close","vol"])
        close_1m = df_1m["close"]
        close_15m = df_15m["close"]

        ema9 = EMAIndicator(close_1m, window=9).ema_indicator()[-1]
        ema21 = EMAIndicator(close_1m, window=21).ema_indicator()[-1]
        ema50 = EMAIndicator(close_15m, window=50).ema_indicator()[-1]
        rsi = RSIIndicator(close_1m, window=14).rsi()[-1]
        price = close_1m.iloc[-1]

        if price > ema50 and ema9 > ema21 and rsi < 65:
            return "long", price
        elif price < ema50 and ema9 < ema21 and rsi > 35:
            return "short", price
        return None, price

    async def calcular_tamano(self, price):
        bal = await self.exchange.fetch_balance()
        usdt_balance = bal.get('USDT', {}).get('free', CAPITAL_MAX_USDT)
        riesgo_usdt = usdt_balance * self.position_pct
        return riesgo_usdt / price  # cantidad de la criptomoneda

    async def ejecutar_trade(self, symbol, side, price):
        cantidad = await self.calcular_tamano(price)
        # StopLoss y TP simples (ej: 0.2% SL, RRR 1.5)
        sl = price * (0.998 if side=="long" else 1.002)
        tp = price + (price - sl)*1.5 if side=="long" else price - (sl - price)*1.5
        order = await self.exchange.create_order(symbol, side, cantidad, price=price, order_type="market")
        state_manager.register_open_position(symbol, side, price, cantidad, sl, tp)
        await telegram.send_message(f"{symbol} {side.upper()} abierto @ {price:.2f} USDT")

    async def run_trading_loop(self):
        await self.actualizar_watchlist()
        while True:
            state_manager.reset_daily_if_needed()
            if not state_manager.can_open_new_trade():
                await asyncio.sleep(60)
                continue
            for sym in self.watchlist:
                if sym in state_manager.open_positions:
                    continue
                side, price = await self.calcular_señales(sym)
                if side:
                    await self.ejecutar_trade(sym, side, price)
                    if len(state_manager.open_positions) >= self.max_active:
                        break
            await asyncio.sleep(1)

    async def stop(self):
        await self.exchange.close()
        await telegram.send_message("⛔ CryptoBot detenido")

# ----- Main -----
async def main():
    bot = CryptoBot()
    await telegram.send_message("🚀 CryptoBot iniciado")
    try:
        await bot.run_trading_loop()
    except asyncio.CancelledError:
        await bot.stop()
    except Exception as e:
        logger.exception("Error en el trading loop: %s", e)
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
