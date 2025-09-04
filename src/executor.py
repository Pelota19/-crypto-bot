import asyncio

class Executor:
    def __init__(self, exchange):
        self.exchange = exchange

    async def start(self):
        pass

    async def stop(self):
        pass

    async def open_position(self, symbol, side, size_usd, price):
        print(f"Simulated open {side} on {symbol} {size_usd} USD @ {price}")
        await asyncio.sleep(0.1)
