#!/usr/bin/env python3
"""
Diagnóstico único para errores de firma (-1022) con Binance (ccxt).
Uso: coloca este archivo en la raíz del repo, activa tu virtualenv y ejecútalo:
    python diagnose_binance_auth.py

Qué hace (todo en una ejecución):
- Carga variables de entorno (.env si existe).
- Muestra valores clave (enmascarados) y la flag USE_TESTNET/DRY_RUN.
- Crea un cliente ccxt.binance (async) con opciones apropiadas (futures/defaultType, adjustForTimeDifference).
- Recupera server time vía API y calcula la diferencia con el reloj local.
- Llama a una API privada de sólo lectura (fetch_balance) para forzar la creación de la firma sin realizar órdenes.
- Si falla por firma, extrae la última petición HTTP (URL) y registra una versión con la signature eliminada
  e imprime el timestamp usado en la petición. También imprime el host/endpoint usado para verificar testnet vs mainnet.
- Sugiere la causa más probable según los resultados.

No imprime ni guarda tu BINANCE_API_SECRET ni ninguna signature.
"""

import asyncio
import os
import time
import logging
import urllib.parse as up
from dotenv import load_dotenv

try:
    import ccxt.async_support as ccxt
    from ccxt.base.errors import AuthenticationError, ExchangeError, NetworkError
except Exception as e:
    raise SystemExit("Falta instalar ccxt: pip install ccxt --upgrade ; error: %s" % e)

# Cargar .env si existe
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("diagnose_binance_auth")


def mask(s: str, keep_start: int = 4, keep_end: int = 4) -> str:
    if not s:
        return "<EMPTY>"
    if len(s) <= keep_start + keep_end:
        return s[:keep_start] + "..."  # muy corto, no mostrar todo
    return f"{s[:keep_start]}...{s[-keep_end:]}"


def redact_signature_from_url(url: str) -> (str, str):
    """
    Devuelve (safe_url, timestamp_value_or_empty).
    Quita el parámetro 'signature' de la querystring para que sea seguro mostrar.
    """
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
            qs_filtered.append((k, v if k.lower() != "signature" else "<removed>"))
        safe_q = up.urlencode(qs_filtered)
        safe = up.urlunparse(p._replace(query=safe_q))
        return safe, ts
    except Exception:
        return url, ""


