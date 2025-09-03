from __future__ import annotations
import asyncio
import logging
from typing import List

from src.config import (
    MODE, BINANCE_TESTNET, BINANCE_API_KEY, BINANCE_API_SECRET, STARTING_BALANCE_USDT,
    POSITION_SIZE_PERCENT, TIMEFRAME, MAX_SYMBOLS, MIN_24H_VOLUME_USDT,
    SLEEP_SECONDS_BETWEEN_CYCLES, LOG_LEVEL, LEVERAGE, MARGIN_MODE,
    MAX_ACTIVE_SYMBOLS, TOP_K_SELECTION
)
from src.exchange.binance_client import BinanceFuturesClient
from src.orders.manager import OrderManager
from src.persistence.sqlite_store import save_balance
from src.telegram.console import send_message, poll_commands
from src.pair_selector import PairSelector
from src.strategy.strategy import decide_trade as strat_decide_trade

logger = logging.getLogger("crypto_bot")


class Context:
    def __init__(self):
        self.exchange = BinanceFuturesClient(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=BINANCE_TESTNET)
        self.equity_usdt = STARTING_BALANCE_USDT if MODE == "paper" else max(
            STARTING_BALANCE_USDT, self.exchange.get_balance_usdt()
        )
        self.om = OrderManager()
        self.pair_selector = PairSelector(self.exchange, self.get_equity)

    def get_equity(self) -> float:
        if MODE == "paper":
            return float(self.equity_usdt)
        # Live: consult exchange
        bal = self.exchange.get_balance_usdt()
        return bal if bal > 0 else float(self.equity_usdt)


def amount_in_base(notional_usd: float, price: float) -> float:
    if price <= 0:
        return 0.0
    return notional_usd / price


async def handle_command(text: str, ctx: Context):
    """Handle telegram command."""
    if text == "/status":
        msg = f"Mode: {MODE}\nEquity: {ctx.get_equity():.2f} USDT\nTop-K: {TOP_K_SELECTION} (max {MAX_ACTIVE_SYMBOLS})"
        await send_message(msg)
    elif text == "/pause":
        await send_message("Bot pausado (no state management implemented).")
    elif text == "/resume":
        await send_message("Bot reanudado (no state management implemented).")


