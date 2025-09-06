import sys
import os
from importlib import reload

# 1) Limpiar __pycache__ de src/exchange
for root, dirs, files in os.walk("src/exchange"):
    for d in dirs:
        if d == "__pycache__":
            path = os.path.join(root, d)
            print("Removing cache:", path)
            try:
                import shutil
                shutil.rmtree(path)
            except Exception as e:
                print("Failed to remove:", path, e)

# 2) Asegurar que src está en sys.path
src_path = os.path.abspath("src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# 3) Importar BinanceClient y recargar
import src.exchange.binance_client as bc
reload(bc)

# 4) Verificar si create_bracket_order existe
print("BinanceClient loaded from:", bc.__file__)
print("Has create_bracket_order:", hasattr(bc.BinanceClient, "create_bracket_order"))

# 5) Opcional: probar crear objeto
client = bc.BinanceClient(dry_run=True)
print("Instance created:", client)
