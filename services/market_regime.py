"""Price-normalized market regime classification."""
import math


def detect_market_regime(df, symbol="EURUSD", volatile_atr_pct=None):
    if df is None or len(df) == 0 or not {"ATR", "close"}.issubset(df.columns):
        return "UNKNOWN"
    try:
        atr, close = float(df.iloc[-1]["ATR"]), float(df.iloc[-1]["close"])
        if not math.isfinite(atr) or not math.isfinite(close) or atr <= 0 or close <= 0:
            return "UNKNOWN"
        if volatile_atr_pct is None:
            name = str(symbol).upper()
            volatile_atr_pct = 0.0035 if "XAU" in name else (0.01 if any(x in name for x in ("BTC", "ETH")) else 0.0015)
        return "VOLATILE" if atr / close > volatile_atr_pct else "NORMAL"
    except (TypeError, ValueError, OverflowError):
        return "UNKNOWN"


def classify_regime(df):
    result = df.copy()
    result["regime"] = "UNKNOWN"
    if {"ATR", "close"}.issubset(result.columns):
        ratio = result["ATR"] / result["close"].replace(0, float("nan"))
        result.loc[ratio <= 0.0015, "regime"] = "NORMAL"
        result.loc[ratio > 0.0015, "regime"] = "VOLATILE"
    result["regime_code"] = result["regime"].map({"NORMAL": 0, "VOLATILE": 1})
    return result