async def main():
    """Main bot loop."""
    # Configure logging
    logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.WARNING))
    
    ctx = Context()
    
    # Load markets
    try:
        ctx.exchange.load_markets()
        logger.info("Markets loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load markets: {e}")
        return

    # Start command poller task
    async def commands_poller():
        async def _handle(cmd: str):
            await handle_command(cmd, ctx)
        await poll_commands(_handle)

    asyncio.create_task(commands_poller())
    
    await send_message(f"Bot started in {MODE} mode with equity {ctx.get_equity():.2f} USDT")

    while True:
        try:
            # Get universe of USDT perpetuals
            try:
                symbols = ctx.exchange.get_usdt_perp_symbols(MIN_24H_VOLUME_USDT, MAX_SYMBOLS)
                if not symbols:
                    logger.warning("No symbols found, retrying in next cycle")
                    await asyncio.sleep(SLEEP_SECONDS_BETWEEN_CYCLES)
                    continue
                    
                logger.info(f"Found {len(symbols)} symbols: {symbols[:5]}...")
            except Exception as e:
                logger.error(f"Failed to get symbols: {e}")
                await asyncio.sleep(SLEEP_SECONDS_BETWEEN_CYCLES)
                continue

            # In live mode, set leverage and margin mode for each symbol
            if MODE == "live":
                logger.info(f"Setting leverage {LEVERAGE} and margin mode {MARGIN_MODE} for live trading")
                for sym in symbols:
                    try:
                        ctx.exchange.set_margin_mode(sym, MARGIN_MODE)
                        ctx.exchange.set_leverage(sym, LEVERAGE)
                    except Exception as e:
                        logger.warning(f"Failed to set leverage/margin for {sym}: {e}")

            # Use top-K selection if enabled, otherwise use legacy behavior
            if TOP_K_SELECTION:
                # Get top K symbols using new selection logic
                try:
                    selected_candidates = ctx.pair_selector.select_top_symbols(
                        symbols, POSITION_SIZE_PERCENT, MAX_ACTIVE_SYMBOLS
                    )
                    
                    # Send single Telegram message with selection summary
                    summary = ctx.pair_selector.format_selection_summary(selected_candidates, len(symbols))
                    if selected_candidates:  # Only send if we have selections
                        await send_message(summary)
                    
                    # Trade only the selected symbols
                    for candidate in selected_candidates:
                        sym = candidate.symbol
                        side = "buy" if candidate.signal == "buy" else "sell"
                        px = candidate.last_price
                        
                        if MODE == "live":
                            # Live mode: place market entry and attach bracket orders
                            sl_price = candidate.sl
                            tp_price = candidate.tp
                            
                            # Compute amount in base from equity and price
                            notional_usd = ctx.get_equity() * POSITION_SIZE_PERCENT
                            amount = amount_in_base(notional_usd, px)
                            
                            # Place market order
                            try:
                                market_order = ctx.exchange.market_order(sym, side, amount, price_hint=px)
                                if market_order:
                                    logger.info(f"Market order placed: {market_order}")
                                    
                                    # Place stop loss (reduce only)
                                    sl_side = "sell" if side == "buy" else "buy"
                                    sl_order = ctx.exchange.stop_market_reduce_only(sym, sl_side, amount, sl_price)
                                    
                                    # Place take profit (reduce only)  
                                    tp_order = ctx.exchange.take_profit_market_reduce_only(sym, sl_side, amount, tp_price)
                                    
                                    await send_message(f"{sym} {side.upper()} @ {px:.2f} | SL {sl_price:.2f} | TP {tp_price:.2f}")
                                else:
                                    logger.warning(f"Failed to place market order for {sym}")
                            except Exception as e:
                                logger.error(f"Live trading error for {sym}: {e}")
                        else:
                            # Paper mode: simulate a quick exit after a short delay
                            await asyncio.sleep(2)
                            try:
                                df2 = ctx.exchange.fetch_ohlcv_df(sym, timeframe=TIMEFRAME, limit=2)
                                if df2.empty:
                                    continue
                                px2 = float(df2["close"].iloc[-1])
                                notional_usd = ctx.get_equity() * POSITION_SIZE_PERCENT
                                gross_pnl = (px2 - px) * (1 if side == "buy" else -1) * amount_in_base(notional_usd, px)
                                fees = notional_usd * 0.0004  # ida+vuelta aprox
                                net_pnl = gross_pnl - fees

                                ctx.equity_usdt += net_pnl
                                
                                await send_message(f"{sym} {side.upper()} @ {px:.2f} -> exit {px2:.2f} | PnL: {net_pnl:.2f} USDT | Equity: {ctx.equity_usdt:.2f}")
                            except Exception as e:
                                logger.error(f"Paper trading error for {sym}: {e}")

                        # Persist balance
                        try:
                            save_balance(ctx.get_equity())
                        except Exception as e:
                            logger.error(f"Failed to save balance: {e}")
                            
                except Exception as e:
                    logger.error(f"Top-K selection failed: {e}")
                    
            else:
                # Legacy behavior: iterate through all symbols
                for sym in symbols:
                    try:
                        df = ctx.exchange.fetch_ohlcv_df(sym, timeframe=TIMEFRAME, limit=200)
                        if df.empty or len(df) < 30:
                            continue

                        px = float(df["close"].iloc[-1])
                        
                        # Use strategy to decide trade
                        trade_decision = strat_decide_trade(df)
                        sig = trade_decision.get("signal", "hold")
                        
                        if sig == "hold":
                            continue

                        side = "buy" if sig == "buy" else "sell"
                        
                        if MODE == "live":
                            # Live mode: use bracket orders with SL/TP
                            sl_price = trade_decision.get("sl", px * (0.998 if side == "buy" else 1.002))
                            tp_price = trade_decision.get("tp", px * (1.004 if side == "buy" else 0.996))
                            
                            # Compute amount in base from equity and price
                            notional_usd = ctx.get_equity() * POSITION_SIZE_PERCENT
                            amount = amount_in_base(notional_usd, px)
                            
                            # Place market order
                            try:
                                market_order = ctx.exchange.market_order(sym, side, amount, price_hint=px)
                                if market_order:
                                    logger.info(f"Market order placed: {market_order}")
                                    
                                    # Place stop loss (reduce only)
                                    sl_side = "sell" if side == "buy" else "buy"
                                    sl_order = ctx.exchange.stop_market_reduce_only(sym, sl_side, amount, sl_price)
                                    
                                    # Place take profit (reduce only)  
                                    tp_order = ctx.exchange.take_profit_market_reduce_only(sym, sl_side, amount, tp_price)
                                    
                                    await send_message(f"{sym} {side.upper()} @ {px:.2f} | SL {sl_price:.2f} | TP {tp_price:.2f}")
                                else:
                                    logger.warning(f"Failed to place market order for {sym}")
                            except Exception as e:
                                logger.error(f"Live trading error for {sym}: {e}")
                        else:
                            # Paper mode: simulated quick exit logic
                            await asyncio.sleep(2)
                            try:
                                df2 = ctx.exchange.fetch_ohlcv_df(sym, timeframe=TIMEFRAME, limit=2)
                                if df2.empty:
                                    continue
                                px2 = float(df2["close"].iloc[-1])
                                notional_usd = ctx.get_equity() * POSITION_SIZE_PERCENT
                                gross_pnl = (px2 - px) * (1 if side == "buy" else -1) * amount_in_base(notional_usd, px)
                                fees = notional_usd * 0.0004  # ida+vuelta aprox
                                net_pnl = gross_pnl - fees

                                ctx.equity_usdt += net_pnl
                                
                                await send_message(f"{sym} {side.upper()} @ {px:.2f} -> exit {px2:.2f} | PnL: {net_pnl:.2f} USDT | Equity: {ctx.equity_usdt:.2f}")
                            except Exception as e:
                                logger.error(f"Paper trading error for {sym}: {e}")

                        # Persist balance
                        try:
                            save_balance(ctx.get_equity())
                        except Exception as e:
                            logger.error(f"Failed to save balance: {e}")
                            
                    except Exception as e:
                        logger.error(f"Symbol processing error for {sym}: {e}")

            await asyncio.sleep(SLEEP_SECONDS_BETWEEN_CYCLES)
            
        except Exception as e:
            logger.exception(f"Main loop error: {e}")
            await asyncio.sleep(SLEEP_SECONDS_BETWEEN_CYCLES)


if __name__ == "__main__":
    logger.info("Starting crypto bot")
    asyncio.run(main())