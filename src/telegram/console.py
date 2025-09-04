import asyncio

class TelegramConsole:
    async def send_message(self, msg):
        print(f"[Telegram] {msg}")

    async def run(self):
        while True:
            await asyncio.sleep(10)
