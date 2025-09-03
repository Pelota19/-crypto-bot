"""
Telegram console module.
Placeholder for Telegram bot interface.
"""
import asyncio


# Simple helpers (placeholders)
async def send_message(message: str):
    print(f"Telegram: {message}")


async def poll_commands(handler):
    """Placeholder poller: doesn't produce commands, keeps a dormant loop."""
    while False:
        await asyncio.sleep(3600)


class TelegramConsole:
    """Placeholder Telegram console."""

    def __init__(self, order_manager=None):
        self.order_manager = order_manager

    async def run(self):
        """Run the Telegram console."""
        # Placeholder implementation
        pass

    async def send_message(self, message: str):
        """Send a message via Telegram."""
        # Placeholder implementation
        print(f"Telegram: {message}")