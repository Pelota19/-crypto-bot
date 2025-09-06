#!/usr/bin/env python3
"""
Coloca una orden de prueba en Binance Futures TESTNET (o MAINNET si USE_TESTNET=False).

Mejoras respecto a la versión anterior:
 - Detecta stepSize (LOT_SIZE) y minNotional (MIN_NOTIONAL) desde market['info']['filters'] cuando están disponibles.
 - Cuantiza qty al stepSize y asegura que qty >= min_qty calculado (evita qty == 0).
 - Cierra exchange en finally para evitar "Unclosed connector".
 - Mantiene detección de hedge/one-way y añade positionSide cuando corresponde.
"""
import argparse
import asyncio
import os
import time
import logging
import urllib.parse as up
from decimal import Decimal, ROUND_DOWN
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("testnet_place_order")


def mask(s: str, keep_start: int = 4, keep_end: int = 4) -> str:
    if not s:
        return "<EMPTY>"
    if len(s) <= keep_start + keep_end:
        return s[:keep_start] + "..."
    return f"{s[:keep_start]}...{s[-keep_end:]}"


def redact_signature_from_url(url: str) -> (str, str):
    try:
        p = up.urlparse(url)
        qs = up.parse_qsl(p.query, keep_blank_values=True)
        ts = ""
        qs_filtered = []
        for k, v in qs:
            if k.lower() == "signature":
                continue
            if k.lower() == "timestamp":
                ts = v
            qs_filtered.append((k, v))
        safe_q = up.urlencode(qs_filtered)
        safe = up.urlunparse(p._replace(query=safe_q))
        return safe, ts
    except Exception:
        return url, ""


def _parse_filters_from_market(market_info: dict):
    """
    Extrae stepSize (minQty), minQty, minNotional desde market_info['filters'] si están presentes.
    Devuelve (stepSize: Decimal|None, min_qty: Decimal|None, min_notional: Decimal|None).
    """
    step = None
    min_qty = None
    min_notional = None
    try:
        filters = market_info.get("filters", []) if isinstance(market_info, dict) else []
        for f in filters:
            t = f.get("filterType") or f.get("type")  # distintas versiones usan keys distintas
            if t in ("LOT_SIZE", "LOT", "LOT_SIZE"):
                # algunos campos: minQty, stepSize
                ss = f.get("stepSize") or f.get("step")
                mq = f.get("minQty")
                if ss:
                    step = Decimal(str(ss))
                if mq:
                    min_qty = Decimal(str(mq))
            if t in ("MIN_NOTIONAL", "MIN_NOTIONAL"):
                mn = f.get("minNotional") or f.get("notional") or f.get("minNotional")
                if mn:
                    min_notional = Decimal(str(mn))
    except Exception:
        pass
    return step, min_qty, min_notional


def quantize_to_step(d: Decimal, step: Decimal) -> Decimal:
    """
    Cuantiza el Decimal d al step (ej: step=Decimal('0.001')) redondeando DOWN.
    """
    if step is None or step == 0:
        return d
    # obtener número de decimales del step
    exp = -step.as_tuple().exponent
    if exp < 0:
        exp = 0
    fmt = "0." + "0" * (exp - 1) + "1" if exp > 0 else "1"
    return d.quantize(Decimal(fmt), rounding=ROUND_DOWN)


