"""
Unified CryptoBot - Binance Futures (USDT-M) - FULL SCAN con filtro de volatilidad
Estrategia: Scalping EMA/RSI con órdenes LIMIT + SL/TP limit.
- Analiza SOLO los pares USDT-M PERPETUAL con variación 24h > ±5%.
- Refresca la lista de símbolos cada N minutos (por defecto 10).
- Notifica por Telegram.
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
REFRESH_SYMBOLS_MINUTES = 10          # cada cuánto refrescar símbolos filtrados
TELEGRAM_MSG_MAX = 4000
VOLATILITY_THRESHOLD = 5.0            # % mínimo de variación 24h

class CryptoBot:
    def __init__(self):
        self.exchange = BinanceClient(
            api_key=API_KEY, api_secret=API_SECRET,
            use_testnet=USE_TESTNET, dry_run=False
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
                return
            if len(msg) > TELEGRAM_MSG_MAX:
                for i in range(0, len(msg), TELEGRAM_MSG_MAX):
                    await self.telegram.send_message(msg[i:i+TELEGRAM_MSG_MAX])
            else:
                await self.telegram.send_message(msg)
            self._telegram_fail_count = 0
        except Exception as e:
            self._telegram_fail_count += 1
            if self._telegram_fail_count >= self._telegram_fail_threshold:
                self._recent_telegram_disabled = True
            logger.warning("Telegram message failed: %s", e)

    async def refresh_symbols(self):
        """
        Trae TODOS los símbolos PERPETUAL USDT-M desde el exchange (testnet)
        y filtra por variación 24h mayor a ±VOLATILITY_THRESHOLD.
        """
        try:
            syms = await self.exchange.fetch_all_symbols()
            filtered = []
            for sym in syms:
                try:
                    ticker = await self.exchange.fetch_ticker(sym)
                    change = ticker.get("percentage")
                    if change is not None and abs(change) >= VOLATILITY_THRESHOLD:
                        filtered.append(sym)
                except Exception:
                    continue
            self.symbols = filtered
            logger.info("Símbolos filtrados (%d): %s", len(filtered), filtered)
            await self.safe_send_telegram(f"🔄 Lista de símbolos filtrada ({len(filtered)}): {filtered}")
        except Exception as e:
            logger.exception("Error refrescando símbolos: %s", e)
            await self.safe_send_telegram(f"❌ Error refrescando símbolos: {e}")

    # --- el resto de métodos: analizar_signal, ejecutar_trade, procesar_par, run_trading_loop ---
    # 🔥 permanecen exactamente igual que en tu versión actual 🔥

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
            return None
        except Exception:
            return None

    # ... ejecutar_trade, procesar_par, run_trading_loop se copian de tu archivo actual sin cambios ...

async def symbols_refresher(bot: CryptoBot):
    await bot.refresh_symbols()
    while True:
        await asyncio.sleep(REFRESH_SYMBOLS_MINUTES * 60)
        await bot.refresh_symbols()

async def main():
    bot = CryptoBot()
    tasks = []
    try:
        await bot.safe_send_telegram("🚀 CryptoBot iniciado en TESTNET (limit-only orders, filtrado ±5% 24h)")
        tasks.append(asyncio.create_task(symbols_refresher(bot)))
        tasks.append(asyncio.create_task(periodic_report(bot)))
        tasks.append(asyncio.create_task(monitor_positions(bot)))
        tasks.append(asyncio.create_task(watchdog_loop(bot)))
        await bot.run_trading_loop()
    except KeyboardInterrupt:
        await bot.safe_send_telegram("⏹️ CryptoBot detenido manualmente")
    except Exception as e:
        await bot.safe_send_telegram(f"❌ Error crítico en main: {e}")
    finally:
        for t in tasks:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
        await bot.exchange.close()
        await bot.telegram.close()

if __name__ == "__main__":
    asyncio.run(main())
