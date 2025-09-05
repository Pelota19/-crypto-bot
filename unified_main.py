import asyncio import logging import time from typing import Optional

from src.exchange.binance_client import BinanceClient from src.config import API_KEY, API_SECRET, USE_TESTNET, DRY_RUN, LEVERAGE from src.notifier.telegram_notifier import TelegramNotifier from src.state import BotState

logger = logging.getLogger(name)

class TradingBot: def init(self): self.client = BinanceClient(API_KEY, API_SECRET, USE_TESTNET, DRY_RUN) self.notifier = TelegramNotifier() self.state = BotState()

async def _create_bracket_order(
    self,
    symbol: str,
    side: str,
    amount: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
):
    try:
        logger.info("Opening %s position on %s qty=%s", side, symbol, amount)

        order = await self.client.create_order(
            symbol,
            type="LIMIT",
            side=side,
            amount=amount,
            price=entry_price,
            params={"timeInForce": "GTC"},
        )

        if not order or order.get("status") == "rejected":
            logger.error("Entry order rejected: %s", order)
            return None

        position_side = "LONG" if side.upper() == "BUY" else "SHORT"

        stop_params = {"stopPrice": stop_loss, "closePosition": False, "positionSide": position_side}
        tp_params = {"price": take_profit, "reduceOnly": True, "positionSide": position_side}

        stop_order = await self.client.create_order(
            symbol,
            type="STOP_MARKET",
            side="SELL" if side.upper() == "BUY" else "BUY",
            amount=amount,
            params=stop_params,
        )

        tp_order = await self.client.create_order(
            symbol,
            type="TAKE_PROFIT_MARKET",
            side="SELL" if side.upper() == "BUY" else "BUY",
            amount=amount,
            params=tp_params,
        )

        self.state.add_trade(symbol, order, stop_order, tp_order)

        await self.notifier.send(
            f"Opened {position_side} {symbol}\nEntry: {entry_price}\nSL: {stop_loss}\nTP: {take_profit}"
        )
        return order
    except Exception as e:
        logger.exception("Bracket order failed: %s", e)
        await self.notifier.send(f"❌ Bracket order failed: {e}")
        return None

async def run(self):
    await self.client._ensure_exchange()
    logger.info("Bot started")

    while True:
        try:
            # Aquí deberías agregar tu lógica de señal
            # Ejemplo dummy: abre una sola orden LONG en BTC/USDT
            if not self.state.has_open_trade("BTC/USDT"):
                ticker = await self.client.fetch_ticker("BTC/USDT")
                if ticker:
                    price = ticker["last"]
                    await self._create_bracket_order(
                        symbol="BTC/USDT",
                        side="BUY",
                        amount=0.001,
                        entry_price=price * 0.999,
                        stop_loss=price * 0.995,
                        take_profit=price * 1.01,
                    )

            await asyncio.sleep(10)
        except Exception as e:
            logger.exception("Main loop error: %s", e)
            await asyncio.sleep(5)

if name == "main": logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s") bot = TradingBot() try: asyncio.run(bot.run()) except KeyboardInterrupt: logger.info("Bot stopped by user")

