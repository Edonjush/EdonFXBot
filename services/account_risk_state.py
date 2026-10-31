"""Persist observed equity baselines for daily and since-install drawdown gates.

The high-water mark begins at first observation by this version of the bot;
this is not a substitute for importing historical account equity.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from config.settings import DATA_DIR, MAX_DAILY_DRAWDOWN, MAX_TOTAL_DRAWDOWN

STATE_PATH = DATA_DIR / "account_risk_state.json"


def update_drawdown_metrics(equity):
    equity = float(equity)
    if not (equity > 0):
        raise ValueError("Account equity must be positive")
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    state = {}
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RuntimeError("Risk state file is unreadable; refusing automated trading")
    if not state:
        state = {"day": day, "day_start_equity": equity, "day_high_water_equity": equity, "high_water_equity": equity}
    elif state.get("day") != day:
        state["day"] = day
        state["day_start_equity"] = equity
        state["day_high_water_equity"] = equity
    peak = max(float(state.get("high_water_equity", equity)), equity)
    day_peak = max(float(state.get("day_high_water_equity", equity)), equity)
    state["high_water_equity"] = peak
    state["day_high_water_equity"] = day_peak
    state["updated_utc"] = now.isoformat()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)
    daily_dd = max(0.0, (day_peak - equity) / day_peak * 100.0)
    total_dd = max(0.0, (peak - equity) / peak * 100.0)
    return {
        "daily_drawdown_pct": daily_dd,
        "total_drawdown_pct": total_dd,
        "daily_drawdown_limit_pct": MAX_DAILY_DRAWDOWN * 100,
        "total_drawdown_limit_pct": MAX_TOTAL_DRAWDOWN * 100,
        "risk_state_updated_utc": state.get("updated_utc"),
    }
