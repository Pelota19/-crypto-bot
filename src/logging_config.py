import logging
import os
from datetime import datetime
from src.config import LOG_LEVEL

level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
fmt = "%(...

root = logging.getLogger()

# Avoid adding duplicate handlers if this module is imported multiple times
if not root.handlers:
    root.setLevel(level)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter(fmt))
    root.addHandler(ch)

    # File handler: one file per day
    os.makedirs("logs", exist_ok=True)
    log_path = f"logs/crypto_bot_{datetime.now().strftime('%Y-%m-%d')}.log"
    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(fmt))
    root.addHandler(fh)