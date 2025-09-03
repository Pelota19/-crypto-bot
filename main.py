#!/usr/bin/env python3
"""
Crypto Scalping Bot - Main Entry Point
"""
import asyncio
import signal
import sys
from core.bot import CryptoBot
from utils.logger import setup_logging, get_logger

logger = get_logger(__name__)
bot = None

def signal_handler(signum, frame):
    print("\nShutdown signal received...")
    if bot:
        asyncio.create_task(bot.stop())
    sys.exit(0)

async def main():
    global bot
    setup_logging()
    logger.info("Starting Crypto Scalping Bot")
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        bot = CryptoBot()
        await bot.start()
        await bot.run_trading_loop()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.exception("Bot crashed on start: %s", e)
        raise
    finally:
        if bot:
            await bot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Bot failed to start: {e}")
        sys.exit(1)
