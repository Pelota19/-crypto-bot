#!/usr/bin/env python3
"""
extract_last7h.py

Uso:
  python3 extract_last7h.py /ruta/al/logfile out.log [--pattern "regex"]

Extrae líneas del logfile donde exista un timestamp ISO "YYYY-MM-DD HH:MM:SS"
y dicho timestamp esté dentro de las últimas 7 horas (UTC). Si se pasa --pattern,
filtra además por la expresión regular (case insensitive).
"""
from datetime import datetime, timezone, timedelta
import re
import sys
import argparse

def find_first_timestamp(line):
    # Busca el primer grupo YYYY-MM-DD HH:MM:SS en la línea
    m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
    return m.group(1) if m else None

def parse_ts(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    except Exception:
        return None

def main():
    p = argparse.ArgumentParser()
    p.add_argument('infile')
    p.add_argument('outfile')
    p.add_argument('--hours', type=int, default=7, help='Horas hacia atrás (default 7)')
    p.add_argument('--pattern', type=str, default=None, help='Regex filter adicional (e.g. "TP placed|SL placed")')
    args = p.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    pat = re.compile(args.pattern, re.IGNORECASE) if args.pattern else None

    written = 0
    with open(args.infile, 'r', errors='ignore') as fin, open(args.outfile, 'w') as fout:
        for line in fin:
            ts_text = find_first_timestamp(line)
            if not ts_text:
                continue
            ts = parse_ts(ts_text)
            if not ts:
                continue
            if ts >= cutoff:
                if pat and not pat.search(line):
                    continue
                fout.write(line)
                written += 1
    print(f"Wrote {written} lines to {args.outfile}")

if __name__ == '__main__':
    main()
