# Añadir/pegar estas funciones dentro de la clase BinanceClient (reemplazar la create_order existente)

async def _is_dual_position_mode(self) -> bool:
    """
    Comprueba si la cuenta está en Hedge (dual) mode.
    Cachea el resultado en self._dual_position_mode para evitar llamadas repetidas.
    Devuelve True si la cuenta está en Hedge, False si está en One-way.
    """
    if getattr(self, "_dual_position_mode", None) is not None:
        return self._dual_position_mode
    try:
        # Endpoint fapi: positionSide/dual
        resp = await self.exchange.request("positionSide/dual", "fapiPrivate", "GET", {})
        val = False
        if isinstance(resp, dict):
            v = resp.get("dualSidePosition")
            # puede venir True/False o "true"/"false"
            val = v in (True, "true", "True", "1", 1)
    except Exception:
        # Si falla la consulta asumimos One-way (más seguro)
        val = False
    self._dual_position_mode = bool(val)
    return self._dual_position_mode


async def create_order(self, symbol, type, side, amount=None, price=None, params=None):
    """
    Envoltorio de create_order que ajusta positionSide según el modo de la cuenta.
    - Si la cuenta está en Hedge (dual) mode y no se pasó positionSide, lo añade en base a `side`.
    - Si la cuenta NO está en Hedge mode eliminará positionSide para evitar -4061.
    """
    params = dict(params or {})
    try:
        # Detectar mode dual/hedge
        try:
            dual = await self._is_dual_position_mode()
        except Exception:
            # si algo falla al consultar, asumir One-way (más seguro)
            dual = False

        # Normalizar side a lowercase para decisiones
        side_l = (side or "").lower() if isinstance(side, str) else None

        if dual:
            # Si la cuenta está en hedge, el campo positionSide es requerido para distinguir LONG/SHORT
            if "positionSide" not in params:
                if side_l == "buy":
                    params["positionSide"] = "LONG"
                elif side_l == "sell":
                    params["positionSide"] = "SHORT"
                # si side no es buy/sell (raro), no añadimos nada y dejamos que ccxt/bridge falle con detalle
            else:
                # Si se proporcionó positionSide explícito, normalizar a mayúsculas esperadas
                try:
                    ps = str(params.get("positionSide")).upper()
                    if ps in ("LONG", "SHORT", "BOTH"):
                        params["positionSide"] = ps
                except Exception:
                    pass
        else:
            # Si no está en hedge, asegurarnos de no enviar positionSide
            if "positionSide" in params:
                params.pop("positionSide", None)

        # Llamar al create_order original de ccxt
        return await self.exchange.create_order(symbol, type, side, amount, price, params or {})

    except Exception as e:
        # Mantén el logging existente para traza
        try:
            logger.exception("create_order failed for %s %s %s %s: %s", symbol, type, side, amount, e)
        except Exception:
            pass
        # Re-raise para que el manejo superior vea la excepción como antes
        raise
