"""Shared deterministic feature builder for offline training and live signals."""
import numpy as np
import pandas as pd
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

FEATURE_COLUMNS = [
    "EMA20", "EMA50", "EMA200", "trend_strength", "RSI", "MACD",
    "ATR", "return", "body_strength", "vol_expansion",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"OHLC data missing columns: {missing}")
    result = df.copy()
    for column in required:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if not np.isfinite(result[required].to_numpy(dtype=float)).all():
        # Preserve row alignment; invalid rows become NaN and are removed below.
        result[required] = result[required].replace([np.inf, -np.inf], np.nan)
    result["EMA20"] = EMAIndicator(result["close"], window=20).ema_indicator()
    result["EMA50"] = EMAIndicator(result["close"], window=50).ema_indicator()
    result["EMA200"] = EMAIndicator(result["close"], window=200).ema_indicator()
    result["RSI"] = RSIIndicator(result["close"], window=14).rsi()
    result["MACD"] = MACD(result["close"]).macd_diff()
    result["ATR"] = AverageTrueRange(result["high"], result["low"], result["close"], window=14).average_true_range()
    result["return"] = result["close"].pct_change()
    safe_atr = result["ATR"].where(result["ATR"] != 0)
    result["body_strength"] = (result["close"] - result["open"]).abs() / safe_atr
    atr_mean = result["ATR"].rolling(20, min_periods=20).mean().where(lambda x: x != 0)
    result["vol_expansion"] = result["ATR"] / atr_mean
    result["trend_strength"] = (result["EMA20"] - result["EMA50"]).abs() / safe_atr
    result[FEATURE_COLUMNS] = result[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan)
    return result.dropna(subset=FEATURE_COLUMNS).copy()


def get_feature_list():
    return list(FEATURE_COLUMNS)
