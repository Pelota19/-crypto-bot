import asyncio
import logging
from typing import Any, Dict, Optional

import ccxt.async_support as ccxt

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        use_testnet: bool = False,
        enable_rate_limit: bool = True,
    ):
        """
        Cliente ligero para Binance (ccxt async). Este fichero contiene la lógica para:
         - inicializar el exchange (futures por defecto)
         - comprobar modo de posición (dual/hedge) y cachearlo
         - crear órdenes asegurando positionSide coherente
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.use_testnet = bool(use_testnet)
        self.enable_rate_limit = bool(enable_rate_limit)
        self.exchange: Optional[ccxt.binance] = None
        self._dual_position_mode: Optional[bool] = None
        # lock para inicialización segura
        self._init_lock = asyncio.Lock()

    async def _ensure_exchange(self) -> None:
        """
        Inicializa y configura la instancia ccxt.binance (async).
        Es idempotente y segura para llamadas concurrentes.
        """
        if self.exchange is not None:
            return
        async with self._init_lock:
            if self.exchange is not None:
                return
            params = {
                "apiKey": self.api_key,
                "secret": self.api_secret,
                "enableRateLimit": self.enable_rate_limit,
                "options": {
                    "defaultType": "future",  # usar futures (USDT-M)
                    "adjustForTimeDifference": True,
                },
            }

            if self.use_testnet:
                # endpoints de futures testnet
                params["urls"] = {
                    "api": {
                        "public": "https://testnet.binancefuture.com",
                        "private": "https://testnet.binancefuture.com",
                        "fapiPublic": "https://testnet.binancefuture.com",
                        "fapiPrivate": "https://testnet.binancefuture.com",
                    }
                }

            self.exchange = ccxt.binance(params)

            # si ccxt expone set_sandbox_mode, usamos
            try:
                if hasattr(self.exchange, "set_sandbox_mode"):
                    try:
                        self.exchange.set_sandbox_mode(self.use_testnet)
                    except Exception:
                        # no crítico
                        pass
            except Exception:
                pass

            # cargar mercados para inicializar símbolos/market data
            try:
                await self.exchange.load_markets()
            except Exception as e:
                logger.debug("load_markets fallo durante init: %s", e)

    async def close(self) -> None:
        if self.exchange:
            try:
                await self.exchange.close()
            except Exception:
                pass
            self.exchange = None

    async def fetch_balance(self) -> Dict[str, Any]:
        """
        Wrapper para fetch_balance que garantiza inicialización.
        """
        await self._ensure_exchange()
        return await self.exchange.fetch_balance()

    async def fetch_time(self) -> Optional[int]:
        """
        Devuelve server time (ms) si disponible, None si falla.
        """
        await self._ensure_exchange()
        try:
            return await self.exchange.fetch_time()
        except Exception:
            # intentar endpoint directo fapiPublicGetTime si existe
            try:
                if hasattr(self.exchange, "fapiPublicGetTime"):
                    info = await self.exchange.fapiPublicGetTime()
                    # info puede tener 'serverTime' o 'time'
                    if isinstance(info, dict):
                        return int(info.get("serverTime", info.get("time", 0)))
            except Exception:
                pass
        return None

    async def _is_dual_position_mode(self) -> bool:
        """
        Comprueba si la cuenta FUTURES está en Hedge (dual) mode.
        Cachea el resultado en self._dual_position_mode para evitar llamadas repetidas.
        """
        if self._dual_position_mode is not None:
            return self._dual_position_mode

        await self._ensure_exchange()
        val = False
        try:
            # endpoint fapi: positionSide/dual
            # ccxt.request(path, api='fapiPrivate', method='GET', params={})
            # Nota: dependiendo de la versión de ccxt la llamada puede variar; este enfoque ha funcionado.
            resp = await self.exchange.request("positionSide/dual", "fapiPrivate", "GET", {})
            if isinstance(resp, dict):
                v = resp.get("dualSidePosition")
                val = v in (True, "true", "True", "1", 1)
        except Exception as e:
            # Si falla la consulta asumimos One-way (más seguro) y continuamos.
            logger.debug("No se pudo consultar positionSide/dual: %s", e)
            val = False

        self._dual_position_mode = bool(val)
        logger.debug("dual_position_mode=%s", self._dual_position_mode)
        return self._dual_position_mode

    async def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: Optional[float] = None,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Envoltorio de create_order que ajusta positionSide según el modo de la cuenta.
        - Si la cuenta está en Hedge (dual) mode y no se pasó positionSide, lo añade en base a `side`.
        - Si la cuenta NO está en Hedge mode eliminará positionSide para evitar -4061.
        """
        await self._ensure_exchange()
        params = dict(params or {})

        try:
            # Detectar mode dual/hedge (cacheado)
            try:
                dual = await self._is_dual_position_mode()
            except Exception:
                dual = False

            side_l = (side or "").lower() if isinstance(side, str) else None

            if dual:
                # En Hedge mode positionSide es relevante; si no está pasado lo establecemos
                if "positionSide" not in params:
                    if side_l == "buy":
                        params["positionSide"] = "LONG"
                    elif side_l == "sell":
                        params["positionSide"] = "SHORT"
                else:
                    # normalizar si se pasó (asegurar LONG/SHORT)
                    try:
                        ps = str(params.get("positionSide")).upper()
                        if ps in ("LONG", "SHORT", "BOTH"):
                            params["positionSide"] = ps
                    except Exception:
                        pass
            else:
                # En One-way mode no enviar positionSide
                if "positionSide" in params:
                    params.pop("positionSide", None)

            # Hacer la llamada real a ccxt
            result = await self.exchange.create_order(symbol, type, side, amount, price, params or {})
            return result

        except Exception as e:
            # Loguear contexto y re-raise
            try:
                logger.exception("create_order failed for %s %s %s %s: %s", symbol, type, side, amount, e)
            except Exception:
                pass
            raise

    # utilitario para extraer la última petición/response (útil para debugging)
    def get_last_request_info(self) -> Dict[str, Any]:
        """
        Devuelve un diccionario con la última petición y respuesta guardadas por ccxt (si existen).
        No imprime firmas; sirve para debug seguro.
        """
        info: Dict[str, Any] = {}
        if not self.exchange:
            return info
        try:
            req = getattr(self.exchange, "last_http_request", None) or getattr(self.exchange, "last_request", None)
            resp = getattr(self.exchange, "last_http_response", None) or getattr(self.exchange, "last_response", None)
            info["last_request"] = req
            info["last_response"] = resp
        except Exception:
            pass
        return info
