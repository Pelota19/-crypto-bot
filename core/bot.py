"""Main crypto scalping bot."""
import asyncio
from datetime import datetime, time, timedelta
from typing import Dict, List
from core.risk_manager import RiskManager
from exchanges.factory import create_exchange
from strategies.factory import create_strategy
from models.analyzer import MarketAnalyzer
from telegram.client import telegram_client
from config.settings import TRADING_PAIRS, STRATEGY, DAILY_PROFIT_TARGET
from utils.logger import get_logger, setup_logging

logger = get_logger(__name__)

class CryptoBot:
    """Main crypto scalping bot class."""
    
    def __init__(self):
        """Initialize the crypto bot."""
        setup_logging()
        
        self.risk_manager = RiskManager()
        self.exchange = None
        self.strategy = create_strategy(STRATEGY)
        self.analyzer = MarketAnalyzer()
        
        # Active orders tracking
        self.active_orders: Dict[str, Dict] = {}
        
        # Bot state
        self.running = False
        self.paused_until_midnight = False
        
    async def start(self):
        """Start the bot."""
        logger.info("Starting crypto bot...")
        
        try:
            # Initialize exchange
            self.exchange = create_exchange()
            await self.exchange.load_markets()
            logger.info("Exchange connected and markets loaded")
            
            # Send start notification
            await telegram_client.send_bot_start()
            
            self.running = True
            logger.info("Bot started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            await telegram_client.send_error_notification(f"Bot startup failed: {e}")
            raise
    
    async def stop(self):
        """Stop the bot."""
        logger.info("Stopping crypto bot...")
        
        self.running = False
        
        if self.exchange:
            await self.exchange.close()
        
        await telegram_client.send_bot_stop()
        logger.info("Bot stopped")
    
    async def run_trading_loop(self, interval_minutes: int = 1):
        """Main trading loop."""
        while self.running:
            try:
                # Check if we should pause until midnight
                if self.should_pause_until_midnight():
                    if not self.paused_until_midnight:
                        logger.info("Daily target reached, pausing until midnight")
                        await telegram_client.send_daily_target_reached(
                            self.risk_manager.daily_pnl, DAILY_PROFIT_TARGET
                        )
                        self.paused_until_midnight = True
                    
                    await self.wait_until_midnight()
                    continue
                
                # Reset pause flag if we've passed midnight
                if self.paused_until_midnight:
                    self.paused_until_midnight = False
                    await telegram_client.send_daily_reset()
                    logger.info("Daily reset completed, resuming trading")
                
                # Process each trading pair
                for symbol in TRADING_PAIRS:
                    try:
                        await self.process_symbol(symbol)
                    except Exception as e:
                        logger.error(f"Error processing {symbol}: {e}")
                        continue
                
                # Monitor active orders
                await self.monitor_orders()
                
                # Wait before next iteration
                await asyncio.sleep(interval_minutes * 60)
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await telegram_client.send_error_notification(f"Trading loop error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    async def process_symbol(self, symbol: str):
        """Process a single trading symbol."""
        logger.debug(f"Processing {symbol}")
        
        # Skip if we already have a position
        if self.risk_manager.get_position(symbol):
            logger.debug(f"Position already exists for {symbol}, skipping")
            return
        
        # Fetch market data
        df = await self.exchange.fetch_ohlcv(symbol, timeframe="1m", limit=200)
        if df.empty:
            logger.warning(f"No data available for {symbol}")
            return
        
        # Analyze market
        analysis = self.analyzer.analyze_market(df)
        
        # Generate trading signal
        signal = self.strategy.generate_signal(df)
        
        if signal["signal"] == "buy":
            await self.execute_buy_signal(symbol, signal, analysis)
    
    async def execute_buy_signal(self, symbol: str, signal: Dict, analysis: Dict):
        """Execute a buy signal."""
        logger.info(f"Buy signal for {symbol}: {signal}")
        
        # Check if we can open position
        if not self.risk_manager.can_open_position(symbol):
            logger.info(f"Cannot open position for {symbol} due to risk limits")
            return
        
        entry_price = signal["entry_price"]
        stop_loss = signal["stop_loss"]
        take_profit = signal["take_profit"]
        
        # Calculate position size
        position_size = self.risk_manager.calculate_position_size(
            entry_price, stop_loss, symbol
        )
        
        if position_size <= 0:
            logger.warning(f"Invalid position size for {symbol}")
            return
        
        try:
            # Place market order
            market_order = await self.exchange.create_market_order(
                symbol, "buy", position_size
            )
            
            # Get actual fill price
            fill_price = market_order.get("price", entry_price)
            
            # Register position
            self.risk_manager.open_position(
                symbol, "buy", fill_price, stop_loss, take_profit, position_size
            )
            
            # Place SL and TP orders
            try:
                # Place stop loss
                sl_order = await self.exchange.create_stop_order(
                    symbol, "sell", position_size, stop_loss
                )
                
                # Place take profit
                tp_order = await self.exchange.create_limit_order(
                    symbol, "sell", position_size, take_profit
                )
                
                # Track orders
                self.active_orders[symbol] = {
                    "market_order": market_order,
                    "sl_order": sl_order,
                    "tp_order": tp_order,
                    "position_size": position_size,
                    "entry_price": fill_price
                }
                
                logger.info(f"Position opened for {symbol} with SL/TP orders")
                
                # Send notification
                await telegram_client.send_order_notification(
                    symbol, "buy", position_size, fill_price
                )
                
            except Exception as e:
                logger.error(f"Failed to place SL/TP orders for {symbol}: {e}")
                # Still keep the position in risk manager
                # but we'll need to monitor manually
                
        except Exception as e:
            logger.error(f"Failed to execute buy order for {symbol}: {e}")
            await telegram_client.send_error_notification(
                f"Failed to place order for {symbol}: {e}"
            )
    
    async def monitor_orders(self):
        """Monitor active orders for fills."""
        for symbol, orders in list(self.active_orders.items()):
            try:
                sl_order = orders["sl_order"]
                tp_order = orders["tp_order"]
                
                # Check SL order status
                sl_status = await self.exchange.fetch_order_status(
                    sl_order["id"], symbol
                )
                
                if sl_status["status"] == "closed":
                    # SL hit
                    exit_price = sl_status["price"]
                    pnl = self.risk_manager.close_position(symbol, exit_price, "stop_loss")
                    
                    # Cancel TP order
                    try:
                        await self.exchange.cancel_order(tp_order["id"], symbol)
                    except:
                        pass
                    
                    # Remove from active orders
                    del self.active_orders[symbol]
                    
                    # Send notification
                    await telegram_client.send_tp_sl_notification(
                        symbol, "buy", exit_price, pnl, "stop_loss"
                    )
                    
                    logger.info(f"Stop loss hit for {symbol}, PnL: ${pnl:.2f}")
                    continue
                
                # Check TP order status
                tp_status = await self.exchange.fetch_order_status(
                    tp_order["id"], symbol
                )
                
                if tp_status["status"] == "closed":
                    # TP hit
                    exit_price = tp_status["price"]
                    pnl = self.risk_manager.close_position(symbol, exit_price, "take_profit")
                    
                    # Cancel SL order
                    try:
                        await self.exchange.cancel_order(sl_order["id"], symbol)
                    except:
                        pass
                    
                    # Remove from active orders
                    del self.active_orders[symbol]
                    
                    # Send notification
                    await telegram_client.send_tp_sl_notification(
                        symbol, "buy", exit_price, pnl, "take_profit"
                    )
                    
                    logger.info(f"Take profit hit for {symbol}, PnL: ${pnl:.2f}")
                
            except Exception as e:
                logger.error(f"Error monitoring orders for {symbol}: {e}")
    
    def should_pause_until_midnight(self) -> bool:
        """Check if bot should pause until midnight."""
        stats = self.risk_manager.get_daily_stats()
        return stats["target_reached"] or stats["daily_pnl"] >= DAILY_PROFIT_TARGET
    
    async def wait_until_midnight(self):
        """Wait until midnight (next day)."""
        now = datetime.now()
        midnight = datetime.combine(now.date(), time.min) + timedelta(days=1)
        sleep_seconds = (midnight - now).total_seconds()
        
        logger.info(f"Sleeping until midnight ({sleep_seconds:.0f} seconds)")
        await asyncio.sleep(min(sleep_seconds, 3600))  # Max 1 hour at a time
    
    async def get_status(self) -> Dict:
        """Get bot status."""
        stats = self.risk_manager.get_daily_stats()
        
        return {
            "running": self.running,
            "paused_until_midnight": self.paused_until_midnight,
            "daily_stats": stats,
            "active_positions": len(self.active_orders),
            "trading_pairs": TRADING_PAIRS
        }