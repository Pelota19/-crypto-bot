# src/state.py
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class BotState:
    """Estado global del bot"""
    daily_pnl_usdt: float = 0.0
    is_paused: bool = False
    open_positions: Dict[str, dict] = field(default_factory=dict)

# Instancia global que importará todo el proyecto
bot_state = BotState()
