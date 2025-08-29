import asyncio
import logging
import pandas as pd
from src.logging_config import *
from src.exchange.bybit_client import create_bybit_exchange
from src.fetcher import fetch_ohlcv_for_symbol
from src.strategy.strategy import decide_signal
from src.trade_manager import manage_position, get_balance_simulated
from src.notifier.telegram_notifier import send_message

logger = logging.getLogger(__name__)

# main orchestration
async def run_once(symbol: str = None):
    exchange = create_bybit_exchange()
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
        ohlcv = await fetch_ohlcv_for_symbol(exchange, symbol, timeframe="1h", limit=200)
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
    # simple loop that runs run_once every interval_seconds
    while True:
        await run_once()
        await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    # for beginners: to run once:
    # python -m src.main
    asyncio.run(run_once())
