from __future__ import annotations
import asyncio
import logging
from src.config import (
    MODE, BINANCE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET, CAPITAL_MAX_USDT,
    STARTING_BALANCE_USDT, POSITION_SIZE_PERCENT, DAILY_PROFIT_TARGET_USD, 
    MAX_DAILY_LOSS_USD, TIMEFRAME, MAX_SYMBOLS, MIN_24H_VOLUME_USDT, 
    SLEEP_SECONDS_BETWEEN_CYCLES, LOG_LEVEL, LEVERAGE, MARGIN_MODE
)
from src.config.plan_loader import get_plan_loader
from src.risk.guardrails import get_guardrails, TradeContext
from src.universe.selector import get_universe_selector
from src.exchange.binance_client import BinanceFuturesClient
from src.strategy.strategy import decide_trade
from src.state import load_state, save_state, reset_if_new_day, can_open_new_trades, update_pnl
from src.orders.manager import OrderManager
from src.persistence.sqlite_store import save_balance, _ensure_db
from src.telegram.console import send_message, poll_commands

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.WARNING),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")

class Context:
    def __init__(self):
        # Load plan configuration
        self.plan_loader = get_plan_loader()
        self.plan = self.plan_loader.load_plan()
        
        # Initialize risk guardrails
        self.guardrails = get_guardrails(self.plan_loader)
        
        # Initialize universe selector
        self.universe_selector = get_universe_selector(self.plan_loader)
        
        # Check if we should fallback to paper mode
        should_fallback = self.plan_loader.should_fallback_to_paper(BINANCE_API_KEY, BINANCE_API_SECRET)
        self.effective_mode = "paper" if should_fallback else MODE
        
        if should_fallback:
            log.warning(f"Plan mode '{self.plan.mode}' requires API credentials but they are missing. Running in paper mode.")
        
        # Initialize exchange client
        self.exchange = BinanceFuturesClient(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=BINANCE_TESTNET)
        self.state = load_state()
        # Initialize balance - use starting balance for paper mode, exchange balance for live (but cap for sizing)
        self.balance_snapshot = STARTING_BALANCE_USDT if MODE == "paper" else max(STARTING_BALANCE_USDT, self.exchange.get_balance_usdt())
        self.om = OrderManager(self.exchange, self.get_equity)
        # Snapshot for live mode PnL tracking
        self.initial_equity_snapshot = None

    def get_equity(self) -> float:
        """Get current equity, capped at CAPITAL_MAX_USDT for position sizing purposes."""
        if MODE == "paper":
            return min(self.balance_snapshot, CAPITAL_MAX_USDT)
        current = self.exchange.get_balance_usdt()
        return min(max(0.0, current), CAPITAL_MAX_USDT)

    def get_actual_balance(self) -> float:
        """Get actual balance without capital cap for PnL tracking."""
        if MODE == "paper":
            return self.balance_snapshot
        return max(0.0, self.exchange.get_balance_usdt())

async def handle_command(text: str, ctx: Context):
    """Handle telegram commands."""
    if text == "/status":
        actual_balance = ctx.get_actual_balance()
        equity_for_sizing = ctx.get_equity()
        msg = (
            f"🤖 <b>Bot Status</b>\n"
            f"Mode: {MODE} ({'testnet' if BINANCE_TESTNET else 'mainnet'})\n"
            f"Balance: {actual_balance:.2f} USDT\n"
            f"Capital for sizing: {equity_for_sizing:.2f} USDT\n"
            f"PnL Today: {ctx.state.pnl_today:.2f} USDT\n"
            f"Target: +{DAILY_PROFIT_TARGET_USD:.0f} | Max Loss: -{MAX_DAILY_LOSS_USD:.0f}\n"
            f"Status: {'🔴 PAUSED' if ctx.state.paused else '🟢 ACTIVE'}"
        )
        await send_message(msg)
    elif text == "/pause":
        ctx.state.paused = True
        save_state(ctx.state)
        await send_message("🔴 Bot paused. No new trades will be opened.")
    elif text == "/resume":
        ctx.state.paused = False
        save_state(ctx.state)
        await send_message("🟢 Bot resumed. Ready to trade!")

