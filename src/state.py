"""
Bot state management module.
Tracks the current state of the trading bot including PnL and pause status.
"""
from dataclasses import dataclass
from typing import Dict


@dataclass
class BotState:
    """Bot state tracking daily PnL and pause status."""
    daily_pnl_usd: float = 0.0
    is_paused: bool = False
    open_positions: Dict[str, dict] = None
    
    def __post_init__(self):
        if self.open_positions is None:
            self.open_positions = {}


# Global bot state instance
bot_state = BotState()