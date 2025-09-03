from __future__ import annotations
import asyncio
import logging
from src.config import (
    MODE, BINANCE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET, STARTING_BALANCE_USDT,
    POSITION_SIZE_PERCENT, DAILY_PROFIT_TARGET_USD, MAX_DAILY_LOSS_USD, TIMEFRAME, MAX_SYMBOLS,
    MIN_24H_VOLUME_USDT, SLEEP_SECONDS_BETWEEN_CYCLES, LOG_LEVEL, LEVERAGE, MARGIN_MODE, CAPITAL_MAX_USDT
)
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
        self.exchange = BinanceFuturesClient(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=BINANCE_TESTNET)
        self.state = load_state()
        self.equity_usdt = STARTING_BALANCE_USDT if MODE == "paper" else max(STARTING_BALANCE_USDT, self.exchange.get_balance_usdt())
        self.om = OrderManager(self.exchange, self.get_equity)
        # Track last equity snapshot for live mode PnL tracking
        self.last_equity_snapshot = self.equity_usdt if MODE == "live" else None

    def get_equity(self) -> float:
        if MODE == "paper":
            return self.equity_usdt
        # Cap equity with CAPITAL_MAX_USDT for position sizing
        live_balance = max(0.0, self.exchange.get_balance_usdt())
        return min(live_balance, CAPITAL_MAX_USDT)

async def handle_command(text: str, ctx: Context):
    if text == "/status":
        msg = f"Mode: {MODE}\nEquity: {ctx.get_equity():.2f} USDT (capped at {CAPITAL_MAX_USDT:.0f})\nPNL hoy: {ctx.state.pnl_today:.2f}\nTarget: {DAILY_PROFIT_TARGET_USD:.2f} | MaxLoss: {MAX_DAILY_LOSS_USD:.2f}\nPausado: {ctx.state.paused}"
        await send_message(msg)
    elif text == "/pause":
        ctx.state.paused = True
        save_state(ctx.state)
        await send_message("Bot pausado.")
    elif text == "/resume":
        ctx.state.paused = False
        save_state(ctx.state)
        await send_message("Bot reanudado.")