async def trading_loop():
    """Main trading loop orchestrator."""
    _ensure_db()
    ctx = Context()

    # Startup message
    mode_msg = f"🚀 Bot started in <b>{MODE}</b> mode on <b>{'Testnet' if BINANCE_TESTNET else 'MAINNET'}</b>"
    capital_msg = f"💰 Capital cap: {CAPITAL_MAX_USDT:.0f} USDT | Daily target: +{DAILY_PROFIT_TARGET_USD:.0f} USD"
    await send_message(f"{mode_msg}\n{capital_msg}")

    # Get trading universe
    symbols = ctx.exchange.get_usdt_perp_symbols(MIN_24H_VOLUME_USDT, MAX_SYMBOLS)
    universe_msg = f"🎯 Universe: {', '.join(symbols[:5])}{'...' if len(symbols) > 5 else ''} ({len(symbols)} symbols)"
    await send_message(universe_msg)

    # Set leverage and margin mode for live trading
    if MODE == "live":
        # Initialize equity snapshot for live mode PnL tracking
        ctx.initial_equity_snapshot = ctx.exchange.get_balance_usdt()
        
        log.warning(f"Setting leverage {LEVERAGE} and margin mode {MARGIN_MODE} for live trading")
        for sym in symbols:
            success_margin = ctx.exchange.set_margin_mode(sym, MARGIN_MODE)
            success_leverage = ctx.exchange.set_leverage(sym, LEVERAGE)
            if not (success_margin and success_leverage):
                log.warning(f"Failed to set margin/leverage for {sym}")

    # Start telegram command polling
    async def commands_poller():
        async def _handle(cmd: str):
            await handle_command(cmd, ctx)
        await poll_commands(_handle)

    # Start command poller as concurrent task
    asyncio.create_task(commands_poller())

    # Main trading loop
    while True:
        try:
            # Reset state if new day
            ctx.state = reset_if_new_day(ctx.state)
            
            # Check if we can trade (not paused, within daily limits)
            can_trade = can_open_new_trades(ctx.state)
            
            # Check if daily target reached and notify
            if ctx.state.pnl_today >= DAILY_PROFIT_TARGET_USD:
                if can_trade:  # First time reaching target
                    await send_message(f"🎉 Daily profit target reached: +{ctx.state.pnl_today:.2f} USD! Stopping new trades.")
                can_trade = False
            elif ctx.state.pnl_today <= -MAX_DAILY_LOSS_USD:
                if can_trade:  # First time hitting max loss
                    await send_message(f"⚠️ Daily loss limit reached: {ctx.state.pnl_today:.2f} USD! Stopping new trades.")
                can_trade = False

            # Iterate through symbols
            for sym in symbols:
                try:
                    # Fetch market data
                    df = ctx.exchange.fetch_ohlcv_df(sym, timeframe=TIMEFRAME, limit=200)
                    if df.empty or len(df) < 30:
                        continue

                    current_price = float(df["close"].iloc[-1])
                    
                    # Calculate position notional to check feasibility
                    equity_for_sizing = ctx.get_equity()
                    notional = equity_for_sizing * POSITION_SIZE_PERCENT
                    
                    # Check if trade is feasible (respects minQty)
                    if not ctx.exchange.is_trade_feasible(sym, notional, current_price):
                        continue

                    # Get trading decision from strategy
                    decision = decide_trade(df)
                    signal = decision["signal"]
                    
                    # Skip if hold signal or can't trade
                    if not can_trade or signal == "hold":
                        continue

                    # Open position
                    side = signal  # "buy" or "sell"
                    order = ctx.om.open_position_market(sym, side, POSITION_SIZE_PERCENT, price_hint=current_price)
                    
                    if order is None:
                        continue  # Order was skipped (amount below minQty)

                    # Calculate position amount for brackets
                    amount_usd = equity_for_sizing * POSITION_SIZE_PERCENT
                    position_amount = amount_usd / current_price

                    if MODE == "live":
                        # Place bracket orders (SL/TP) from strategy decision
                        sl_price = decision["sl"]
                        tp_price = decision["tp"]
                        
                        if sl_price > 0 and tp_price > 0:
                            bracket_result = ctx.om.place_brackets(sym, side, position_amount, sl_price, tp_price)
                            
                            # Notify successful trade with brackets
                            score = decision["score"]
                            msg = (
                                f"📈 <b>{sym}</b> {side.upper()} @ {current_price:.4f}\n"
                                f"💰 Size: {amount_usd:.0f} USDT\n"
                                f"🛡️ SL: {sl_price:.4f} | 🎯 TP: {tp_price:.4f}\n"
                                f"🤖 AI Score: {score:.3f}"
                            )
                            await send_message(msg)
                        
                        # Update PnL tracking by snapshotting balance
                        current_balance = ctx.get_actual_balance()
                        pnl_delta = current_balance - ctx.balance_snapshot
                        if abs(pnl_delta) > 0.01:  # Only update if meaningful change
                            ctx.state = update_pnl(ctx.state, pnl_delta)
                            ctx.balance_snapshot = current_balance
                            
                    else:
                        # Paper mode: simulate quick exit for demo
                        await asyncio.sleep(2)
                        df2 = ctx.exchange.fetch_ohlcv_df(sym, timeframe=TIMEFRAME, limit=2)
                        if df2.empty:
                            continue
                            
                        exit_price = float(df2["close"].iloc[-1])
                        gross_pnl = (exit_price - current_price) * (1 if side == "buy" else -1) * (amount_usd / current_price)
                        fees = amount_usd * 0.0004  # Approximate round-trip fees
                        net_pnl = gross_pnl - fees

                        # Update paper trading balance and PnL
                        ctx.balance_snapshot += net_pnl
                        ctx.state = update_pnl(ctx.state, net_pnl)
                        
                        # Notify paper trade result
                        direction = "📈" if net_pnl > 0 else "📉"
                        msg = (
                            f"{direction} <b>{sym}</b> {side.upper()}\n"
                            f"Entry: {current_price:.4f} → Exit: {exit_price:.4f}\n"
                            f"PnL: {net_pnl:.2f} USDT | Day: {ctx.state.pnl_today:.2f} USDT"
                        )
                        await send_message(msg)

                    # Save balance snapshot
                    save_balance(ctx.get_actual_balance())
                    
                    # Re-check if we can continue trading
                    can_trade = can_open_new_trades(ctx.state)
                    if not can_trade:
                        break  # Stop iterating symbols if we hit limits
                        
                except Exception as e:
                    log.warning(f"Error processing {sym}: {e}")
                    continue

            # Sleep between cycles
            await asyncio.sleep(SLEEP_SECONDS_BETWEEN_CYCLES)
            
        except Exception as e:
            log.exception(f"Main loop error: {e}")
            await send_message(f"⚠️ Error in main loop: {str(e)}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(trading_loop())
    except KeyboardInterrupt:
        log.info("Bot stopped by user")
    except Exception as e:
        log.exception(f"Fatal error: {e}")