async def main():
    parser = argparse.ArgumentParser(description="Place a small test order on Binance Futures (testnet)")
    parser.add_argument("--symbol", default="BTC/USDT", help="Market symbol (default BTC/USDT)")
    parser.add_argument("--side", choices=["buy", "sell"], default="buy", help="buy or sell")
    parser.add_argument("--amount-usd", type=float, default=10.0, help="Notional in USD to use (default 10)")
    parser.add_argument("--order-type", choices=["limit", "market"], default="limit", help="Order type")
    parser.add_argument("--offset-pct", type=float, default=1.0, help="Price offset percent for limit orders (default 1.0)")
    parser.add_argument("--testnet", choices=["true", "false"], default=None, help="Override USE_TESTNET")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually place the order, just show params")
    args = parser.parse_args()

    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    use_testnet_env = os.getenv("USE_TESTNET", "True") if args.testnet is None else args.testnet
    use_testnet = str(use_testnet_env).lower() in ("true", "1", "yes")

    logger.info("USE_TESTNET = %s", use_testnet)
    logger.info("BINANCE_API_KEY = %s", mask(api_key))

    if not api_key or not api_secret:
        logger.error("Faltan BINANCE_API_KEY o BINANCE_API_SECRET en el entorno. Revisa tu .env")
        return 2

    try:
        import ccxt.async_support as ccxt
        from ccxt.base.errors import AuthenticationError, ExchangeError, NetworkError
    except Exception as e:
        logger.error("Falta instalar ccxt: pip install ccxt --upgrade ; error: %s", e)
        return 3

    params = {
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
            "adjustForTimeDifference": True,
        },
    }

    if use_testnet:
        params["urls"] = {
            "api": {
                "public": "https://testnet.binancefuture.com",
                "private": "https://testnet.binancefuture.com",
                "fapiPublic": "https://testnet.binancefuture.com",
                "fapiPrivate": "https://testnet.binancefuture.com",
            }
        }

    exchange = ccxt.binance(params)

    # set sandbox mode if available
    try:
        if hasattr(exchange, "set_sandbox_mode"):
            exchange.set_sandbox_mode(use_testnet)
    except Exception:
        pass

    try:
        # server time
        try:
            server_time = await exchange.fetch_time()
        except Exception:
            server_time = None
        local_ms = int(time.time() * 1000)
        logger.info("Server time (ms): %s", server_time)
        logger.info("Local  time (ms): %s", local_ms)
        if server_time is not None:
            logger.info("Diff ms: %d", server_time - local_ms)

        await exchange.load_markets()

        # --- parametros de la orden ---
        symbol = args.symbol.upper()
        side = args.side.lower()
        order_type = args.order_type.lower()
        amount_usd = Decimal(str(args.amount_usd))
        offset_pct = Decimal(str(args.offset_pct))
        dry_run = args.dry_run

        # obtener ticker
        try:
            ticker = await exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error("No se pudo obtener ticker para %s: %s", symbol, e)
            return 4

        bid = Decimal(str(ticker.get("bid") or ticker.get("last") or 0))
        ask = Decimal(str(ticker.get("ask") or ticker.get("last") or 0))
        if bid == 0 or ask == 0:
            logger.error("No se pudo obtener bid/ask para %s", symbol)
            return 5

        # precio objetivo
        if order_type == "market":
            price = None
            use_price = (bid + ask) / Decimal(2)
            qty = (amount_usd / use_price) if use_price > 0 else Decimal("0")
        else:
            if side == "buy":
                price = (bid * (Decimal(1) - offset_pct / Decimal(100)))
            else:
                price = (ask * (Decimal(1) + offset_pct / Decimal(100)))
            price = price.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)  # redondeo inicial seguro
            qty = (amount_usd / price) if price > 0 else Decimal("0")

        # obtener info del market para stepSize/minNotional
        market = exchange.markets.get(symbol) or {}
        step, min_qty_filter, min_notional_filter = _parse_filters_from_market(market.get("info", {}))

        # si no hay step en filters, usar precision amount si existe
        if step is None:
            try:
                amount_prec = market.get("precision", {}).get("amount")
                if amount_prec is not None:
                    step = Decimal("1").scaleb(-int(amount_prec))
            except Exception:
                step = None

        # calcular min_qty si no existe pero hay min_notional
        min_qty = None
        if min_qty_filter is not None:
            min_qty = min_qty_filter
        elif min_notional_filter is not None and price is not None and price > 0:
            min_qty = (min_notional_filter / price).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

        # cuantizar qty al step y garantizar >= min_qty
        if qty <= 0:
            logger.error("Cantidad calculada es 0 o negativa: %s (price=%s). Ajusta amount-usd o symbol.", qty, price)
            return 6

        qty_dec = Decimal(qty)
        if step:
            qty_q = quantize_to_step(qty_dec, step)
        else:
            # fallback: redondear a 8 decimales
            qty_q = qty_dec.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

        if min_qty and qty_q < min_qty:
            # ajustar al mínimo (y cuantizar)
            logger.warning("Qty calculada %s es menor que min_qty %s, ajustando al mínimo.", qty_q, min_qty)
            qty_q = min_qty
            if step:
                qty_q = quantize_to_step(qty_q, step)

        # último chequeo
        if qty_q <= 0:
            logger.error("Cantidad ajustada sigue siendo 0 o negativa: %s (price=%s). No se puede crear orden.", qty_q, price)
            return 6

        # preparar params (positionSide si dual)
        async def is_dual_mode() -> bool:
            try:
                resp = await exchange.request("positionSide/dual", "fapiPrivate", "GET", {})
                if isinstance(resp, dict):
                    v = resp.get("dualSidePosition")
                    return v in (True, "true", "True", "1", 1)
            except Exception:
                pass
            return False

        dual = await is_dual_mode()
        params_order = {"timeInForce": "GTC"}
        if dual:
            params_order["positionSide"] = "LONG" if side == "buy" else "SHORT"

        logger.info(
            "Preparando orden: %s %s %s USD -> qty=%s price=%s order_type=%s dual=%s step=%s min_qty=%s min_notional=%s",
            symbol,
            side.upper(),
            str(amount_usd),
            str(qty_q),
            str(price),
            order_type,
            dual,
            str(step),
            str(min_qty),
            str(min_notional_filter),
        )
        logger.info("Params (no secret): %s", params_order)

        if dry_run:
            logger.info("Dry-run activado, no se enviará la orden.")
            return 0

        # realizar la orden
        try:
            if order_type == "market":
                order = await exchange.create_order(symbol, "market", side, float(qty_q), None, params_order)
            else:
                order = await exchange.create_order(symbol, "limit", side, float(qty_q), float(price), params_order)

            logger.info("Orden creada: %s", order)
            order_id = order.get("id") or order.get("orderId") or order.get("clientOrderId")
            status = order.get("status")
            logger.info("Order id: %s  status: %s", order_id, status)
            logger.info("Respuesta completa (peek): keys=%s", list(order.keys())[:12])
            if use_testnet:
                logger.info("Ve a https://testnet.binancefuture.com y en la sección 'Orders' o 'Positions' busca el orderId o símbolo para verificar.")
            else:
                logger.info("Ve a https://www.binance.com y en la sección 'Orders' o 'Positions' busca el orderId o símbolo para verificar.")
        except AuthenticationError as ae:
            logger.error("AuthenticationError: %s", ae)
            req = getattr(exchange, "last_http_request", None) or getattr(exchange, "last_request", None)
            resp = getattr(exchange, "last_http_response", None) or getattr(exchange, "last_response", None)
            if req:
                url = req.get("url") if isinstance(req, dict) else req
                safe, ts = redact_signature_from_url(url)
                logger.error("Última petición (signature eliminado): %s", safe)
                if ts:
                    logger.error("Timestamp en la petición: %s", ts)
            logger.error("Última respuesta bruta: %s", resp)
            return 7
        except ExchangeError as ee:
            logger.error("ExchangeError al crear orden: %s", ee)
            req = getattr(exchange, "last_http_request", None) or getattr(exchange, "last_request", None)
            resp = getattr(exchange, "last_http_response", None) or getattr(exchange, "last_response", None)
            if req:
                url = req.get("url") if isinstance(req, dict) else req
                safe, ts = redact_signature_from_url(url)
                logger.error("Última petición (signature eliminado): %s", safe)
                if ts:
                    logger.error("Timestamp en la petición: %s", ts)
            logger.error("Última respuesta bruta: %s", resp)
            return 8
        except Exception as e:
            logger.exception("Error inesperado al crear orden: %s", e)
            req = getattr(exchange, "last_http_request", None) or getattr(exchange, "last_request", None)
            resp = getattr(exchange, "last_http_response", None) or getattr(exchange, "last_response", None)
            if req:
                url = req.get("url") if isinstance(req, dict) else req
                safe, ts = redact_signature_from_url(url)
                logger.error("Última petición (signature eliminado): %s", safe)
                if ts:
                    logger.error("Timestamp en la petición: %s", ts)
            logger.error("Última respuesta bruta: %s", resp)
            return 9

        return 0

    finally:
        try:
            await exchange.close()
        except Exception:
            pass


if __name__ == "__main__":
    code = asyncio.run(main())
    raise SystemExit(code)
