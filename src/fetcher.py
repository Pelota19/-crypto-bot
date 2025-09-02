import pandas as pd
import logging

logger = logging.getLogger(__name__)


async def fetch_ohlcv_for_symbol(
    exchange, symbol: str, timeframe: str = "1h", limit: int = 200
):
    """
    Returns a DataFrame with columns: ['timestamp','open','high','low','close','volume']
    """
    try:
        raw = await exchange.fetch_ohlcv(
            symbol, timeframe=timeframe, since=None, limit=limit
        )
        if not raw:
            return pd.DataFrame()
        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        # convert timestamp (ms) to datetime index optional
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        logger.exception("Failed to fetch ohlcv for %s: %s", symbol, e)
        return pd.DataFrame()
