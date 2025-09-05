import asyncio
import logging
import os
from dotenv import load_dotenv

from binance_client import BinanceClient
from strategies.scalping_strategy import ScalpingStrategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("unified_main")


async def main():
    load_dotenv()

    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    use_testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"

    client = BinanceClient(api_key, api_secret, use_testnet=use_testnet, dry_run=dry_run)
    strategy = ScalpingStrategy(client)

    try:
        while True:
            # Filtra símbolos con ±5% en 24h
            symbols = await client.fetch_symbols_with_change(5.0)
            logger.info("Símbolos seleccionados para scalping: %s", symbols)

            if not symbols:
                logger.info("No hay símbolos con movimiento suficiente. Reintentando en 5m...")
                await asyncio.sleep(300)
                continue

            # Ejecuta la estrategia de scalping en esos símbolos
            for sym in symbols:
                try:
                    await strategy.run(sym)
                except Exception as e:
                    logger.error("Error en estrategia para %s: %s", sym, e)

            # Espera antes de volver a actualizar la lista
            await asyncio.sleep(300)  # cada 5 minutos

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
