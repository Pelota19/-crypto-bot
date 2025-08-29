import logging
from src.config import BYBIT_MODE, POSITION_SIZE_PERCENT, STARTING_BALANCE_USDT, DAILY_PROFIT_TARGET_USD, MAX_DAILY_LOSS_USD
from src.persistence.sqlite_store import save_order, save_balance
from src.notifier.telegram_notifier import send_message
import asyncio
from datetime import datetime, date

logger = logging.getLogger(__name__)

# In-memory daily tracking (recreated on restart)
_daily_profit = 0.0
_daily_loss = 0.0
_last_day = date.today()

async def get_balance_simulated() -> float:
    """
    Returns the current simulated available USD (starting balance minus PnL).
    In paper mode we use STARTING_BALANCE_USDT - tracked PnL in DB (simple approach).
    For the initial version we return STARTING_BALANCE_USDT.
    """
    # For simplicity: caller can persist balance externally; we log and return starting amount for first tests.
    return STARTING_BALANCE_USDT

async def can_trade_today() -> bool:
    global _daily_profit, _daily_loss, _last_day
    today = date.today()
    if today != _last_day:
        _daily_profit = 0.0
        _daily_loss = 0.0
        _last_day = today
    if _daily_profit >= DAILY_PROFIT_TARGET_USD:
        await send_message(f"Daily profit target reached ({_daily_profit} USD). Trading paused for today.")
        return False
    if _daily_loss >= MAX_DAILY_LOSS_USD:
        await send_message(f"Daily loss limit reached ({_daily_loss} USD). Trading paused for today.")
        return False
    return True

async def manage_position(exchange, symbol: str, signal: str, ohlcv_last_price: float):
    """
    Minimal manager that:
    - In paper mode simulates an order and logs + persists it.
    - In live mode places a market order via exchange.create_order (caller must ensure params).
    """
    global _daily_profit, _daily_loss

    if not await can_trade_today():
        return {"status": "paused"}

    if signal == "hold":
        logger.info("Signal hold - no action")
        return {"status": "hold"}

    # position sizing (value in USD)
    equity = await get_balance_simulated()
    order_value = max(1.0, equity * POSITION_SIZE_PERCENT)
    amount = order_value / float(ohlcv_last_price)

    side = "buy" if signal == "buy" else "sell"
    if BYBIT_MODE == "paper":
        # simulate execution at last price
        save_order(symbol, side, float(ohlcv_last_price), float(amount), float(order_value), "filled_paper")
        # simple PnL simulation: assume immediate unrealized PnL 0 (we log executed value)
        await send_message(f"PAPER ORDER: {side} {symbol} amount={amount:.6f} price={ohlcv_last_price:.4f} value_usd={order_value:.2f}")
        logger.info("Simulated paper order placed: %s %s", side, symbol)
        # For demonstration, we won't update _daily_profit/_daily_loss until we settle trades (future)
        save_balance(equity)  # snapshot
        return {"status": "paper_filled", "side": side, "amount": amount, "price": ohlcv_last_price}
    else:
        # LIVE mode - attempt to create a market order (simplified example)
        try:
            # note: for bybit futures may require params like reduceOnly/leverage; this is a basic example
            order = await exchange.create_order(symbol, "market", side, amount, None, {})
            save_order(symbol, side, order.get("price") or ohlcv_last_price, amount, order_value, "filled_live")
            await send_message(f"LIVE ORDER placed: {side} {symbol} amount={amount:.6f} value_usd={order_value:.2f}")
            return {"status": "live_filled", "order": order}
        except Exception as e:
            logger.exception("Failed placing live order: %s", e)
            await send_message(f"ERROR placing live order: {e}")
            return {"status": "error", "error": str(e)}
