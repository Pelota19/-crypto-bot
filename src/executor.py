import asyncio
import logging
from src.config import DRY_RUN
logger = logging.getLogger(__name__)

class Executor:
    def __init__(self, exchange, risk_manager, dry_run=True):
        self.exchange = exchange
        self.risk_manager = risk_manager
        self.dry_run = dry_run

    async def start(self):
        logger.info("Executor started (dry_run=%s)", self.dry_run)

    async def stop(self):
        logger.info("Executor stopped")

    async def open_position(self, symbol: str, side: str, size_usd: float, price: float):
        if self.dry_run:
            logger.info("Simulated open %s on %s %.2f USD @ %.2f", side.upper(), symbol, size_usd, price)
            return {"symbol": symbol, "side": side, "size_usd": size_usd, "price": price}
        else:
            # Testnet real order
            amount = size_usd / price
            order = await self.exchange.create_order(symbol, side, amount)
            logger.info("Opened %s on %s %.2f USD @ %.2f", side.upper(), symbol, size_usd, price)
            return order
