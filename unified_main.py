import asyncio
import logging
import datetime

from src.exchange.binance_client import BinanceFuturesClient
from src.executor import Executor
from src.state import StateManager
from src.notifier.telegram_notifier import TelegramNotifier
from src.pair_selector import PairSelector
from src.signal_generator import SignalGenerator

# ========================
# Configuración General
# ========================
CAPITAL_TOTAL = 2000
RIESGO_POR_OPERACION_PORCENTAJE = 1.0
OBJETIVO_PROFIT_DIARIO = 50
MAX_OPERACIONES_SIMULTANEAS = 5

TELEGRAM_TOKEN = "TU_TOKEN"
TELEGRAM_CHAT_ID = "TU_CHAT_ID"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/crypto_bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class CryptoBot:
    def __init__(self):
        # Exchange
        self.exchange = BinanceFuturesClient()

        # Componentes principales
        self.executor = Executor(self.exchange, dry_run=False)
        self.state_manager = StateManager(daily_profit_target=OBJETIVO_PROFIT_DIARIO)
        self.notifier = TelegramNotifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
        self.pair_selector = PairSelector(self.exchange)
        self.signal_generator = SignalGenerator(self.exchange)

        # Variables internas
        self.watchlist = []

    async def actualizar_watchlist(self):
        """ Actualizar dinámicamente la watchlist cada hora """
        self.watchlist = await self.pair_selector.select_top_symbols_async(
            position_size_percent=RIESGO_POR_OPERACION_PORCENTAJE
        )
        self.notifier.send(f"🔄 Watchlist actualizada: {', '.join(self.watchlist)}")

    async def hourly_summary(self):
        """ Enviar resumen cada hora a Telegram """
        while True:
            now = datetime.datetime.utcnow()
            summary = (
                f"📊 RESUMEN {now.strftime('%Y-%m-%d %H:%M')}\n"
                f"PnL Realizado Hoy: {self.state_manager.realized_pnl_today:.2f} USDT\n"
                f"Operaciones Abiertas: {len(self.state_manager.open_positions)}\n"
                f"Watchlist Dinámica: {', '.join(self.watchlist)}"
            )
            self.notifier.send(summary)
            await asyncio.sleep(3600)

    async def run_trading_loop(self):
        """ Bucle principal del bot """
        while True:
            try:
                # Verificar si puede abrir nuevas operaciones
                if not self.state_manager.can_open_new_trade():
                    await asyncio.sleep(60)
                    continue

                # Control de concurrencia
                if len(self.state_manager.open_positions) >= MAX_OPERACIONES_SIMULTANEAS:
                    await asyncio.sleep(60)
                    continue

                # Escaneo de señales en la watchlist
                for symbol in self.watchlist:
                    if symbol in self.state_manager.open_positions:
                        continue  # ya hay posición abierta en este par

                    signal = await self.signal_generator.check_signal(symbol)
                    if signal:
                        side, entry, sl, tp, size = signal

                        # Ejecutar trade
                        order = await self.executor.open_position(symbol, side, size, entry)
                        if order:
                            self.state_manager.register_open_position(symbol, side, entry, size, sl, tp)
                            self.notifier.send(
                                f"🚀 Trade abierto: {symbol} {side}\nEntry: {entry}\nSL: {sl}\nTP: {tp}\nSize: {size}"
                            )

                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Unhandled exception in trading loop: {e}")
                self.notifier.send(f"⚠️ Error en loop: {e}")
                await asyncio.sleep(30)

    async def main(self):
        logger.info("Starting CryptoBot")
        self.notifier.send("🚀 CryptoBot started on TESTNET")

        # Primera actualización de watchlist
        await self.actualizar_watchlist()

        # Resumen cada hora
        asyncio.create_task(self.hourly_summary())

        # Trading loop
        await self.run_trading_loop()

if __name__ == "__main__":
    bot = CryptoBot()
    try:
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        logger.info("Stopping CryptoBot")
        bot.notifier.send("⛔ CryptoBot stopped")
