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
        # Testnet correcto en ccxt 4.x
        if self.testnet:
            self.exchange.set_sandbox_mode(True)

        self.exchange.load_markets()

    def _normalize_symbol(self, symbol: str) -> str:
        """
        Devuelve el símbolo preferido si existe en markets (p.ej. BTC/USDT:USDT),
        o el original como fallback.
        """
        markets = self.exchange.markets or {}
        if symbol in markets:
            return symbol
        # Intentos comunes de normalización para USDM
        if ":USDT" not in symbol and "/USDT" in symbol:
            candidate = symbol + ":USDT"
            if candidate in markets:
                return candidate
        # También intentar quitar sufijo si vino con :USDT y no existe
        if ":USDT" in symbol:
            candidate = symbol.replace(":USDT", "")
            if candidate in markets:
                return candidate
        return symbol

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
        filtered = []
        for s, v in rows:
            if v >= min_volume_usdt:
                norm = self._normalize_symbol(s)
                if norm not in filtered:
                    filtered.append(norm)
        if not filtered:
            # Fallback razonable y normalizado si existe
            for base in ["BTC/USDT:USDT", "BTC/USDT", "ETH/USDT:USDT", "ETH/USDT"]:
                fb = self._normalize_symbol(base)
                if fb not in filtered:
                    filtered.append(fb)
        return filtered[:limit]

    def fetch_ohlcv_df(self, symbol: str, timeframe: str = "1m", limit: int = 200) -> pd.DataFrame:
        sym = self._normalize_symbol(symbol)
        ohlcv = self.exchange.fetch_ohlcv(sym, timeframe=timeframe, limit=limit)
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
        sym = self._normalize_symbol(symbol)
        params = {"reduceOnly": True} if reduce_only else {}
        return self.exchange.create_order(symbol=sym, type="market", side=side, amount=amount, params=params)

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol. Returns True on success, False on failure."""
        try:
            sym = self._normalize_symbol(symbol)
            self.exchange.set_leverage(leverage, sym)
            log.info(f"Set leverage {leverage} for {sym}")
            return True
        except Exception as e:
            log.warning(f"Failed to set leverage {leverage} for {symbol}: {e}")
            return False

    def set_margin_mode(self, symbol: str, mode: str = "ISOLATED") -> bool:
        """Set margin mode for a symbol. Returns True on success, False on failure."""
        try:
            sym = self._normalize_symbol(symbol)
            self.exchange.set_margin_mode(mode, sym)
            log.info(f"Set margin mode {mode} for {sym}")
            return True
        except Exception as e:
            log.warning(f"Failed to set margin mode {mode} for {symbol}: {e}")
            return False