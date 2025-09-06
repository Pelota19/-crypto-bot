import asyncio
import logging
from src.exchange.binance_client import BinanceClient

logging.basicConfig(level=logging.INFO)

async def test_symbols():
    client = BinanceClient(dry_run=True)  # Dry-run para no tocar real
    symbols = await client.fetch_all_symbols()
    valid_symbols = []

    for sym in symbols:
        try:
            # Intentar fetch OHLCV para ver si el símbolo es válido
            ohlcv = await client.fetch_ohlcv(sym, limit=1)
            if not ohlcv:
                logging.info(f"{sym} - Ignorado: no hay OHLCV")
                continue
        except Exception as e:
            logging.warning(f"{sym} - Ignorado: {e}")
            continue

        # Revisar mínimo de orden según la estrategia
        try:
            market_info = client.exchange.markets[sym]
            min_qty = float(market_info['limits']['amount']['min'])
            estrategia_qty = 0.01  # reemplazar por tu qty de estrategia
            if estrategia_qty < min_qty:
                logging.info(f"{sym} - Ignorado: estrategia qty {estrategia_qty} < min {min_qty}")
                continue
        except Exception as e:
            logging.warning(f"{sym} - No se pudo verificar lotSize: {e}")
            continue

        valid_symbols.append(sym)
        logging.info(f"{sym} - Válido para trading")

    logging.info(f"Símbolos válidos totales: {len(valid_symbols)}")
    await client.close()

if __name__ == "__main__":
    asyncio.run(test_symbols())
