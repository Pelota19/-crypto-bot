#!/usr/bin/env python3
"""
Crypto Scalping Bot - Main Entry Point

A modular crypto scalping bot that runs on Binance Futures Testnet with:
- Risk management and position sizing
- EMA cross + RSI strategy 
- Daily profit targets
- Telegram notifications
- Market analysis
"""
import asyncio
import signal
import sys
from core.bot import CryptoBot
from utils.logger import setup_logging, get_logger

logger = get_logger(__name__)

# Global bot instance
bot = None

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print("\nShutdown signal received...")
    if bot:
        asyncio.create_task(bot.stop())
    sys.exit(0)

async def main():
    """Main entry point."""
    global bot
    
    # Setup logging
    setup_logging()
    logger.info("Starting Crypto Scalping Bot")
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Create and start bot
        bot = CryptoBot()
        await bot.start()
        
        # Run trading loop
        await bot.run_trading_loop()
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
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