from __future__ import annotations
import logging
from typing import List, Dict, Any
import ccxt
import pandas as pd

log = logging.getLogger(__name__)

class BinanceFuturesClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.testnet = testnet
        self.exchange = ccxt.binanceusdm({
            "apiKey": api_key,
            "secret": api_secret,
            "options": {"defaultType": "future"},
            "enableRateLimit": True,
            "timeout": 20000,
        })
        # Ajuste de endpoint para testnet de futuros
        if self.testnet:
            # ccxt no usa set_sandbox_mode para futuros; redirigimos manualmente
            self.exchange.urls["api"]["fapi"] = "https://testnet.binancefuture.com/fapi"
        self.exchange.load_markets()

    def get_usdt_perp_symbols(self, min_volume_usdt: float, limit: int) -> List[str]:
        # Usamos fetch_tickers y filtramos swaps USDT
        tickers = self.exchange.fetch_tickers()
        rows = []
        for sym, t in tickers.items():
            market = self.exchange.markets.get(sym)
            if not market:
                continue
            if not market.get("swap"):
                continue
            if market.get("quote") != "USDT":
                continue
            vol_quote = t.get("quoteVolume") or t.get("baseVolume")
            if vol_quote is None:
                continue
            rows.append((sym, float(vol_quote)))
        rows.sort(key=lambda x: x[1], reverse=True)
        filtered = [s for s, v in rows if v >= min_volume_usdt]
        if not filtered:
            # Fallback razonable
            filtered = ["BTC/USDT", "ETH/USDT"]
        return filtered[:limit]

    def fetch_ohlcv_df(self, symbol: str, timeframe: str = "1m", limit: int = 200) -> pd.DataFrame:
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv:
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df

    def get_balance_usdt(self) -> float:
        try:
            bal = self.exchange.fetch_balance()
            if "USDT" in bal.get("total", {}):
                return float(bal["total"]["USDT"])
            return float(bal.get("USDT", {}).get("total", 0.0))
        except Exception as e:
            log.warning(f"fetch_balance failed: {e}")
            return 0.0

    def market_order(self, symbol: str, side: str, amount: float, reduce_only: bool = False) -> Dict[str, Any]:
        params = {"reduceOnly": True} if reduce_only else {}
        return self.exchange.create_order(symbol=symbol, type="market", side=side, amount=amount, params=params)
