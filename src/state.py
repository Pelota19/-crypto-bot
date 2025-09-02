from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass
from src.config import STATE_PATH, DAILY_PROFIT_TARGET_USD, MAX_DAILY_LOSS_USD, DAILY_RESET_HOUR_UTC, DATA_DIR

@dataclass
class BotState:
    date_key: str
    pnl_today: float
    paused: bool

def _today_key_utc(reset_hour: int) -> str:
    t = time.gmtime()
    if t.tm_hour < reset_hour:
        ts = time.time() - 86400
        t = time.gmtime(ts)
    return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"

def load_state() -> BotState:
    os.makedirs(os.path.dirname(STATE_PATH) or DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_PATH):
        st = BotState(_today_key_utc(DAILY_RESET_HOUR_UTC), 0.0, False)
        save_state(st)
        return st
    with open(STATE_PATH, "r") as f:
        d = json.load(f)
    return BotState(d.get("date_key"), float(d.get("pnl_today", 0.0)), bool(d.get("paused", False)))

def save_state(state: BotState):
    os.makedirs(os.path.dirname(STATE_PATH) or DATA_DIR, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump({"date_key": state.date_key, "pnl_today": state.pnl_today, "paused": state.paused}, f)

def reset_if_new_day(state: BotState) -> BotState:
    key = _today_key_utc(DAILY_RESET_HOUR_UTC)
    if key != state.date_key:
        state = BotState(key, 0.0, False)
        save_state(state)
    return state

def can_open_new_trades(state: BotState) -> bool:
    if state.paused:
        return False
    if state.pnl_today >= DAILY_PROFIT_TARGET_USD:
        return False
    if state.pnl_today <= -MAX_DAILY_LOSS_USD:
        return False
    return True

def update_pnl(state: BotState, delta_usd: float) -> BotState:
    state.pnl_today += float(delta_usd)
    save_state(state)
    return state
