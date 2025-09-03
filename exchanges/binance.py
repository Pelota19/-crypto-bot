"""Binance Futures exchange implementation."""
import ccxt.async_support as ccxt
from typing import Dict, List, Optional, Any
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)

class BinanceExchange:
    """Binance Futures exchange wrapper."""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """Initialize Binance exchange."""
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self._exchange = None
        
    async def _get_exchange(self):
        """Get or create exchange instance."""
        if self._exchange is None:
            config = {
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "future"  # Use futures by default
                }
            }
            
            self._exchange = ccxt.binance(config)
            
            if self.testnet:
                try:
                    # Enable sandbox mode for testnet
                    self._exchange.set_sandbox_mode(True)
                    logger.info("Binance Futures Testnet mode enabled")
                except Exception as e:
                    logger.warning(f"Could not set sandbox mode: {e}")
            
        return self._exchange
    
    async def load_markets(self) -> Dict:
        """Load available markets."""
        exchange = await self._get_exchange()
        return await exchange.load_markets()
    
    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 100) -> pd.DataFrame:
        """Fetch OHLCV data."""
        try:
            exchange = await self._get_exchange()
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            if not ohlcv:
                return pd.DataFrame()
            
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            return pd.DataFrame()
    
    async def create_market_order(self, symbol: str, side: str, amount: float, params: Optional[Dict] = None) -> Dict:
        """Create a market order."""
        try:
            exchange = await self._get_exchange()
            order = await exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=amount,
                price=None,
                params=params or {}
            )
            logger.info(f"Market order created: {side} {amount} {symbol}")
            return order
        except Exception as e:
            logger.error(f"Failed to create market order: {e}")
            raise
    
    async def create_limit_order(self, symbol: str, side: str, amount: float, price: float, params: Optional[Dict] = None) -> Dict:
        """Create a limit order (for TP)."""
        try:
            exchange = await self._get_exchange()
            order = await exchange.create_order(
                symbol=symbol,
                type="limit",
                side=side,
                amount=amount,
                price=price,
                params=params or {}
            )
            logger.info(f"Limit order created: {side} {amount} {symbol} @ {price}")
            return order
        except Exception as e:
            logger.error(f"Failed to create limit order: {e}")
            raise
    
    async def create_stop_order(self, symbol: str, side: str, amount: float, stop_price: float, params: Optional[Dict] = None) -> Dict:
        """Create a stop order (for SL)."""
        try:
            exchange = await self._get_exchange()
            
            # For Binance Futures, use stopPrice parameter
            stop_params = {"stopPrice": stop_price}
            if params:
                stop_params.update(params)
            
            order = await exchange.create_order(
                symbol=symbol,
                type="stop",
                side=side,
                amount=amount,
                price=None,
                params=stop_params
            )
            logger.info(f"Stop order created: {side} {amount} {symbol} @ stop {stop_price}")
            return order
        except Exception as e:
            logger.error(f"Failed to create stop order: {e}")
            raise
    
    async def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """Cancel an order."""
        try:
            exchange = await self._get_exchange()
            result = await exchange.cancel_order(order_id, symbol)
            logger.info(f"Order cancelled: {order_id} for {symbol}")
            return result
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            raise
    
    async def fetch_order_status(self, order_id: str, symbol: str) -> Dict:
        """Fetch order status."""
        try:
            exchange = await self._get_exchange()
            order = await exchange.fetch_order(order_id, symbol)
            return order
        except Exception as e:
            logger.error(f"Failed to fetch order status {order_id}: {e}")
            raise
    
    async def fetch_balance(self) -> Dict:
        """Fetch account balance."""
        try:
            exchange = await self._get_exchange()
            balance = await exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            raise
    
    async def close(self):
        """Close exchange connection."""
        if self._exchange:
            await self._exchange.close()
            self._exchange = None