async def run_diagnostics():
    api_key = os.getenv("BINANCE_API_KEY", "")
    api_secret = os.getenv("BINANCE_API_SECRET", "")
    use_testnet_env = os.getenv("USE_TESTNET", "True")
    dry_run_env = os.getenv("DRY_RUN", "False")

    use_testnet = str(use_testnet_env).lower() in ("true", "1", "yes")
    dry_run = str(dry_run_env).lower() in ("true", "1", "yes")

    logger.info("Leyendo variables de entorno (enmascaradas):")
    logger.info("  USE_TESTNET = %s", use_testnet)
    logger.info("  DRY_RUN     = %s", dry_run)
    logger.info("  BINANCE_API_KEY    = %s", mask(api_key))
    logger.info("  BINANCE_API_SECRET = %s", mask(api_secret))

    if not api_key or not api_secret:
        logger.error("BINANCE_API_KEY o BINANCE_API_SECRET vacías. Revisa tu .env o variables de entorno.")
        return 1

    # Preparar parámetros para ccxt.binance (async)
    params = {
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {
            "defaultType": "future",
            "adjustForTimeDifference": True,
        },
        # no verbose por defecto (puede mostrar signature)
    }

    if use_testnet:
        logger.info("Configurando endpoints de TESTNET (binance futures testnet).")
        params["urls"] = {
            "api": {
                "public": "https://testnet.binancefuture.com",
                "private": "https://testnet.binancefuture.com",
                "fapiPublic": "https://testnet.binancefuture.com",
                "fapiPrivate": "https://testnet.binancefuture.com",
            }
        }

    exchange = ccxt.binance(params)

    # Intentar set_sandbox_mode si la versión de ccxt lo soporta
    try:
        if hasattr(exchange, "set_sandbox_mode"):
            exchange.set_sandbox_mode(use_testnet)
    except Exception:
        pass

    exit_code = 0
    try:
        # 1) load_markets (no necesario pero ayuda a inicializar)
        try:
            await exchange.load_markets()
            logger.info("load_markets OK (mercados cargados).")
        except Exception as e:
            logger.warning("load_markets falló: %s", e)

        # 2) fetch_time: comparar server vs local
        try:
            server_time = None
            try:
                server_time = await exchange.fetch_time()  # ms (ccxt)
            except Exception:
                # fallback a endpoint raw
                if hasattr(exchange, "fapiPublicGetTime"):
                    info = await exchange.fapiPublicGetTime()
                    server_time = int(info.get("serverTime", info.get("time", 0)))
            local_ms = int(time.time() * 1000)
            logger.info("Server time (ms): %s", server_time)
            logger.info("Local  time (ms): %s", local_ms)
            if server_time is not None:
                diff = server_time - local_ms
                logger.info("Diferencia server - local (ms): %d", diff)
                if abs(diff) > 5000:
                    logger.warning("Diferencia de tiempo > 5000ms. Sincroniza el reloj (ntp) o deja que ccxt ajuste la diferencia.")
            else:
                logger.warning("No se pudo obtener server time.")
        except Exception as e:
            logger.warning("Error obteniendo server time: %s", e)

        # 3) Llamada privada de sólo lectura para forzar la firma (NO modifica nada).
        # Usamos fetch_balance que en future cae en fapiPrivateGetAccount (lectura).
        logger.info("Intentando una llamada privada de sólo lectura (fetch_balance).")
        try:
            bal = await exchange.fetch_balance()
            logger.info("fetch_balance OK. Respuesta parcial (enmascarada): keys=%s", list(bal.keys())[:5])
            logger.info("Autenticación parece correcta (firma válida).")
        except AuthenticationError as ae:
            logger.error("Respuesta: AuthenticationError: %s", ae)
            # Tratar de extraer la última petición y mostrar URL sin signature
            try:
                req = getattr(exchange, "last_http_request", None) or getattr(exchange, "last_request", None)
                resp = getattr(exchange, "last_http_response", None) or getattr(exchange, "last_response", None)
                safe_req_url = None
                ts_in_req = ""
                host = ""
                if isinstance(req, dict):
                    url = req.get("url") or ""
                    safe_req_url, ts_in_req = redact_signature_from_url(url)
                    host = up.urlparse(url).netloc
                elif isinstance(req, str):
                    safe_req_url, ts_in_req = redact_signature_from_url(req)
                    host = up.urlparse(req).netloc
                if safe_req_url:
                    logger.error("Última petición (signature eliminado): %s", safe_req_url)
                    if ts_in_req:
                        logger.error("Timestamp en la petición: %s", ts_in_req)
                if host:
                    logger.info("Host/endpoint usado en la última petición: %s", host)
                logger.error("Última respuesta bruta (server): %s", resp)
            except Exception as e2:
                logger.debug("No se pudo extraer último request/response: %s", e2)
            exit_code = 2
        except ExchangeError as ee:
            logger.error("ExchangeError (no auth-specific): %s", ee)
            # intentar extraer último request para diagnosticar
            try:
                req = getattr(exchange, "last_http_request", None) or getattr(exchange, "last_request", None)
                if req:
                    url = req.get("url") if isinstance(req, dict) else req
                    safe_req_url, ts = redact_signature_from_url(url)
                    logger.error("Última petición (signature eliminado): %s", safe_req_url)
            except Exception:
                pass
            exit_code = 3
        except NetworkError as ne:
            logger.error("NetworkError al contactar Binance: %s", ne)
            exit_code = 4
        except Exception as e:
            logger.exception("Error inesperado durante fetch_balance: %s", e)
            exit_code = 5

        # 4) Mostrar recomendación corta basada en lo recolectado.
        if exit_code == 0:
            logger.info("Diagnóstico básico OK: la firma fue aceptada y la autenticación funciona.")
            logger.info("Si aún ves -1022 en create_order, puede ser un problema puntual de endpoint o permisos específicos (futures trading).")
        elif exit_code == 2:
            logger.info("Diagnóstico: la firma fue rechazada (AuthenticationError). Posibles causas, en orden:")
            logger.info("  1) API key/secret incorrectos o con espacios/charset extraño.")
            logger.info("  2) Estás usando claves de MAINNET con endpoints TESTNET (o al revés).")
            logger.info("  3) Reloj local desincronizado (timestamp demasiado distinto).")
            logger.info("  4) Las claves no tienen permisos de FUTURES trading (para USDT-M).")
            logger.info("Recomendaciones inmediatas:")
            logger.info("  - Verifica USE_TESTNET y confirma que usas las claves correspondientes.")
            logger.info("  - Vuelve a copiar/pegar el secret desde Binance y revisa espacios finales.")
            logger.info("  - Ejecuta: sudo timedatectl set-ntp true  (o sincroniza el reloj) y vuelve a probar.")
            logger.info("  - Revisa el 'Última petición (signature eliminado)' que se imprimió arriba y comparte esa URL (sin signature) si quieres que la revise.")
        else:
            logger.info("Diagnóstico inconcluso. Revisa las líneas anteriores para el error concreto.")
    finally:
        try:
            await exchange.close()
        except Exception:
            pass

    return exit_code


if __name__ == "__main__":
    code = asyncio.run(run_diagnostics())
    # exit code 0 => OK auth, 2 => signature/auth failed, other => network/other
    if code == 0:
        logger.info("FIN: diagnóstico completado con éxito.")
    elif code == 2:
        logger.info("FIN: firma rechazada. Sigue las recomendaciones mostradas.")
    else:
        logger.info("FIN: diagnóstico finalizado (código %s).", code)
    raise SystemExit(code)
