"""
Minimal robust async wrapper around ccxt.async_support.binance used by the bot.

Exposes the methods the bot expects:
- fetch_all_symbols()
- fetch_ticker(symbol)
- fetch_ohlcv(symbol, timeframe, limit)  <-- robust: catches -1122 and network errors and returns None
- create_order(symbol, type, side, amount, price=None, params=None)
- fetch_open_orders(symbol=None)
- fetch_order(order_id, symbol=None)
- close()

This file is intended to replace/standalone the previous client implementation if you want a
clean, defensive wrapper that works with CCXT async binance. Adjust API URLs / options if your
environment requires different testnet endpoints.
"""
import logging
from typing import Optional, Any, List

import ccxt.async_support as ccxt
from ccxt.base.errors import BadRequest, ExchangeError, NetworkError, RequestTimeout

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(self, api_key: str = None, api_secret: str = None, use_testnet: bool = False, dry_run: bool = False):
        """
        api_key, api_secret: credentials (can be None for public endpoints)
        use_testnet: if True, configure the client for Binance Futures testnet (best-effort)
        dry_run: if True, create_order will not actually submit to exchange (simulated)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.use_testnet = use_testnet
        self.dry_run = dry_run
        self.exchange = None
        self._initialized = False

    async def _ensure_exchange(self):
        if self._initialized and self.exchange:
            return
        # Create ccxt async binance instance with futures defaultType
        params = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',  # USDT-M futures
            }
        }
        # If you want to enforce the testnet endpoints for Binance Futures testnet,
        # uncomment or adjust the following. This is left as a best-effort and may
        # need updating depending on the ccxt version.
        if self.use_testnet:
            logger.info("Binance sandbox mode enabled")
            # CCXT's testnet setting for Binance futures can vary; ccxt may honor 'urls' override:
            params['urls'] = {
                # Common testnet endpoints—if incorrect for your ccxt version, update accordingly.
                'api': {
                    'public': 'https://testnet.binancefuture.com/fapi/v1',
                    'private': 'https://testnet.binancefuture.com/fapi/v1',
                }
            }
            # Some setups simply set 'test' flag; ccxt historically supports 'sandboxMode' on some wrappers.
            params['options']['defaultType'] = 'future'

        self.exchange = ccxt.binance(params)
        # For some ccxt versions you need to set sandboxMode explicitly:
        try:
            if self.use_testnet:
                # ccxt binance has attribute 'set_sandbox_mode' in some versions
                if hasattr(self.exchange, 'set_sandbox_mode'):
                    self.exchange.set_sandbox_mode(True)
        except Exception:
            pass

        # Load markets once
        try:
            await self.exchange.load_markets()
        except Exception as e:
            logger.warning("Warning loading markets for BinanceClient: %s", e)

        self._initialized = True

    async def fetch_all_symbols(self) -> List[str]:
        """
        Return a list of symbol strings, e.g. ["BTC/USDT", "ETH/USDT", ...]
        """
        await self._ensure_exchange()
        try:
            markets = self.exchange.markets or {}
            return list(markets.keys())
        except Exception as e:
            logger.warning("fetch_all_symbols failed: %s", e)
            return []

    async def fetch_ticker(self, symbol: str) -> Optional[dict]:
        await self._ensure_exchange()
        try:
            t = await self.exchange.fetch_ticker(symbol)
            return t
        except BadRequest as e:
            logger.warning("fetch_ticker BadRequest for %s: %s", symbol, e)
            return None
        except (NetworkError, RequestTimeout) as e:
            logger.warning("fetch_ticker network/timeout for %s: %s", symbol, e)
            return None
        except ExchangeError as e:
            logger.warning("fetch_ticker ExchangeError for %s: %s", symbol, e)
            return None
        except Exception as e:
            logger.exception("fetch_ticker unexpected error for %s: %s", symbol, e)
            return None

    async def fetch_ohlcv(self, symbol: str, timeframe: str = '1m', since: Optional[int] = None, limit: int = 100):
        """
        Robust wrapper for fetch_ohlcv. Returns list of OHLCV rows or None on error/invalid symbol.
        Catches ccxt BadRequest errors (including binance -1122 Invalid symbol status) and returns None.
        """
        await self._ensure_exchange()
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
            if not ohlcv:
                logger.debug("fetch_ohlcv returned empty for %s %s", symbol, timeframe)
                return None
            return ohlcv
        except BadRequest as e:
            # Frequent on Binance for symbols not active on that market (e.g. -1122)
            logger.warning("fetch_ohlcv BadRequest for %s: %s", symbol, e)
            return None
        except (NetworkError, RequestTimeout) as e:
            logger.warning("fetch_ohlcv network/timeout for %s: %s", symbol, e)
            return None
        except ExchangeError as e:
            logger.warning("fetch_ohlcv ExchangeError for %s: %s", symbol, e)
            return None
        except Exception as e:
            logger.exception("fetch_ohlcv unexpected error for %s: %s", symbol, e)
            return None

    async def create_order(self, symbol: str, type: str, side: str, amount: float, price: Optional[float] = None, params: Optional[dict] = None) -> Any:
        """
        Wrapper around ccxt.create_order. If dry_run=True this function simulates an order and returns a simulated structure.
        """
        await self._ensure_exchange()
        if self.dry_run:
            logger.info("DRY RUN create_order %s %s %s @%s qty=%s params=%s", symbol, type, side, price, amount, params)
            # Return a minimal simulated order dict
            return {
                "id": "dryrun-" + symbol.replace('/', ''),
                "symbol": symbol,
                "type": type,
                "side": side,
                "price": price,
                "amount": amount,
                "status": "open",
                "info": {"dry_run": True}
            }
        try:
            # ccxt create_order signature: create_order(symbol, type, side, amount, price=None, params={})
            return await self.exchange.create_order(symbol, type, side, amount, price, params or {})
        except Exception as e:
            logger.exception("create_order failed for %s %s %s %s: %s", symbol, type, side, amount, e)
            raise

    async def fetch_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.warning("fetch_open_orders failed for %s: %s", symbol, e)
            return []

    async def fetch_order(self, order_id: str, symbol: Optional[str] = None) -> Optional[dict]:
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_order(order_id, symbol)
        except Exception as e:
            logger.warning("fetch_order failed for %s (%s): %s", order_id, symbol, e)
            return None

    async def close(self):
        try:
            if self.exchange:
                await self.exchange.close()
        except Exception:
            logger.debug("Error closing exchange client", exc_info=True)
