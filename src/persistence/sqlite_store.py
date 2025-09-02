import os
import sqlite3
import time
from typing import Optional, Tuple
from src.config import DB_PATH, DATA_DIR

def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH) or DATA_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            qty REAL NOT NULL,
            fee REAL NOT NULL,
            status TEXT NOT NULL
        )
        """
        )
        cur.execute("""
        CREATE TABLE IF NOT EXISTS balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            balance_usdt REAL NOT NULL
        )
        """
        )
        conn.commit()

def save_order(symbol: str, side: str, price: float, qty: float, fee: float, status: str):
    _ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor(
        )
        cur.execute(
            "INSERT INTO orders (ts, symbol, side, price, qty, fee, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (int(time.time()), symbol, side, float(price), float(qty), float(fee), status),
        )
        conn.commit()

def save_balance(balance_usdt: float):
    _ensure_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO balances (ts, balance_usdt) VALUES (?, ?)",
            (int(time.time()), float(balance_usdt)),
        )
        conn.commit()
