"""Telegram client for notifications."""
import asyncio
import requests
from typing import Optional
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from utils.logger import get_logger

logger = get_logger(__name__)

class TelegramClient:
    """Telegram bot client for sending notifications."""
    
    def __init__(self, token: str = None, chat_id: str = None):
        """Initialize Telegram client."""
        self.token = token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        
    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return bool(self.token and self.chat_id)
    
    def _send_sync(self, message: str) -> bool:
        """Send message synchronously."""
        if not self.is_configured():
            logger.debug("Telegram not configured, skipping message")
            return False
        
        try:
            response = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.debug("Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def send_message(self, message: str) -> bool:
        """Send message asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._send_sync, message)
    
    async def send_bot_start(self):
        """Send bot start notification."""
        message = "🤖 *Crypto Bot Started*\n\nBot is now running and monitoring markets."
        await self.send_message(message)
    
    async def send_bot_stop(self):
        """Send bot stop notification.""" 
        message = "🛑 *Crypto Bot Stopped*\n\nBot has been stopped."
        await self.send_message(message)
    
    async def send_order_notification(self, symbol: str, side: str, amount: float, 
                                    price: float, order_type: str = "market"):
        """Send order notification."""
        message = (
            f"📈 *Order {order_type.title()}*\n\n"
            f"Symbol: `{symbol}`\n"
            f"Side: *{side.upper()}*\n"
            f"Amount: `{amount:.6f}`\n"
            f"Price: `${price:.4f}`\n"
            f"Value: `${amount * price:.2f}`"
        )
        await self.send_message(message)
    
    async def send_tp_sl_notification(self, symbol: str, side: str, price: float, 
                                    pnl: float, reason: str):
        """Send TP/SL fill notification."""
        emoji = "🎯" if reason == "take_profit" else "🛡️"
        pnl_emoji = "✅" if pnl > 0 else "❌"
        
        message = (
            f"{emoji} *{reason.replace('_', ' ').title()} Hit*\n\n"
            f"Symbol: `{symbol}`\n"
            f"Side: *{side.upper()}*\n"
            f"Exit Price: `${price:.4f}`\n"
            f"PnL: {pnl_emoji} `${pnl:.2f}`"
        )
        await self.send_message(message)
    
    async def send_error_notification(self, error: str):
        """Send error notification."""
        message = f"⚠️ *Bot Error*\n\n`{error}`"
        await self.send_message(message)
    
    async def send_daily_target_reached(self, profit: float, target: float):
        """Send daily target reached notification."""
        message = (
            f"🎯 *Daily Target Reached!*\n\n"
            f"Profit: `${profit:.2f}`\n"
            f"Target: `${target:.2f}`\n\n"
            f"Trading paused until next day."
        )
        await self.send_message(message)
    
    async def send_daily_reset(self):
        """Send daily reset notification."""
        message = (
            f"🌅 *Daily Reset*\n\n"
            f"New trading day started.\n"
            f"Metrics reset and trading resumed."
        )
        await self.send_message(message)
    
    async def send_risk_limit_hit(self, limit_type: str, current: float, maximum: float):
        """Send risk limit notification."""
        message = (
            f"🚨 *Risk Limit Hit*\n\n"
            f"Type: `{limit_type}`\n"
            f"Current: `${current:.2f}`\n"
            f"Maximum: `${maximum:.2f}`\n\n"
            f"Trading paused for safety."
        )
        await self.send_message(message)

# Global instance
telegram_client = TelegramClient()

# Convenience functions
async def send_message(message: str) -> bool:
    """Send a Telegram message."""
    return await telegram_client.send_message(message)