import datetime
import logging

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, daily_profit_target=50.0):
        self.open_positions = {}   # dict {symbol: {"side": "long/short", "entry": float, "size": float, "sl": float, "tp": float}}
        self.realized_pnl_today = 0.0
        self.daily_profit_target = daily_profit_target
        self.last_reset_date = datetime.datetime.utcnow().date()

    def reset_daily_if_needed(self):
        today = datetime.datetime.utcnow().date()
        if today != self.last_reset_date:
            logger.info("Reset diario del PnL")
            self.realized_pnl_today = 0.0
            self.last_reset_date = today

    def can_open_new_trade(self):
        """ Verifica si se puede abrir una nueva operación """
        self.reset_daily_if_needed()
        if self.realized_pnl_today >= self.daily_profit_target:
            logger.info("Objetivo de profit diario alcanzado. No se abrirán nuevas operaciones.")
            return False
        return True

    def register_open_position(self, symbol, side, entry, size, sl, tp):
        self.open_positions[symbol] = {
            "side": side,
            "entry": entry,
            "size": size,
            "sl": sl,
            "tp": tp
        }
        logger.info(f"📌 Nueva posición abierta en {symbol}: {side} {size} @ {entry}, SL {sl}, TP {tp}")

    def register_closed_position(self, symbol, pnl):
        if symbol in self.open_positions:
            del self.open_positions[symbol]
        self.realized_pnl_today += pnl
        logger.info(f"✅ Operación cerrada en {symbol} con PnL: {pnl:.2f} USDT (Total diario: {self.realized_pnl_today:.2f})")
