import sqlite3
import threading
from datetime import datetime
from typing import Optional

DB_PATH = "data/crypto_bot.db"
_LOCK = threading.Lock()

def _ensure_db():
    with _LOCK:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                symbol TEXT,
                side TEXT,
                price REAL,
                amount REAL,
                value_usd REAL,
                status TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS balances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                balance_usd REAL
            )
            """
        )
        conn.commit()
        conn.close()

def save_order(symbol: str, side: str, price: float, amount: float, value_usd: float, status: str):
    _ensure_db()
    with _LOCK:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (ts, symbol, side, price, amount, value_usd, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), symbol, side, price, amount, value_usd, status),
        )
        conn.commit()
        conn.close()

def save_balance(balance_usd: float):
    _ensure_db()
    with _LOCK:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO balances (ts, balance_usd) VALUES (?, ?)", (datetime.utcnow().isoformat(), balance_usd))
        conn.commit()
        conn.close()
