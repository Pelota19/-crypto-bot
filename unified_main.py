#!/usr/bin/env python3
"""
Unified CryptoBot - Entry point
Testnet real con Binance Futures (USDT-M)
"""
import asyncio
import logging
from core.bot import CryptoBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    bot = CryptoBot()
    await bot.start()
    await bot.run_trading_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot detenido por usuario")
    except Exception as e:
        print(f"Error iniciando el bot: {e}")
