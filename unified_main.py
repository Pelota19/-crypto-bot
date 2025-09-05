"""
Unified CryptoBot - Binance Futures (USDT-M)
Scalping EMA/RSI con gestión de riesgo estricta y Bracket orders.
Telegram actúa como consola de alertas y reportes.
Excepción SOL/USDT para abrir orden mínima si cumple estrategia.
Incluye monitor de cierres de posiciones y watchdog para alertas de fallas.

Modificación: entrada SOLO con órdenes LIMIT y SL/TP configuradas como stop-limit / take-profit-limit.
Se añadió fallback robusto cuando el cliente exchange devuelve errores (símbolos inválidos).
"""
import asyncio
import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Any

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
TELEGRAM_MSG_MAX = 4000  # límite seguro Telegram


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
        # Telegram failure protection
        self._telegram_fail_count = 0
        self._telegram_fail_threshold = 5
        self._recent_telegram_disabled = False

    async def safe_send_telegram(self, msg: str):
        """Envía mensaje a Telegram, corta si demasiado largo.
        Añade protección contra fallos repetidos (400) para evitar spam de errores."""
        try:
            if getattr(self, "_recent_telegram_disabled", False):
                logger.warning("Telegram disabled due to repeated failures; skipping message")
                return
            if len(msg) > TELEGRAM_MSG_MAX:
                for i in range(0, len(msg), TELEGRAM_MSG_MAX):
                    await self.telegram.send_message(msg[i:i+TELEGRAM_MSG_MAX])
            else:
                await self.telegram.send_message(msg)
            # envío exitoso -> reset contador
            self._telegram_fail_count = 0
        except Exception as e:
            # registrar excepción completa en logs para diagnóstico
            logger.warning("Telegram message failed: %s", e)
            self._telegram_fail_count = getattr(self, "_telegram_fail_count", 0) + 1
            if self._telegram_fail_count >= getattr(self, "_telegram_fail_threshold", 5):
                logger.error(
                    "Telegram failing %d times consecutivas, desactivando envíos temporalmente",
                    self._telegram_fail_count
                )
                self._recent_telegram_disabled = True
            # no relanzamos la excepción para no romper loops

    async def actualizar_watchlist(self):
        """
        Construye watchlist usando fetch_all_symbols (compatible con BinanceClient).
        - Filtra por símbolos que terminen en '/USDT'
        - Evita símbolos que devuelvan errores al pedir OHLCV/ticker (serán ignorados)
        """
        try:
            all_symbols = await self.exchange.fetch_all_symbols()
            candidates: List[str] = []

            for sym in all_symbols:
                try:
                    if not isinstance(sym, str):
                        continue
                    if not sym.upper().endswith("/USDT"):
                        continue
                    candidates.append(sym)
                except Exception:
                    continue

            filtered = []
            for sym in candidates:
                try:
                    ticker = await self.exchange.fetch_ticker(sym)
                    if not ticker:
                        continue
                    vol = float(ticker.get("quoteVolume") or ticker.get("info", {}).get("quoteVolume") or 0)
                    ohlcv = await self.exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_TENDENCIA, limit=50)
                    if not ohlcv:
                        continue
                    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    price = float(df["close"].iloc[-1])
                    if price > MAX_PRICE_PER_UNIT:
                        continue
                    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().iloc[-1]
                    atr_rel = atr / price
                    if vol < 50_000_000 or price <= 0 or atr_rel < 0.005:
                        continue
                    filtered.append((sym, vol))
                except Exception as e:
                    msg = str(e)
                    if "Invalid symbol status" in msg or "Invalid symbol" in msg:
                        logger.info("Symbol %s tiene estado inválido, se ignorará: %s", sym, msg)
                        continue
                    logger.debug("Error validando símbolo %s: %s", sym, e)
                    continue

            filtered.sort(key=lambda x: x[1], reverse=True)
            global WATCHLIST_DINAMICA
            WATCHLIST_DINAMICA = [x[0] for x in filtered[:MAX_ACTIVE_SYMBOLS]]
            await self.safe_send_telegram(f"📊 Watchlist actualizada: {WATCHLIST_DINAMICA}")
        except Exception as e:
            await self.safe_send_telegram(f"❌ Error actualizando watchlist: {e}")

    async def analizar_signal(self, sym: str):
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
                try:
                    if sym in WATCHLIST_DINAMICA:
                        WATCHLIST_DINAMICA.remove(sym)
                        logger.info("Removed %s from watchlist due to invalid status", sym)
                        await self.safe_send_telegram(f"⚠️ {sym} removido de watchlist: estado inválido en exchange")
                except Exception:
                    logger.debug("Error removiendo símbolo problemático %s", sym)
                return None
            await self.safe_send_telegram(f"❌ Error analizando {sym}: {e}")
            return None
        return None

    async def _create_bracket_order(self, symbol: str, side: str, quantity: float,
                                    entry_price: float, stop_price: float, take_profit_price: float,
                                    wait_timeout: int = 30) -> Tuple[Optional[Any], Optional[Any], Optional[Any]]:
        """
        Limit-only flow:
        - Create LIMIT entry order (GTC).
        - Create stop-limit (SL) and take-profit-limit (TP) orders using common variants.
        Note: Limit entry may not fill immediately. Ensure monitor/reconciler is enabled to track fills.
        """
        # If client has native create_bracket_order, try it first
        if hasattr(self.exchange, "create_bracket_order") and callable(getattr(self.exchange, "create_bracket_order")):
            try:
                return await self.exchange.create_bracket_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    take_profit_price=take_profit_price,
                    wait_timeout=wait_timeout
                )
            except Exception as e:
                logger.warning("create_bracket_order del cliente falló: %s — intentando fallback limit-only", e)

        entry_order = None
        stop_order = None
        tp_order = None
        close_side = "SELL" if side.upper() == "BUY" else "BUY"

        # 1) Create entry as LIMIT only
        try:
            params_entry = {"timeInForce": "GTC"}
            entry_order = await self.exchange.create_order(symbol, 'limit', side, quantity, entry_price, params_entry)
            logger.info("Orden LIMIT de entrada creada para %s: %s", symbol, entry_order)
        except Exception as e:
            logger.error("No se pudo crear la orden LIMIT de entrada para %s a %s: %s", symbol, entry_price, e)
            raise Exception(f"No se pudo crear orden LIMIT de entrada para {symbol}: {e}") from e

        # 2) SL stop-limit (attempt common variants)
        try:
            params_sl = {"stopPrice": stop_price, "reduceOnly": True, "timeInForce": "GTC"}
            try:
                stop_order = await self.exchange.create_order(symbol, 'stop_limit', close_side, quantity, stop_price, params_sl)
            except Exception:
                stop_order = await self.exchange.create_order(symbol, 'STOP_LIMIT', close_side, quantity, stop_price, params_sl)
            logger.info("Stop-limit creado para %s: %s", symbol, stop_order)
        except Exception as e:
            logger.warning("Crear SL (stop-limit) falló para %s: %s", symbol, e)
            stop_order = None

        # 3) TP take-profit-limit (attempt common variants)
        try:
            params_tp = {"stopPrice": take_profit_price, "reduceOnly": True, "timeInForce": "GTC"}
            try:
                tp_order = await self.exchange.create_order(symbol, 'take_profit_limit', close_side, quantity, take_profit_price, params_tp)
            except Exception:
                tp_order = await self.exchange.create_order(symbol, 'TAKE_PROFIT_LIMIT', close_side, quantity, take_profit_price, params_tp)
            logger.info("Take-profit limit creado para %s: %s", symbol, tp_order)
        except Exception as e:
            logger.warning("Crear TP (take-profit limit) falló para %s: %s", symbol, e)
            tp_order = None

        return entry_order, stop_order, tp_order

    async def ejecutar_trade(self, sym: str, signal: str):
        if sym in self.state.open_positions:
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

        # Excepción SOL/USDT para abrir orden mínima
        min_notional = MIN_NOTIONAL_USD
        if sym == "SOL/USDT":
            min_notional = min(MIN_NOTIONAL_USD, 5)

        quantity = (size_usdt / price)
        notional = price * quantity
        if notional > MAX_TRADE_USDT:
            quantity = MAX_TRADE_USDT / price
            notional = MAX_TRADE_USDT
        if notional < min_notional:
            if sym != "SOL/USDT":
                await self.safe_send_telegram(f"⚠️ Orden ignorada {sym}: Notional {notional:.2f} < min {min_notional}")
                return
            else:
                quantity = min_notional / price
                notional = min_notional

        # Aplicar leverage
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
                # register_open_position expects notional based on pre-leverage amount in previous design
                self.state.register_open_position(sym, signal, entry, (quantity / LEVERAGE) * price, sl, tp)
                await self.safe_send_telegram(
                    f"✅ {sym} {signal.upper()} LIMIT creado @ {entry:.2f} USDT\nSL {sl:.2f} | TP {tp:.2f} | Qty {quantity:.6f}"
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
            try:
                self.state.reset_daily_if_needed()
            except Exception:
                logger.debug("StateManager.reset_daily_if_needed missing or failed", exc_info=True)
            if not getattr(self.state, "can_open_new_trade", lambda: True)() or len(getattr(self.state, "open_positions", {})) >= MAX_OPERATIONS_SIMULTANEAS:
                await asyncio.sleep(60)
                continue
            tasks = [self.procesar_par(sym) for sym in WATCHLIST_DINAMICA]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(1)


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
                f"📌 Watchlist: {WATCHLIST_DINAMICA}"
            )
        except Exception as e:
            await bot.safe_send_telegram(f"❌ Error en reporte horario: {e}")


