#!/usr/bin/env bash
# Safe patcher: hace backup de unified_main.py y elimina cualquier argumento `dry_run=...`
# y fuerza use_testnet=True reemplazando use_testnet=False.
# Ejecuta desde la raíz del repo:
#   chmod +x fix_unified_main.sh
#   ./fix_unified_main.sh

set -euo pipefail

FILE="unified_main.py"
BACKUP="${FILE}.bak.$(date +%s)"
if [ ! -f "$FILE" ]; then
  echo "Error: $FILE no existe en el directorio actual."
  exit 1
fi

cp "$FILE" "$BACKUP"
echo "Backup creado: $BACKUP"

python3 - <<'PY'
import re, sys, pathlib

fname = "unified_main.py"
text = pathlib.Path(fname).read_text()

# 1) Eliminar ocurrencias como ", dry_run=True" o "dry_run=True," o "dry_run = True"
text = re.sub(r',\s*dry_run\s*=\s*(?:True|False)\s*', '', text)
text = re.sub(r'dry_run\s*=\s*(?:True|False)\s*,\s*', '', text)
text = re.sub(r'\bdry_run\s*=\s*(?:True|False)\b', '', text)

# 2) Forzar use_testnet=True cuando esté escrito como use_testnet=False
text = re.sub(r'use_testnet\s*=\s*False', 'use_testnet=True', text)

# 3) Limpieza: en caso de dejar comas dobles por eliminación, arreglar ", ,"
text = re.sub(r',\s*,', ',', text)

pathlib.Path(fname).write_text(text)
print("Archivo parchado:", fname)
PY

echo "Hecho. Revisa los cambios y prueba:"
echo "  git diff $BACKUP..$FILE"
echo "Luego ejecuta:"
echo "  python unified_main.py"
