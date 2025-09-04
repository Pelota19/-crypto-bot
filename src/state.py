"""
Bot state management module.
Tracks the current state of the trading bot including PnL and pause status.
"""
from dataclasses import dataclass, asdict
from typing import Dict
import json
from pathlib import Path
from datetime import datetime

STATE_FILE = Path("data/bot_state.json")

@dataclass
class BotState:
    """Bot state tracking daily PnL and pause status."""
    daily_pnl_usd: float = 0.0
    is_paused: bool = False
    open_positions: Dict[str, dict] = None
    last_reset_day: str = None  # YYYY-MM-DD

    def __post_init__(self):
        if self.open_positions is None:
            self.open_positions = {}
        if self.last_reset_day is None:
            self.last_reset_day = datetime.utcnow().strftime("%Y-%m-%d")


# Global bot state instance
bot_state = BotState()

# ---------------------
# Functions expected by bot
# ---------------------

def load_state() -> BotState:
    """Load state from file or return fresh instance."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            bot_state.daily_pnl_usd = data.get("daily_pnl_usd", 0.0)
            bot_state.is_paused = data.get("is_paused", False)
            bot_state.open_positions = data.get("open_positions", {})
            bot_state.last_reset_day = data.get("last_reset_day", datetime.utcnow().strftime("%Y-%m-%d"))
        except Exception:
            pass
    return bot_state

def save_state(state: BotState):
    """Save current state to file."""
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(asdict(state), indent=2))

def update_pnl(state: BotState, pnl_change: float) -> BotState:
    """Update daily PnL."""
    state.daily_pnl_usd += pnl_change
    return state

def reset_if_new_day(state: BotState) -> BotState:
    """Reset daily PnL if a new UTC day has started."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if state.last_reset_day != today:
        state.daily_pnl_usd = 0.0
        state.last_reset_day = today
        state.is_paused = False
    return state

def can_open_new_trades(state: BotState) -> bool:
    """Check if bot can open new trades."""
    if state.is_paused:
        return False
    # You can add limits based on daily drawdown, max trades, etc.
    return True
