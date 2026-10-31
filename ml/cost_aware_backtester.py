"""Conservative OHLC backtester with explicit round-trip transaction costs.

Signals are generated at candle close and entries occur at the next candle open.
If stop-loss and take-profit are both touched in one candle, stop-loss is assumed
first. `round_trip_cost_price` must express spread + both-side slippage + round-
trip commission converted into the instrument's price units.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd


def backtest_signals(candles: pd.DataFrame, signals: pd.Series, *,
                     atr_column="ATR", stop_atr_multiple=2.0,
                     take_profit_atr_multiple=4.0, max_holding_bars=12,
                     round_trip_cost_price=0.0) -> dict:
    required = {"open", "high", "low", "close", atr_column}
    missing = sorted(required.difference(candles.columns))
    if missing:
        raise ValueError(f"Candles missing required columns: {missing}")
    if len(candles) != len(signals):
        raise ValueError("signals and candles must have equal length")
    if not candles.index.is_monotonic_increasing:
        raise ValueError("Candles must be chronological")
    if stop_atr_multiple <= 0 or take_profit_atr_multiple <= 0 or max_holding_bars < 1:
        raise ValueError("Stop, target and holding parameters must be positive")
    cost = float(round_trip_cost_price)
    if not math.isfinite(cost) or cost < 0:
        raise ValueError("round_trip_cost_price must be finite and non-negative")

    data = candles.copy()
    for col in ("open", "high", "low", "close", atr_column):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    if not np.isfinite(data[["open", "high", "low", "close", atr_column]].to_numpy()).all():
        raise ValueError("OHLC/ATR contains missing or non-finite values")
    if (data["high"] < data[["open", "close", "low"]].max(axis=1)).any() or (data["low"] > data[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC candle ranges")

    signal_values = pd.Series(signals, index=candles.index).fillna(0).astype(int)
    if not signal_values.isin([-1, 0, 1]).all():
        raise ValueError("Signals must be -1 (SELL), 0 (flat), or 1 (BUY)")

    trades = []
    next_available = 1
    for i in range(len(data) - 1):
        direction = int(signal_values.iloc[i])
        if direction == 0 or i + 1 < next_available:
            continue
        atr = float(data[atr_column].iloc[i])
        if atr <= 0:
            continue
        entry_index = i + 1
        entry = float(data["open"].iloc[entry_index])
        stop_distance = atr * stop_atr_multiple
        target_distance = atr * take_profit_atr_multiple
        stop = entry - direction * stop_distance
        target = entry + direction * target_distance
        last_index = min(len(data) - 1, entry_index + max_holding_bars - 1)
        exit_price, exit_index, exit_reason = None, last_index, "time"
        for j in range(entry_index, last_index + 1):
            high, low = float(data["high"].iloc[j]), float(data["low"].iloc[j])
            stop_hit = low <= stop if direction == 1 else high >= stop
            target_hit = high >= target if direction == 1 else low <= target
            if stop_hit:
                exit_price, exit_index, exit_reason = stop, j, "stop_loss"
                break
            if target_hit:
                exit_price, exit_index, exit_reason = target, j, "take_profit"
                break
        if exit_price is None:
            exit_price = float(data["close"].iloc[last_index])
        gross_price_move = direction * (exit_price - entry)
        net_price_move = gross_price_move - cost
        gross_r = gross_price_move / stop_distance
        net_r = net_price_move / stop_distance
        trades.append({
            "signal_index": str(data.index[i]), "entry_index": str(data.index[entry_index]),
            "exit_index": str(data.index[exit_index]), "direction": "BUY" if direction == 1 else "SELL",
            "entry": entry, "exit": exit_price, "exit_reason": exit_reason,
            "gross_r": gross_r, "cost_r": cost / stop_distance, "net_r": net_r,
        })
        next_available = exit_index + 1

    returns = np.asarray([t["net_r"] for t in trades], dtype=float)
    wins = returns[returns > 0]
    losses = returns[returns < 0]
    equity = np.cumsum(returns) if len(returns) else np.asarray([], dtype=float)
    if len(equity):
        peaks = np.maximum.accumulate(np.maximum(equity, 0.0))
        max_drawdown = float(np.max(peaks - equity))
    else:
        max_drawdown = 0.0
    return {
        "trades": trades,
        "trade_count": int(len(trades)),
        "win_rate": float(len(wins) / len(trades)) if trades else 0.0,
        "gross_expectancy_r": float(np.mean([t["gross_r"] for t in trades])) if trades else 0.0,
        "net_expectancy_r": float(np.mean(returns)) if trades else 0.0,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and len(wins) else (float("inf") if len(wins) else 0.0),
        "max_drawdown_r": max_drawdown,
        "round_trip_cost_price": cost,
        "assumptions": {
            "entry": "next candle open after signal close",
            "intrabar_collision": "stop-loss first",
            "costs": "caller-supplied round_trip_cost_price subtracted from every trade",
            "positioning": "one position at a time; no pyramiding",
        },
    }
