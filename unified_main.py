import asyncio
from core.bot import CryptoBot
import logging

logging.basicConfig(level=logging.INFO)

async def main():
    bot = CryptoBot()
    await bot.start()
    try:
        await bot.run_trading_loop()
    except KeyboardInterrupt:
        await bot.stop()

if __name__ == "__main__":
    asyncio.run(main())
