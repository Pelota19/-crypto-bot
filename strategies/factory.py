"""Strategy factory for creating strategy instances."""
from .scalping_ema_rsi import ScalpingEmaRsiStrategy
from utils.logger import get_logger

logger = get_logger(__name__)

def create_strategy(strategy_name: str):
    """Create and return a strategy instance."""
    strategies = {
        "scalping_ema_rsi": ScalpingEmaRsiStrategy,
    }
    
    strategy_class = strategies.get(strategy_name.lower())
    if not strategy_class:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    
    return strategy_class()