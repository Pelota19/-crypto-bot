"""
Unified CryptoBot - Binance Futures (USDT-M) - FULL SCAN (sin watchlist)
Estrategia: Scalping EMA/RSI con órdenes LIMIT + SL/TP limit.
- Analiza TODOS los pares USDT-M PERPETUAL (testnet) en bucle.
- Refresca la lista de símbolos cada N minutos (por defecto 10).
- Notifica por Telegram.

Requisitos:
- config.py con: API_KEY, API_SECRET, USE_TESTNET, POSITION_SIZE_PERCENT,
  MAX_OPEN_TRADES, DAILY_PROFIT_TARGET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
  MIN_NOTIONAL_USD, LEVERAGE
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
REFRESH_SYMBOLS_MINUTES = 10          # cada cuánto refrescar TODOS los símbolos
TELEGRAM_MSG_MAX = 4000

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
        # protección fallos Telegram
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
                logger.error("Telegram failing %d times, disabling temporarily", self._telegram_fail_count)
                self._recent_telegram_disabled = True

    async def refresh_symbols(self):
        """
        Trae TODOS los símbolos PERPETUAL USDT-M desde el exchange (testnet).
        """
        try:
            syms = await self.exchange.fetch_all_symbols()
            self.symbols = syms
            logger.info("Símbolos (full-scan): %s", syms)
            await self.safe_send_telegram(f"🔄 Lista de símbolos refrescada ({len(syms)}): {syms}")
        except Exception as e:
            logger.exception("Error refrescando símbolos: %s", e)
            await self.safe_send_telegram(f"❌ Error refrescando símbolos: {e}")

    async def _create_bracket_order(self, symbol: str, side: str, quantity: float,
                                    entry_price: float, stop_price: float, take_profit_price: float,
                                    wait_timeout: int = 30) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
        """
        Flujo limit-only:
        - Entrada LIMIT (GTC)
        - SL: stop-limit (reduceOnly)
        - TP: take-profit-limit (reduceOnly)
        """
        # Fallback simple con create_order
        entry_order = None
        stop_order = None
        tp_order = None
        close_side = "SELL" if side.upper() == "BUY" else "BUY"

        # 1) Entrada LIMIT
        try:
            params_entry = {"timeInForce": "GTC"}
            entry_order = await self.exchange.create_order(symbol, "limit", side, quantity, entry_price, params_entry)
            logger.info("LIMIT entry creada %s: %s", symbol, entry_order)
        except Exception as e:
            logger.error("Fallo creando LIMIT de entrada %s @%s: %s", symbol, entry_price, e)
            raise Exception(f"No se pudo crear orden LIMIT de entrada para {symbol}: {e}") from e

        # 2) SL stop-limit
        try:
            params_sl = {"stopPrice": stop_price, "reduceOnly": True, "timeInForce": "GTC"}
            try:
                stop_order = await self.exchange.create_order(symbol, "stop_limit", close_side, quantity, stop_price, params_sl)
            except Exception:
                stop_order = await self.exchange.create_order(symbol, "STOP_LIMIT", close_side, quantity, stop_price, params_sl)
            logger.info("SL stop-limit creado %s: %s", symbol, stop_order)
        except Exception as e:
            logger.warning("Crear SL (stop-limit) falló para %s: %s", symbol, e)

        # 3) TP take-profit-limit
        try:
            params_tp = {"stopPrice": take_profit_price, "reduceOnly": True, "timeInForce": "GTC"}
            try:
                tp_order = await self.exchange.create_order(symbol, "take_profit_limit", close_side, quantity, take_profit_price, params_tp)
            except Exception:
                tp_order = await self.exchange.create_order(symbol, "TAKE_PROFIT_LIMIT", close_side, quantity, take_profit_price, params_tp)
            logger.info("TP take-profit-limit creado %s: %s", symbol, tp_order)
        except Exception as e:
            logger.warning("Crear TP (take-profit limit) falló para %s: %s", symbol, e)

        return entry_order, stop_order, tp_order

    async def analizar_signal(self, sym: str) -> Optional[str]:
        """
        Señal simple:
        - Tendencia por EMA50 en 15m
        - Cruce EMA9/EMA21 en 1m
        - RSI 1m con filtros de sobrecompra/sobreventa suaves
        """
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

            # Long si: tendencia alcista + cruce alcista + RSI no sobrecomprado
            if price > ema50_15m and ema9 > ema21 and rsi14 < 65:
                return "long"

            # Short si: tendencia bajista + cruce bajista + RSI no sobrevendido
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

        # precio actual vía OHLCV último close 1m
        try:
            ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_SIGNAL, limit=1)
            if not ohlcv:
                await self.safe_send_telegram(f"⚠️ No se pudo obtener precio para {sym}")
                return
            price = float(ohlcv[-1][4])
        except Exception as e:
            await self.safe_send_telegram(f"❌ Error obteniendo precio para {sym}: {e}")
            return

        # Notional con tope y mínimo
        min_notional = MIN_NOTIONAL_USD
        quantity = (size_usdt / price)
        notional = price * quantity
        if notional > MAX_TRADE_USDT:
            quantity = MAX_TRADE_USDT / price
            notional = MAX_TRADE_USDT
        if notional < min_notional:
            # opcional: saltar símbolos con notional demasiado bajo
            await self.safe_send_telegram(f"⚠️ Orden ignorada {sym}: Notional {notional:.2f} < min {min_notional}")
            return

        # Aplicar leverage
        quantity *= LEVERAGE

        # Niveles
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
            entry_order, stop_order, tp_order = await self._create_bracket_order(
                symbol=sym,
                side=side,
                quantity=quantity,
                entry_price=entry,
                stop_price=sl,
                take_profit_price=tp,
                wait_timeout=30
            )
            if entry_order:
                # Registrar posición (usa notional pre-leverage si tu StateManager lo espera así)
                self.state.register_open_position(sym, signal, entry, (quantity / LEVERAGE) * price, sl, tp)
                await self.safe_send_telegram(
                    f"✅ {sym} {signal.upper()} LIMIT @ {entry:.4f}\n"
                    f"SL {sl:.4f} | TP {tp:.4f} | Qty {quantity:.6f}"
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
        """
        Bucle principal:
        - analiza todos los símbolos disponibles
        - respeta MAX_OPEN_TRADES
        """
        while not self._stop_event.is_set():
            self.last_loop_heartbeat = datetime.now(timezone.utc)
            try:
                self.state.reset_daily_if_needed()
            except Exception:
                logger.debug("StateManager.reset_daily_if_needed missing or failed", exc_info=True)

            # respetar límites de operaciones
            if (not getattr(self.state, "can_open_new_trade", lambda: True)()) or \
               (len(getattr(self.state, "open_positions", {})) >= MAX_OPERATIONS_SIMULTANEAS):
                await asyncio.sleep(5)
                continue

            # si no hay símbolos aún, espera breve
            if not self.symbols:
                await asyncio.sleep(2)
                continue

            # procesar todos en paralelo (concurrency moderada para no saturar)
            # chunk pequeño para evitar rate limits
            CHUNK = 8
            for i in range(0, len(self.symbols), CHUNK):
                batch = self.symbols[i:i+CHUNK]
                tasks = [self.procesar_par(sym) for sym in batch]
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(0.5)  # pequeña pausa entre tandas

            await asyncio.sleep(1)

async def periodic_report(bot: CryptoBot):
    while True:
        try:
            await asyncio.sleep(3600)
            open_syms = list(getattr(bot.state, "open_positions", {}).keys())
            pnl = getattr(bot.state, "realized_pnl_today", 0.0)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            await bot.safe_send_telegram(
                f"🕒 Reporte horario {ts}\n"
                f"📌 Operaciones abiertas: {len(open_syms)}\n"
                f"📌 PnL diario: {pnl:.2f} USDT\n"
                f"📌 Símbolos escaneados: {len(bot.symbols)}"
            )
        except Exception as e:
            await bot.safe_send_telegram(f"❌ Error en reporte horario: {e}")

async def monitor_positions(bot: CryptoBot):
    """
    Stub básico: si tu StateManager soporta reconciliación, conéctalo aquí.
    """
    while True:
        try:
            closed_positions = []
            if hasattr(bot.state, "check_positions_closed") and callable(getattr(bot.state, "check_positions_closed")):
                closed_positions = bot.state.check_positions_closed()
            elif hasattr(bot.state, "get_closed_positions") and callable(getattr(bot.state, "get_closed_positions")):
                closed_positions = bot.state.get_closed_positions()
            else:
                closed_positions = getattr(bot.state, "closed_positions_history", [])

            for pos in closed_positions or []:
                try:
                    sym = pos.get("symbol")
                    pnl = pos.get("pnl", 0.0)
                    reason = pos.get("reason", "unknown")
                    await bot.safe_send_telegram(f"📉 {sym} cerrada por {reason}. PnL: {pnl:.2f} USDT")
                except Exception:
                    logger.debug("Posición cerrada con formato inesperado: %s", pos)
                    continue
        except Exception as e:
            await bot.safe_send_telegram(f"❌ Error monitor_positions: {e}")
        await asyncio.sleep(5)

async def watchdog_loop(bot: CryptoBot):
    while True:
        try:
            await asyncio.sleep(60)
            if (datetime.now(timezone.utc) - bot.last_loop_heartbeat) > timedelta(seconds=120):
                await bot.safe_send_telegram("⚠️ Alert: posible bloqueo del bot")
        except Exception as e:
            await bot.safe_send_telegram(f"❌ Error watchdog: {e}")

async def symbols_refresher(bot: CryptoBot):
    """
    Tarea de fondo que refresca la lista de símbolos cada REFRESH_SYMBOLS_MINUTES.
    """
    await bot.refresh_symbols()  # primer load inmediato
    while True:
        await asyncio.sleep(REFRESH_SYMBOLS_MINUTES * 60)
        await bot.refresh_symbols()

async def main():
    bot = CryptoBot()
    tasks = []
    try:
        await bot.safe_send_telegram("🚀 CryptoBot iniciado en TESTNET (limit-only orders, full-scan PERPETUAL USDT-M)")
        # Lanzar tareas de fondo
        tasks.append(asyncio.create_task(symbols_refresher(bot)))
        tasks.append(asyncio.create_task(periodic_report(bot)))
        tasks.append(asyncio.create_task(monitor_positions(bot)))
        tasks.append(asyncio.create_task(watchdog_loop(bot)))
        # Loop principal
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
