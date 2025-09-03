from __future__ import annotations
import asyncio
import logging
from src.config import (
    MODE, BINANCE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET, STARTING_BALANCE_USDT,
    POSITION_SIZE_PERCENT, DAILY_PROFIT_TARGET_USD, MAX_DAILY_LOSS_USD, TIMEFRAME, MAX_SYMBOLS,
    MIN_24H_VOLUME_USDT, SLEEP_SECONDS_BETWEEN_CYCLES, LOG_LEVEL, LEVERAGE, MARGIN_MODE, CAPITAL_MAX_USDT
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
        self.equity_usdt = STARTING_BALANCE_USDT if self.effective_mode == "paper" else max(STARTING_BALANCE_USDT, self.exchange.get_balance_usdt())
        self.om = OrderManager(self.exchange, self.get_equity)
        # Track last equity snapshot for live mode PnL tracking
        self.last_equity_snapshot = self.equity_usdt if MODE == "live" else None

    def get_equity(self) -> float:
        if self.effective_mode == "paper":
            return self.equity_usdt
        # Cap equity with CAPITAL_MAX_USDT for position sizing
        live_balance = max(0.0, self.exchange.get_balance_usdt())
        return min(live_balance, CAPITAL_MAX_USDT)

async def handle_command(text: str, ctx: Context):
    if text == "/status":
        plan = ctx.plan
        risk_status = ctx.guardrails.get_risk_status()
        msg = (f"Profile: {plan.profile_name}\n"
               f"Mode: {ctx.effective_mode} (plan: {plan.mode})\n"
               f"Equity: {ctx.get_equity():.2f} USDT\n"
               f"Daily PnL: {risk_status['daily_pnl']:.2f} USDT\n"
               f"Positions: {risk_status['current_positions']}/{risk_status['max_positions']}\n"
               f"Paused: {ctx.state.paused}")
        await send_message(msg)
    elif text == "/pause":
        ctx.state.paused = True
        save_state(ctx.state)
        await send_message("Bot pausado.")
    elif text == "/resume":
        ctx.state.paused = False
        save_state(ctx.state)
        await send_message("Bot reanudado.")
    elif text == "/refresh":
        ctx.universe_selector.force_refresh()
        await send_message("Universe refresh forced.")
    elif text == "/plan":
        plan = ctx.plan
        msg = (f"Plan: {plan.profile_name}\n"
               f"Mode: {plan.mode}\n"
               f"Universe: {plan.universe.mode}\n"
               f"Position size: {plan.risk.position_size_pct}%\n"
               f"Leverage: {plan.risk.leverage}x\n"
               f"Max positions: {plan.risk.max_concurrent_positions}")
        await send_message(msg)

async def trading_loop():
    _ensure_db()
    ctx = Context()

    # Load plan settings
    plan = ctx.plan
    log.info(f"Loaded plan '{plan.profile_name}' with mode '{plan.mode}' (effective: {ctx.effective_mode})")
    
    await send_message(f"🤖 Bot started - Plan: {plan.profile_name} ({ctx.effective_mode} mode)")
    
    # Get universe from plan-driven selector
    symbols = ctx.universe_selector.get_active_symbols(ctx.exchange)
    await send_message(f"Universe ({plan.universe.mode}): {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")

    # If live mode, set leverage and margin mode for each symbol using plan settings
    if ctx.effective_mode == "live":
        leverage = plan.risk.leverage
        margin_mode = plan.risk.margin_mode
        log.info(f"Setting leverage {leverage} and margin mode {margin_mode} for live trading")
        for sym in symbols:
            try:
                ctx.exchange.set_margin_mode(sym, margin_mode)
                ctx.exchange.set_leverage(sym, leverage)
                log.debug(f"Set {sym}: leverage={leverage}, margin_mode={margin_mode}")
            except Exception as e:
                log.warning(f"Failed to set leverage/margin for {sym}: {e}")

    async def commands_poller():
        async def _handle(cmd: str):
            await handle_command(cmd, ctx)
        await poll_commands(_handle)

    # Start command poller as concurrent task
    asyncio.create_task(commands_poller())

    # Refresh universe periodically based on plan settings
    last_universe_refresh = 0
    refresh_interval = plan.universe.dynamic_selector.refresh_interval_min * 60 if plan.universe.mode == "dynamic" else 3600

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
            
            # Refresh universe if needed
            import time
            now = time.time()
            if now - last_universe_refresh >= refresh_interval:
                symbols = ctx.universe_selector.get_active_symbols(ctx.exchange)
                log.info(f"Refreshed universe: {len(symbols)} symbols")
                last_universe_refresh = now

            for sym in symbols:
                if ctx.state.paused:
                    break
                    
                df = ctx.exchange.fetch_ohlcv_df(sym, timeframe=plan.universe.timeframe, limit=200)
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

                side = "buy" if sig == "buy" else "sell"
                
                # Get plan-driven position size and validate with guardrails
                plan_position_pct = ctx.plan_loader.get_position_size_pct()
                validated_position_pct = ctx.guardrails.validate_position_size(ctx.get_equity(), plan_position_pct * 100)
                position_size_usd = ctx.get_equity() * validated_position_pct
                
                # Check if trade should be opened based on guardrails
                trade_context = TradeContext(
                    symbol=sym,
                    side=side,
                    entry_price=px,
                    position_size_usd=position_size_usd,
                    equity_usd=ctx.get_equity(),
                    current_positions=ctx.guardrails.state.current_positions,
                    daily_pnl=ctx.guardrails.state.daily_pnl
                )
                
                check_result = ctx.guardrails.should_open_trade(trade_context)
                if not check_result['allowed']:
                    log.info(f"Trade blocked for {sym}: {check_result['reason']}")
                    continue

                # Open position
                order = ctx.om.open_position_market(sym, side, validated_position_pct, price_hint=px)

                if ctx.effective_mode == "live":
                    # Live mode: use bracket orders with SL/TP from plan
                    sl_pct = ctx.plan_loader.get_sl_pct()
                    tp_pct = ctx.plan_loader.get_tp_pct()
                    sl_price, tp_price = compute_sl_tp(px, side, sl_pct=sl_pct, tp_pct=tp_pct)
                    
                    # Compute amount in base from equity and price
                    amount = position_size_usd / px
                    
                    # Place bracket orders
                    ctx.om.place_brackets(sym, side, amount, sl_price, tp_price)
                    
                    # Update guardrails state
                    ctx.guardrails.on_trade_opened(trade_context)
                    
                    await send_message(f"{sym} {side.upper()} @ {px:.2f} | SL {sl_price:.2f} | TP {tp_price:.2f} | Size: {validated_position_pct*100:.1f}%")
                else:
                    # Paper mode: keep current simulated quick exit logic
                    await asyncio.sleep(2)
                    df2 = ctx.exchange.fetch_ohlcv_df(sym, timeframe=plan.universe.timeframe, limit=2)
                    if df2.empty:
                        continue
                    px2 = float(df2["close"].iloc[-1])
                    amount_usd = position_size_usd
                    gross_pnl = (px2 - px) * (1 if side == "buy" else -1) * (amount_usd / px)
                    fees = amount_usd * 0.0004  # ida+vuelta aprox
                    net_pnl = gross_pnl - fees

                    ctx.equity_usdt += net_pnl
                    ctx.state = update_pnl(ctx.state, net_pnl)
                    
                    # Update guardrails state
                    ctx.guardrails.on_trade_opened(trade_context)
                    ctx.guardrails.on_trade_closed(sym, net_pnl)
                    
                    await send_message(f"{sym} {side.upper()} @ {px:.2f} -> exit {px2:.2f} | PnL: {net_pnl:.2f} USDT | Daily: {ctx.guardrails.state.daily_pnl:.2f}")

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
