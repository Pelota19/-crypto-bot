from dataclasses import dataclass
from typing import Dict

@dataclass
class BotState:
    daily_pnl_usd: float = 0.0
    is_paused: bool = False
    open_positions: Dict[str, dict] = None

    def __post_init__(self):
        if self.open_positions is None:
            self.open_positions = {}

bot_state = BotState()
