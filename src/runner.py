import asyncio
import logging
from datetime import datetime

from src.config import PAIRS, TIMEFRAME, DAILY_PROFIT_GOAL_USD
from src.exchange.client import ExchangeClient
from src.strategy.scalping import ScalpingStrategy
from src.orders.manager import OrderManager
from src.risk.manager import RiskManager
from src.state import bot_state
from src.telegram.console import TelegramConsole


def setup_logging():
    """Sets up the logging configuration (console + daily rotating file)."""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    # Create logs directory if it doesn't exist
    import os
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Configure logging to file
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        filename=f'logs/trading_bot_{datetime.now().strftime("%Y-%m-%d")}.log',
        filemode='a'
    )

    # Configure console logging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(console_handler)

    logging.info("Logging configured.")


async def main():
    """Main function to run the bot."""
    setup_logging()
    logging.info("Starting crypto scalping bot...")

    # Initialize components
    exchange_client = ExchangeClient()
    order_manager = OrderManager(exchange_client)
    risk_manager = RiskManager()
    strategy = ScalpingStrategy()
    telegram_console = TelegramConsole(order_manager)

    # Start Telegram console in the background
    asyncio.create_task(telegram_console.run())
    logging.info("Telegram console started.")

    await telegram_console.send_message("Bot iniciado. ¡A la caza de oportunidades! 🚀")

    while True:
        try:
            # Respect pause state
            if bot_state.is_paused:
                await asyncio.sleep(10)
                continue

            # Pause when daily PnL goal reached
            if bot_state.daily_pnl_usd >= DAILY_PROFIT_GOAL_USD:
                if not bot_state.is_paused:
                    logging.info(
                        f"Daily profit goal of ${DAILY_PROFIT_GOAL_USD} reached. Pausing new trades.")
                    await telegram_console.send_message(
                        f"🎉 ¡Meta de ganancias diarias alcanzada (${bot_state.daily_pnl_usd:.2f})! "
                        "El bot se detiene hasta mañana. 🎉"
                    )
                    bot_state.is_paused = True
                await asyncio.sleep(60)
                continue

            # Update open positions and PnL
            await order_manager.update_open_positions()

            # Per-pair strategy loop
            for pair in PAIRS:
                if not risk_manager.can_open_new_trade(pair):
                    logging.debug(
                        f"Cannot open new trade for {pair} due to risk limits or existing position.")
                    continue

                logging.debug(f"Fetching data for {pair} on {TIMEFRAME} timeframe.")
                klines = await exchange_client.get_klines(pair, TIMEFRAME)

                if klines is None or getattr(klines, 'empty', False):
                    logging.warning(f"No kline data returned for {pair}.")
                    continue

                signal = strategy.analyze(klines)

                if signal.get('signal') and signal['signal'] != 'none':
                    logging.info(f"Signal for {pair}: {signal['signal'].upper()}")
                    trade_size_usd = risk_manager.calculate_position_size()

                    if trade_size_usd > 0:
                        await order_manager.place_order(
                            pair=pair,
                            signal=signal['signal'],
                            trade_size_usd=trade_size_usd,
                            entry_price=signal.get('price')
                        )
                    else:
                        logging.warning("Position size is zero; skipping order.")

            # Sleep before next cycle
            await asyncio.sleep(60)

        except asyncio.CancelledError:
            logging.info("Bot shutdown requested.")
            break
        except Exception as e:
            logging.error(
                f"Unexpected error in main loop: {e}", exc_info=True)
            try:
                await telegram_console.send_message(f"⚠️ Error crítico en el bot: {e}")
            except Exception:
                # Avoid crash if Telegram also fails
                pass
            await asyncio.sleep(60)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")