async def trading_loop():
    _ensure_db()
    ctx = Context()

    await send_message("🤖 Bot iniciado en testnet.")
    symbols = ctx.exchange.get_usdt_perp_symbols(MIN_24H_VOLUME_USDT, MAX_SYMBOLS)
    await send_message(f"Universo: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")

    # If live mode, set leverage and margin mode for each symbol with error handling
    if MODE == "live":
        log.info(f"Setting leverage {LEVERAGE} and margin mode {MARGIN_MODE} for live trading")
        for sym in symbols:
            try:
                ctx.exchange.set_margin_mode(sym, MARGIN_MODE)
                await asyncio.sleep(0.1)  # Small delay to avoid rate limits
                ctx.exchange.set_leverage(sym, LEVERAGE)
                await asyncio.sleep(0.1)  # Small delay to avoid rate limits
            except Exception as e:
                log.warning(f"Failed to set leverage/margin for {sym}: {e}")

    # Daily target tracking variables
    daily_target_notified = False

    async def commands_poller():
        async def _handle(cmd: str):
            await handle_command(cmd, ctx)
        await poll_commands(_handle)

    # Start command poller as concurrent task
    asyncio.create_task(commands_poller())

    while True:
        try:
            ctx.state = reset_if_new_day(ctx.state)
            
            # Reset daily target notification on new day
            if ctx.state.pnl_today == 0.0:
                daily_target_notified = False
            
            # Update PnL in live mode
            if MODE == "live" and ctx.last_equity_snapshot is not None:
                current_equity = ctx.exchange.get_balance_usdt()
                pnl_delta = current_equity - ctx.last_equity_snapshot
                if abs(pnl_delta) > 0.01:  # Only update if significant change
                    ctx.state = update_pnl(ctx.state, pnl_delta)
                    ctx.last_equity_snapshot = current_equity
            
            can_trade = can_open_new_trades(ctx.state)
            
            # Check if daily targets reached and send single notification
            if not daily_target_notified and (
                ctx.state.pnl_today >= DAILY_PROFIT_TARGET_USD or 
                ctx.state.pnl_today <= -MAX_DAILY_LOSS_USD
            ):
                if ctx.state.pnl_today >= DAILY_PROFIT_TARGET_USD:
                    await send_message(f"🎯 Daily profit target reached: {ctx.state.pnl_today:.2f} USDT. Trading paused for today.")
                else:
                    await send_message(f"🚨 Daily loss limit reached: {ctx.state.pnl_today:.2f} USDT. Trading paused for today.")
                daily_target_notified = True

            for sym in symbols:
                if not can_trade:
                    break
                    
                df = ctx.exchange.fetch_ohlcv_df(sym, timeframe=TIMEFRAME, limit=200)
                if df.empty or len(df) < 30:
                    continue

                px = float(df["close"].iloc[-1])
                
                # Use decide_trade to get signal, sl, tp, and score
                trade_decision = decide_trade(df)
                signal = trade_decision["signal"]
                sl_price = trade_decision["sl"]
                tp_price = trade_decision["tp"]
                score = trade_decision["score"]
                
                if signal == "hold":
                    continue

                # Check trade feasibility before attempting
                notional = ctx.get_equity() * POSITION_SIZE_PERCENT
                if not ctx.exchange.is_trade_feasible(sym, notional, px):
                    log.debug(f"Trade not feasible for {sym}: notional={notional:.2f}, price={px:.4f}")
                    continue

                side = "buy" if signal == "buy" else "sell"
                order = ctx.om.open_position_market(sym, side, POSITION_SIZE_PERCENT, price_hint=px)
                
                if order is None:
                    continue  # Skip if order couldn't be placed

                if MODE == "live":
                    # Use returned order amount or fallback to sizing for brackets
                    order_amount = float(order.get("amount", notional / px))
                    
                    # Place bracket orders using OrderManager
                    bracket_result = ctx.om.place_brackets(sym, side, order_amount, sl_price, tp_price)
                    
                    if bracket_result:
                        await send_message(f"🔄 {sym} {side.upper()} @ {px:.4f} | SL {sl_price:.4f} | TP {tp_price:.4f} | Score: {score:.3f}")
                    else:
                        await send_message(f"🔄 {sym} {side.upper()} @ {px:.4f} (brackets failed)")
                else:
                    # Paper mode: keep current simulated quick exit logic
                    await asyncio.sleep(2)
                    df2 = ctx.exchange.fetch_ohlcv_df(sym, timeframe=TIMEFRAME, limit=2)
                    if df2.empty:
                        continue
                    px2 = float(df2["close"].iloc[-1])
                    amount_usd = ctx.get_equity() * POSITION_SIZE_PERCENT
                    gross_pnl = (px2 - px) * (1 if side == "buy" else -1) * (amount_usd / px)
                    fees = amount_usd * 0.0004  # ida+vuelta aprox
                    net_pnl = gross_pnl - fees

                    ctx.equity_usdt += net_pnl
                    ctx.state = update_pnl(ctx.state, net_pnl)
                    
                    await send_message(f"📊 {sym} {side.upper()} @ {px:.4f} -> exit {px2:.4f} | PnL: {net_pnl:.2f} USDT | Day PnL: {ctx.state.pnl_today:.2f}")

                save_balance(ctx.get_equity())
                can_trade = can_open_new_trades(ctx.state)

            await asyncio.sleep(SLEEP_SECONDS_BETWEEN_CYCLES)
        except Exception as e:
            log.exception(f"Loop error: {e}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    try:
        asyncio.run(trading_loop())
    except KeyboardInterrupt:
        log.info("Stopping...")
