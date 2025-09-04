import asyncio

class TelegramConsole:
    def __init__(self, order_manager=None):
        self.order_manager = order_manager

    async def run(self):
        pass  # placeholder

    async def send_message(self, message: str):
        print(f"[Telegram] {message}")