async def monitor_positions(bot):
    """
    Monitor flexible que:
    - pregunta a StateManager por posiciones cerradas (métodos check_positions_closed/get_closed_positions/closed_positions_history)
    - y notifica cierres
    Nota: idealmente añadir reconciliador que inspeccione fetch_open_orders/fetch_order y actualice state.
    """
    while True:
        try:
            closed_positions = []
            if hasattr(bot.state, "check_positions_closed") and callable(getattr(bot.state, "check_positions_closed")):
                closed_positions = bot.state.check_positions_closed()
            elif hasattr(bot.state, "get_closed_positions") and callable(getattr(bot.state, "get_closed_positions")):
                closed_positions = bot.state.get_closed_positions()
            else:
                if hasattr(bot.state, "closed_positions_history"):
                    closed_positions = getattr(bot.state, "closed_positions_history")
                else:
                    closed_positions = []

            for pos in closed_positions:
                try:
                    sym = pos.get("symbol") if isinstance(pos, dict) else pos["symbol"]
                    pnl = pos.get("pnl", 0.0) if isinstance(pos, dict) else pos.get("pnl", 0.0)
                    reason = pos.get("reason", "unknown") if isinstance(pos, dict) else pos.get("reason", "unknown")
                    await bot.safe_send_telegram(f"📉 {sym} cerrada por {reason}. PnL: {pnl:.2f} USDT")
                except Exception:
                    logger.debug("Posición cerrada con formato inesperado: %s", pos)
                    continue
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
        await bot.safe_send_telegram("🚀 CryptoBot iniciado en TESTNET (limit-only orders)")
        await bot.actualizar_watchlist()
        tasks.append(asyncio.create_task(periodic_report(bot)))
        tasks.append(asyncio.create_task(monitor_positions(bot)))
        tasks.append(asyncio.create_task(watchdog_loop(bot)))
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
