import asyncio
import logging
from typing import Optional
import src.logging_config  # noqa: F401 - Import for side effects (configures logging)
from src.exchange.binance_client import create_binance_exchange
from src.fetcher import fetch_ohlcv_for_symbol
from src.strategy.strategy import decide_signal
from src.trade_manager import manage_position, get_balance_simulated
from src.notifier.telegram_notifier import send_message

logger = logging.getLogger(__name__)


# main orchestration
async def run_once(symbol: Optional[str] = None):
    exchange = create_binance_exchange()
    try:
        markets = await exchange.load_markets()
        logger.info("Markets loaded: %d", len(markets))
        if not symbol:
            # choose a USDT pair if possible
            for s in markets.keys():
                if "USDT" in s:
                    symbol = s
                    break
            if not symbol:
                symbol = list(markets.keys())[0]
        logger.info("Selected symbol: %s", symbol)

        # Fetch OHLCV (use 1h candle as example)
        ohlcv = await fetch_ohlcv_for_symbol(
            exchange, symbol, timeframe="1h", limit=200
        )
        if ohlcv is None or ohlcv.empty:
            logger.warning("No OHLCV data available for %s", symbol)
            await send_message(f"No OHLCV for {symbol} - skipping")
            return

        signal = decide_signal(ohlcv)
        logger.info("Signal for %s: %s", symbol, signal)
        # price is last close
        last_price = float(ohlcv["close"].iloc[-1])

        # optional: check simulated balance
        balance = await get_balance_simulated()
        logger.info("Simulated balance: %s", balance)

        result = await manage_position(exchange, symbol, signal, last_price)
        logger.info("manage_position result: %s", result)

    except Exception as e:
        logger.exception("Error in run_once: %s", e)
        await send_message(f"Bot error: {e}")
    finally:
        await exchange.close()


async def run_loop(interval_seconds: int = 60 * 60):
    """Run the bot in a loop with error recovery."""
    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            await run_once()
            consecutive_errors = 0  # Reset on successful run
        except Exception as e:
            consecutive_errors += 1
            logger.exception(
                "Error in run_loop iteration %d: %s", consecutive_errors, e
            )

            if consecutive_errors >= max_consecutive_errors:
                error_msg = (
                    f"Too many consecutive errors ({consecutive_errors}). Stopping bot."
                )
                logger.critical(error_msg)
                try:
                    await send_message(error_msg)
                except Exception:
                    pass  # Don't fail if telegram fails
                break

            # Wait a bit longer after errors
            error_sleep = min(interval_seconds * 2, 300)  # Max 5 minutes
            logger.info("Waiting %d seconds before retry...", error_sleep)
            await asyncio.sleep(error_sleep)
            continue

        await asyncio.sleep(interval_seconds)


async def health_check():
    """Basic health check for bot components."""
    logger.info("Running health check...")

    try:
        # Test exchange connection
        exchange = create_binance_exchange()
        try:
            # Try to get server time (lightweight test)
            server_time = await exchange.fetch_time()
            logger.info("Exchange connection: OK (server time: %s)", server_time)
        finally:
            await exchange.close()
    except Exception as e:
        logger.warning("Exchange connection: FAILED (%s)", e)

    # Test balance simulation
    try:
        balance = await get_balance_simulated()
        logger.info("Balance simulation: OK (%s)", balance)
    except Exception as e:
        logger.warning("Balance simulation: FAILED (%s)", e)

    # Test telegram (if configured)
    try:
        await send_message("🔧 Bot health check completed")
        logger.info("Telegram notifications: OK")
    except Exception as e:
        logger.warning("Telegram notifications: FAILED (%s)", e)


if __name__ == "__main__":
    # Run configuration validation first
    from validate_config import validate_config

    issues, warnings = validate_config()

    if issues:
        logger.critical("Configuration issues found:")
        for issue in issues:
            logger.critical("  • %s", issue)
        exit(1)

    if warnings:
        logger.warning("Configuration warnings:")
        for warning in warnings:
            logger.warning("  • %s", warning)

    # Run health check and then main execution
    try:
        logger.info("Starting crypto bot...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run health check first
        loop.run_until_complete(health_check())

        # For beginners: to run once:
        # python -m src.main
        loop.run_until_complete(run_once())

        # Uncomment to run in loop mode:
        # loop.run_until_complete(run_loop())

    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        exit(1)
    finally:
        if "loop" in locals():
            loop.close()
        logger.info("Bot shutdown complete")
