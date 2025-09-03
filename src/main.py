from __future__ import annotations
import asyncio
import logging
from src.config import (
    MODE, BINANCE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET, STARTING_BALANCE_USDT,
    POSITION_SIZE_PERCENT, DAILY_PROFIT_TARGET_USD, MAX_DAILY_LOSS_USD, TIMEFRAME, MAX_SYMBOLS,
    MIN_24H_VOLUME_USDT, SLEEP_SECONDS_BETWEEN_CYCLES, LOG_LEVEL, LEVERAGE, MARGIN_MODE,
    MAX_ACTIVE_SYMBOLS, TOP_K_SELECTION
)
from src.exchange.binance_client import BinanceFuturesClient
from src.strategy.strategy import decide_signal, decide_trade
from src.state import load_state, save_state, reset_if_new_day, can_open_new_trades, update_pnl
from src.orders.manager import OrderManager
from src.persistence.sqlite_store import save_balance, _ensure_db
from src.telegram.console import send_message, poll_commands
from src.risk.manager import compute_sl_tp
from src.pair_selector import PairSelector

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("main")

class Context:
    def __init__(self):
        self.exchange = BinanceFuturesClient(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=BINANCE_TESTNET)
        self.state = load_state()
        self.equity_usdt = STARTING_BALANCE_USDT if MODE == "paper" else max(STARTING_BALANCE_USDT, self.exchange.get_balance_usdt())
        self.om = OrderManager(self.exchange, self.get_equity)
        self.pair_selector = PairSelector(self.exchange, self.get_equity)

    def get_equity(self) -> float:
        if MODE == "paper":
            return self.equity_usdt
        return max(0.0, self.exchange.get_balance_usdt())

async def handle_command(text: str, ctx: Context):
    if text == "/status":
        msg = f"Mode: {MODE}\nEquity: {ctx.get_equity():.2f} USDT\nPNL hoy: {ctx.state.pnl_today:.2f}\nTarget: {DAILY_PROFIT_TARGET_USD:.2f} | MaxLoss: {MAX_DAILY_LOSS_USD:.2f}\nPausado: {ctx.state.paused}"
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

            if not can_trade:
                log.debug("Cannot trade (daily limits or paused)")
                await asyncio.sleep(SLEEP_SECONDS_BETWEEN_CYCLES)
                continue

            # Use top-K selection if enabled, otherwise use legacy behavior
            if TOP_K_SELECTION:
                # Get top K symbols using new selection logic
                selected_candidates = ctx.pair_selector.select_top_symbols(
                    symbols, POSITION_SIZE_PERCENT, MAX_ACTIVE_SYMBOLS
                )
                
                # Send single Telegram message with selection summary
                summary = ctx.pair_selector.format_selection_summary(selected_candidates, len(symbols))
                if selected_candidates:  # Only send if we have selections
                    await send_message(summary)
                
                # Trade only the selected symbols
                for candidate in selected_candidates:
                    if not can_open_new_trades(ctx.state):
                        break
                    
                    sym = candidate.symbol
                    side = "buy" if candidate.signal == "buy" else "sell"
                    px = candidate.last_price
                    
                    order = ctx.om.open_position_market(sym, side, POSITION_SIZE_PERCENT, price_hint=px)

                    if MODE == "live":
                        # Live mode: use bracket orders with SL/TP from strategy
                        sl_price = candidate.sl
                        tp_price = candidate.tp
                        # Compute amount in base from equity and price
                        amount = (ctx.get_equity() * POSITION_SIZE_PERCENT) / px
                        # Place bracket orders
                        ctx.om.place_brackets(sym, side, amount, sl_price, tp_price)
                        
                        await send_message(f"{sym} {side.upper()} @ {px:.2f} | SL {sl_price:.2f} | TP {tp_price:.2f}")
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
                        
                        await send_message(f"{sym} {side.upper()} @ {px:.2f} -> exit {px2:.2f} | PnL: {net_pnl:.2f} USDT | PnL día: {ctx.state.pnl_today:.2f}")

                    save_balance(ctx.get_equity())
                    
            else:
                # Legacy behavior: iterate through all symbols
                for sym in symbols:
                    df = ctx.exchange.fetch_ohlcv_df(sym, timeframe=TIMEFRAME, limit=200)
                    if df.empty or len(df) < 30:
                        continue

                    px = float(df["close"].iloc[-1])
                    sig = decide_signal(df)
                    if not can_trade or sig == "hold":
                        continue

                    side = "buy" if sig == "buy" else "sell"
                    order = ctx.om.open_position_market(sym, side, POSITION_SIZE_PERCENT, price_hint=px)

                    if MODE == "live":
                        # Live mode: use bracket orders with SL/TP
                        sl_price, tp_price = compute_sl_tp(px, side, sl_pct=0.002, tp_pct=0.004)
                        # Compute amount in base from equity and price
                        amount = (ctx.get_equity() * POSITION_SIZE_PERCENT) / px
                        # Place bracket orders
                        ctx.om.place_brackets(sym, side, amount, sl_price, tp_price)
                        
                        await send_message(f"{sym} {side.upper()} @ {px:.2f} | SL {sl_price:.2f} | TP {tp_price:.2f}")
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
                        
                        await send_message(f"{sym} {side.upper()} @ {px:.2f} -> exit {px2:.2f} | PnL: {net_pnl:.2f} USDT | PnL día: {ctx.state.pnl_today:.2f}")

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
