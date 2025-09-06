#!/bin/bash
# clean_and_test.sh
# Limpia __pycache__, asegura virtualenv y prueba BinanceClient

echo "Desactivando virtualenv si está activo..."
deactivate 2>/dev/null || true

echo "Activando virtualenv..."
source .venv/bin/activate

echo "Borrando todos los __pycache__..."
find . -name "__pycache__" -exec rm -rf {} +

echo "Verificando el archivo binance_client.py correcto..."
python3 - <<'END'
import src.exchange.binance_client as bc
print("Archivo cargado:", bc.__file__)
print("Tiene create_bracket_order:", hasattr(bc.BinanceClient, "create_bracket_order"))
END

echo "Si 'Tiene create_bracket_order: True', ya puedes correr unified_main.py"
