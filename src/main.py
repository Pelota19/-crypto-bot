from __future__ import annotations
import asyncio
import logging
from src.config import (
    MODE, BINANCE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET, STARTING_BALANCE_USDT,
    POSITION_SIZE_PERCENT, DAILY_PROFIT_TARGET_USD, MAX_DAILY_LOSS_USD, TIMEFRAME, MAX_SYMBOLS,
    MIN_24H_VOLUME_USDT, SLEEP_SECONDS_BETWEEN_CYCLES, LOG_LEVEL, LEVERAGE, MARGIN_MODE,
    CAPITAL_MAX_USDT
)
from src.exchange.binance_client import BinanceFuturesClient
from src.strategy.strategy import decide_trade
from src.state import load_state, save_state, reset_if_new_day, can_open_new_trades, update_pnl
from src.orders.manager import OrderManager
from src.persistence.sqlite_store import save_balance, _ensure_db
from src.telegram.console import send_message, poll_commands
from src.risk.manager import compute_sl_tp

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")

class Context:
    def __init__(self):
        self.exchange = BinanceFuturesClient(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=BINANCE_TESTNET)
        self.state = load_state()
        self.equity_usdt = STARTING_BALANCE_USDT if MODE == "paper" else max(STARTING_BALANCE_USDT, self.exchange.get_balance_usdt())
        self.om = OrderManager(self.exchange, self.get_equity)

    def get_equity(self) -> float:
        if MODE == "paper":
            equity = self.equity_usdt
        else:
            equity = max(0.0, self.exchange.get_balance_usdt())
        # Enforce capital cap for sizing calculations
        return min(equity, CAPITAL_MAX_USDT)

async def handle_command(text: str, ctx: Context):
    if text == "/status":
        msg = f"🤖 <b>Bot Status</b>\nMode: {MODE}\nCapital Cap: {CAPITAL_MAX_USDT} USDT\nEffective Equity: {ctx.get_equity():.2f} USDT\nPNL Today: {ctx.state.pnl_today:.2f} USDT\nTarget: +{DAILY_PROFIT_TARGET_USD:.2f} | Max Loss: -{MAX_DAILY_LOSS_USD:.2f}\nPaused: {'Yes' if ctx.state.paused else 'No'}"
        await send_message(msg)
    elif text == "/pause":
        ctx.state.paused = True
        save_state(ctx.state)
        await send_message("⏸️ Bot paused.")
    elif text == "/resume":
        ctx.state.paused = False
        save_state(ctx.state)
        await send_message("▶️ Bot resumed.")

async def trading_loop():
    _ensure_db()
    ctx = Context()

    await send_message(f"🤖 <b>Crypto Scalping Bot Started</b>\nMode: {MODE} ({'testnet' if BINANCE_TESTNET else 'live'})\nCapital Cap: {CAPITAL_MAX_USDT} USDT\nEffective Equity: {ctx.get_equity():.2f} USDT")
    symbols = ctx.exchange.get_usdt_perp_symbols(MIN_24H_VOLUME_USDT, MAX_SYMBOLS)
    await send_message(f"📈 <b>Trading Universe ({len(symbols)} symbols)</b>\n{', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")

    # If live mode, set leverage and margin mode for each symbol
    if MODE == "live":
        log.info(f"Setting leverage {LEVERAGE} and margin mode {MARGIN_MODE} for live trading")
        for sym in symbols:
            ctx.exchange.set_margin_mode(sym, MARGIN_MODE)
            ctx.exchange.set_leverage(sym, LEVERAGE)

    async def commands_poller():
        async def _handle(cmd: str):
            await handle_command(cmd, ctx)
        await poll_commands(_handle)

    asyncio.create_task(commands_poller())

    while True:
        try:
            ctx.state = reset_if_new_day(ctx.state)
            can_trade = can_open_new_trades(ctx.state)

            for sym in symbols:
                df = ctx.exchange.fetch_ohlcv_df(sym, timeframe=TIMEFRAME, limit=200)
                if df.empty or len(df) < 30:
                    continue

                px = float(df["close"].iloc[-1])
                
                # Use comprehensive decide_trade function
                trade_decision = decide_trade(df)
                sig = trade_decision["signal"]
                score = trade_decision["score"]
                
                if not can_trade or sig == "hold":
                    continue

                # Check trade feasibility before opening
                notional_usd = ctx.get_equity() * POSITION_SIZE_PERCENT
                if not ctx.exchange.is_trade_feasible(sym, notional_usd, px):
                    log.warning(f"Trade not feasible for {sym} with notional {notional_usd:.2f} USDT")
                    continue

                side = "buy" if sig == "buy" else "sell"
                
                try:
                    order = ctx.om.open_position_market(sym, side, POSITION_SIZE_PERCENT, price_hint=px)
                    if not order:
                        continue

                    if MODE == "live":
                        # Live mode: use bracket orders with SL/TP from strategy
                        sl_price = trade_decision["sl"]
                        tp_price = trade_decision["tp"]
                        
                        # Compute amount in base from equity and price
                        amount = (ctx.get_equity() * POSITION_SIZE_PERCENT) / px
                        
                        # Place bracket orders
                        brackets = ctx.om.place_brackets(sym, side, amount, sl_price, tp_price)
                        
                        await send_message(f"🎯 <b>{sym}</b> {side.upper()} @ {px:.4f}\nSize: {amount:.6f} | Score: {score:.3f}\nSL: {sl_price:.4f} | TP: {tp_price:.4f}")
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
                        
                        await send_message(f"📊 <b>{sym}</b> {side.upper()} @ {px:.4f} → exit {px2:.4f}\nPnL: {net_pnl:.2f} USDT | Daily PnL: {ctx.state.pnl_today:.2f} USDT")

                    save_balance(ctx.get_equity())

                    # Check if daily targets reached
                    if ctx.state.pnl_today >= DAILY_PROFIT_TARGET_USD:
                        await send_message(f"🎉 <b>Daily Profit Target Reached!</b>\nTarget: +{DAILY_PROFIT_TARGET_USD} USDT\nActual: +{ctx.state.pnl_today:.2f} USDT\nStopping new trades until tomorrow.")
                    elif ctx.state.pnl_today <= -MAX_DAILY_LOSS_USD:
                        await send_message(f"🛑 <b>Daily Loss Limit Reached!</b>\nLimit: -{MAX_DAILY_LOSS_USD} USDT\nActual: {ctx.state.pnl_today:.2f} USDT\nStopping new trades until tomorrow.")

                    can_trade = can_open_new_trades(ctx.state)
                
                except Exception as e:
                    log.warning(f"Trade execution failed for {sym}: {e}")
                    continue

            await asyncio.sleep(SLEEP_SECONDS_BETWEEN_CYCLES)
        except Exception as e:
            log.exception(f"Loop error: {e}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    try:
        asyncio.run(trading_loop())
    except KeyboardInterrupt:
        log.info("Stopping...")
